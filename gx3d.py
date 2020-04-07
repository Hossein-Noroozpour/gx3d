itemsbl_info = {
    'name': 'Gearoenix 3D Blender',
    'author': 'Hossein Noroozpour',
    'version': (3, 0),
    'blender': (2, 7, 5),
    'api': 1,
    'location': 'File > Export',
    'description': 'Export several scene into a Gearoenix 3D file format.',
    'warning': '',
    'wiki_url': '',
    'tracker_url': '',
    'category': 'Import-Export',
}

import collections
import ctypes
import enum
import gc
import io
import math
import os
import subprocess
import sys
import tempfile

import bpy
import bpy_extras
import mathutils


class Gearoenix:

    TYPE_BOOLEAN = ctypes.c_uint8
    TYPE_BYTE = ctypes.c_uint8
    TYPE_FLOAT = ctypes.c_float
    TYPE_U64 = ctypes.c_uint64
    TYPE_U32 = ctypes.c_uint32
    TYPE_U16 = ctypes.c_uint16
    TYPE_U8 = ctypes.c_uint8

    DEBUG_MODE = True

    EPSILON = 0.0001

    ENGINE_GEAROENIX = 0
    ENGINE_VULKUST = 1

    EXPORT_GEAROENIX = False
    EXPORT_VULKUST = False
    EXPORT_FILE_PATH = None

    GX3D_FILE = None
    CPP_FILE = None
    RUST_FILE = None

    BAKED_SKYBOX_CUBE_RES = 1024
    IRRADIANCE_RES = 128
    RADIANCE_RES = 512

    IBL_BAKER_ENVIRONMENT_NAME = 'GEAROENIX_IBL_BAKER'

    last_id = None

    @classmethod
    def register(cls, c):
        exec('cls.' + c.__name__ + ' = c')


@Gearoenix.register
def terminate(*msgs):
    msg = ''
    for m in msgs:
        msg += str(m) + ' '
    print('Fatal error: ' + msg)
    raise Exception(msg)


@Gearoenix.register
def initialize():
    Gearoenix.last_id = 1024
    Gearoenix.GX3D_FILE = open(Gearoenix.EXPORT_FILE_PATH, mode='wb')
    dirstr = os.path.dirname(Gearoenix.EXPORT_FILE_PATH)
    filename = Gearoenix.EXPORT_FILE_PATH[len(dirstr) + 1:]
    p_dir_str = os.path.dirname(dirstr)
    if Gearoenix.EXPORT_VULKUST:
        rs_file = filename.replace('.', '_') + '.rs'
        Gearoenix.RUST_FILE = open(p_dir_str + '/src/' + rs_file, mode='w')
    elif Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE = open(Gearoenix.EXPORT_FILE_PATH + '.hpp', mode='w')
    else:
        Gearoenix.terminate('Unexpected engine selection')


@Gearoenix.register
def log_info(*msgs):
    if Gearoenix.DEBUG_MODE:
        msg = ''
        for m in msgs:
            msg += str(m) + ' '
        print('Info: ' + msg)


@Gearoenix.register
def write_float(f):
    Gearoenix.GX3D_FILE.write(Gearoenix.TYPE_FLOAT(f))


@Gearoenix.register
def write_u64(n):
    Gearoenix.GX3D_FILE.write(Gearoenix.TYPE_U64(n))


@Gearoenix.register
def write_u32(n):
    Gearoenix.GX3D_FILE.write(Gearoenix.TYPE_U32(n))


@Gearoenix.register
def write_u16(n):
    Gearoenix.GX3D_FILE.write(Gearoenix.TYPE_U16(n))


@Gearoenix.register
def write_u8(n):
    Gearoenix.GX3D_FILE.write(Gearoenix.TYPE_U8(n))


@Gearoenix.register
def write_type_id(n):
    Gearoenix.write_u8(n)


@Gearoenix.register
def write_instances_ids(instances):
    Gearoenix.write_u64(len(instances))
    for ins in instances:
        Gearoenix.write_id(ins.my_id)


@Gearoenix.register
def write_id(id):
    Gearoenix.write_u64(id)


@Gearoenix.register
def write_vector(v, element_count=3):
    for i in range(element_count):
        Gearoenix.write_float(v[i])


@Gearoenix.register
def write_matrix(matrix):
    for i in range(0, 4):
        for j in range(0, 4):
            Gearoenix.write_float(matrix[j][i])


@Gearoenix.register
def write_u32_array(arr):
    Gearoenix.write_u64(len(arr))
    for i in arr:
        Gearoenix.write_u32(i)


@Gearoenix.register
def write_u64_array(arr):
    Gearoenix.write_u64(len(arr))
    for i in arr:
        Gearoenix.write_u64(i)


@Gearoenix.register
def write_bool(b):
    data = 0
    if b:
        data = 1
    Gearoenix.GX3D_FILE.write(Gearoenix.TYPE_BOOLEAN(data))


@Gearoenix.register
def write_file_content(name):
    Gearoenix.GX3D_FILE.write(open(name, 'rb').read())


@Gearoenix.register
def file_tell():
    return Gearoenix.GX3D_FILE.tell()


@Gearoenix.register
def limit_check(val, maxval=1.0, minval=0.0, obj=None):
    if val > maxval or val < minval:
        msg = 'Out of range value'
        if obj is not None:
            msg += ', in object: ' + obj.name
        Gearoenix.terminate(msg)


@Gearoenix.register
def uint_check(s):
    try:
        if int(s) >= 0:
            return True
    except ValueError:
        Gearoenix.terminate('Type error')
    Gearoenix.terminate('Type error')


@Gearoenix.register
def get_origin_name(b_obj):
    origin_name = b_obj.name.strip().split('.')
    num_dot = len(origin_name)
    if num_dot > 2 or num_dot < 1:
        Gearoenix.terminate('Wrong name in:', b_obj.name)
    elif num_dot == 1:
        return None
    try:
        int(origin_name[1])
    except:
        Gearoenix.terminate('Wrong name in:', b_obj.name)
    return origin_name[0]


@Gearoenix.register
def is_zero(f):
    return -Gearoenix.EPSILON < f < Gearoenix.EPSILON


@Gearoenix.register
def has_transformation(b_obj):
    m = b_obj.matrix_world
    if b_obj.parent is not None:
        m = b_obj.parent.matrix_world.inverted() @ m
    for i in range(4):
        for j in range(4):
            if i == j:
                if not Gearoenix.is_zero(m[i][j] - 1.0):
                    return True
            elif not Gearoenix.is_zero(m[i][j]):
                return True
    return False


@Gearoenix.register
def write_string(s):
    bs = bytes(s, 'utf-8')
    Gearoenix.write_u64(len(bs))
    for b in bs:
        Gearoenix.write_u8(b)


@Gearoenix.register
def const_string(s):
    ss = s.replace('-', '_')
    ss = ss.replace('/', '_')
    ss = ss.replace('.', '_')
    ss = ss.replace('C:\\', '_')
    ss = ss.replace('c:\\', '_')
    ss = ss.replace('\\', '_')
    ss = ss.upper()
    return ss


@Gearoenix.register
def read_file(f):
    return open(f, 'rb').read()


@Gearoenix.register
def write_file(f):
    Gearoenix.write_u64(len(f))
    Gearoenix.GX3D_FILE.write(f)


@Gearoenix.register
def enum_max_check(e):
    if e == e.MAX:
        Gearoenix.terminate('UNEXPECTED')


@Gearoenix.register
def write_start_module(c):
    mod_name = c.__name__
    if Gearoenix.EXPORT_VULKUST:
        Gearoenix.RUST_FILE.write('#[allow(dead_code)]\n')
        Gearoenix.RUST_FILE.write('#[cfg_attr(debug_assertions, derive(Debug))]\n')
        Gearoenix.RUST_FILE.write('#[repr(u64)]\n')
        Gearoenix.RUST_FILE.write('pub enum ' + mod_name + ' {\n')
        Gearoenix.RUST_FILE.write('    Unexpected = 0,\n')
    elif Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE.write('namespace ' + mod_name + '\n{\n')


@Gearoenix.register
def make_camel_underlined(name):
    camel = ""
    must_up = True
    for c in name:
        if c == '_':
            must_up = True
        elif must_up:
            camel += c.upper()
            must_up = False
        else:
            camel += c.lower()
    return camel


@Gearoenix.register
def write_name_id(name, item_id):
    if Gearoenix.EXPORT_VULKUST:
        Gearoenix.RUST_FILE.write('    ' + Gearoenix.make_camel_underlined(name) + ' = ' + str(int(item_id)) + ',\n')
    elif Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE.write('    const gearoenix::core::Id ' + name + ' = ' + str(item_id) + ';\n')


@Gearoenix.register
def write_end_module():
    if Gearoenix.EXPORT_VULKUST:
        Gearoenix.RUST_FILE.write('}\n\n')
    elif Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE.write('}\n')


@Gearoenix.register
def find_common_starting(s1, s2):
    s = ''
    l = min(len(s1), len(s2))
    for i in range(l):
        if s1[i] == s2[i]:
            s += s1[i]
        else:
            break
    return s


@Gearoenix.register
def find_tools():
    Gearoenix.IBL_BAKER_PATH = os.environ['IBL_BAKER_ENVIRONMENT_NAME']


@Gearoenix.register
def create_sky_resources(file: str):
    baked_cube = Gearoenix.GxTmpFile()
    irradiance = Gearoenix.GxTmpFile()
    radiance = Gearoenix.GxTmpFile()
    subprocess.run([
        Gearoenix.IBL_BAKER_PATH,
        '--environment-file',
        file,
        '--baked-cube-file',
        baked_cube.filename,
        '--baked-cube-resolution',
        Gearoenix.BAKED_SKYBOX_CUBE_RES,
        '--irradiance-file',
        irradiance.filename,
        '--irradiance-resolution',
        Gearoenix.IRRADIANCE_RES,
        '--radiance-file',
        radiance.filename,
        '--radiance-resolution',
        Gearoenix.RADIANCE_RES,
    ])
    return (baked_cube, irradiance, radiance)


@Gearoenix.register
class GxTmpFile:
    def __init__(self):
        tmpfile = tempfile.NamedTemporaryFile(delete=False)
        self.filename = tmpfile.name
        tmpfile.close()

    def __del__(self):
        os.remove(self.filename)

    def read(self):
        f = open(self.filename, 'rb')
        d = f.read()
        f.close()
        return d


@Gearoenix.register
class RenderObject:
    # each instance of this class must define:
    #     my_type    int
    # it will add following fields:
    #     items      dict[name] = instance
    #     name       str
    #     my_id      int
    #     offset     int
    #     b_obj       blender-object

    def __init__(self, b_obj):
        self.offset = 0
        self.b_obj = b_obj
        self.my_id = Gearoenix.last_id
        Gearoenix.last_id += 1
        self.name = self.__class__.get_name_from_b_obj(b_obj)
        if not b_obj.name.startswith(self.__class__.get_prefix()):
            terminate('Unexpected name in ', self.__class__.__name__)
        if self.name in self.__class__.items:
            terminate(self.name, 'is already in items.')
        self.__class__.items[self.name] = self

    @classmethod
    def get_prefix(cls):
        return cls.__name__.lower() + '-'

    def write(self):
        Gearoenix.write_type_id(self.my_type)

    @classmethod
    def write_all(cls):
        items = sorted(cls.items.items(), key=lambda kv: kv[1].my_id)
        for (_, item) in items:
            item.offset = Gearoenix.file_tell()
            item.write()

    @classmethod
    def write_table(cls):
        Gearoenix.write_start_module(cls)
        items = sorted(cls.items.items(), key=lambda kv: kv[1].my_id)
        common_starting = ''
        if len(cls.items) > 1:
            for k in cls.items.keys():
                common_starting = Gearoenix.const_string(k)
                break
        for k in cls.items.keys():
            common_starting = Gearoenix.find_common_starting(
                common_starting, Gearoenix.const_string(k))
        Gearoenix.write_u64(len(items))
        Gearoenix.log_info('Number of', cls.__name__, len(items))
        for _, item in items:
            Gearoenix.write_id(item.my_id)
            Gearoenix.write_u64(item.offset)
            Gearoenix.log_info('  id:', item.my_id, 'offset:', item.offset)
            name = Gearoenix.const_string(item.name)[len(common_starting):]
            Gearoenix.write_name_id(name, item.my_id)
        Gearoenix.write_end_module()

    @staticmethod
    def get_name_from_b_obj(b_obj):
        return b_obj.name

    @classmethod
    def read(cls, b_obj):
        name = cls.get_name_from_b_obj(b_obj)
        if not b_obj.name.startswith(cls.get_prefix()):
            return None
        if name in cls.items:
            return None
        return cls(b_obj)

    @classmethod
    def init(cls):
        cls.items = dict()

    def get_offset(self):
        return self.offset


@Gearoenix.register
class UniRenderObject(Gearoenix.RenderObject):
    # It is going to implement those objects:
    #     Having an origin that their data is is mostly same
    #     Must be kept unique in all object to prevent data redundancy
    # It adds following fields in addition to RenderObject fields:
    #     origin_instance instance

    def __init__(self, b_obj):
        self.origin_instance = None
        origin_name = Gearoenix.get_origin_name(b_obj)
        if origin_name is None:
            return super().__init__(b_obj)
        self.origin_instance = self.__class__.items[origin_name]
        self.name = b_obj.name
        self.my_id = self.origin_instance.my_id
        self.my_type = self.origin_instance.my_type
        self.b_obj = b_obj

    def write(self):
        if self.origin_instance is not None:
            Gearoenix.terminate('This object must not written like this. in', self.name)
        super().write()

    @classmethod
    def read(cls, b_obj):
        if not b_obj.name.startswith(cls.get_prefix()):
            return None
        origin_name = Gearoenix.get_origin_name(b_obj)
        if origin_name is None:
            return super().read(b_obj)
        super().read(bpy.data.objects[origin_name])
        return cls(b_obj)


@Gearoenix.register
class ReferenceableObject(Gearoenix.RenderObject):
    # It is going to implement those objects:
    #     Have a same data in all object
    # It adds following fields in addition to RenderObject fields:
    #     origin_instance instance

    def __init__(self, b_obj):
        self.origin_instance = None
        self.name = self.__class__.get_name_from_b_obj(b_obj)
        if self.name not in self.__class__.items:
            return super().__init__(b_obj)
        self.origin_instance = self.__class__.items[self.name]
        self.my_id = self.origin_instance.my_id
        self.my_type = self.origin_instance.my_type
        self.b_obj = b_obj

    @classmethod
    def read(cls, b_obj):
        if not b_obj.name.startswith(cls.get_prefix()):
            return None
        name = cls.get_name_from_b_obj(b_obj)
        if name not in cls.items:
            return super().read(b_obj)
        return cls(b_obj)

    def write(self):
        if self.origin_instance is not None:
            Gearoenix.terminate('This object must not written like this. in', self.name)
        super().write()

    def get_offset(self):
        if self.origin_instance is None:
            return self.offset
        return self.origin_instance.offset

@Gearoenix.register
class Aabb():
    def __init__(self):
        m = sys.float_info.max
        self.upper = mathutils.Vector((-m, -m, -m))
        self.lower = mathutils.Vector((m, m, m))
    
    def put(self, v):
        if self.upper.x < v.x:
            self.upper.x = v.x
        if self.upper.y < v.y:
            self.upper.y = v.y
        if self.upper.z < v.z:
            self.upper.z = v.z
        if self.lower.x > v.x:
            self.lower.x = v.x
        if self.lower.y > v.y:
            self.lower.y = v.y
        if self.lower.z > v.z:
            self.lower.z = v.z
    
    def write(self):
        Gearoenix.write_vector(self.upper)
        Gearoenix.write_vector(self.lower)
    

@Gearoenix.register
class Audio(Gearoenix.ReferenceableObject):
    TYPE_MUSIC = 1
    TYPE_OBJECT = 2

    @classmethod
    def init(cls):
        super().init()
        cls.MUSIC_PREFIX = cls.get_prefix() + 'music-'
        cls.OBJECT_PREFIX = cls.get_prefix() + 'object-'

    def __init__(self, b_obj):
        super().__init__(b_obj)
        if b_obj.startswith(self.MUSIC_PREFIX):
            self.my_type = self.TYPE_MUSIC
        elif b_obj.startswith(self.OBJECT_PREFIX):
            self.my_type = self.TYPE_OBJECT
        else:
            Gearoenix.terminate('Unspecified type in:', b_obj.name)
        self.file = Gearoenix.read_file(self.name)

    def write(self):
        super().write()
        Gearoenix.write_file(self.file)

    @staticmethod
    def get_name_from_b_obj(b_obj):
        if b_obj.type != 'SPEAKER':
            Gearoenix.terminate('Audio must be speaker: ', b_obj.name)
        aud = b_obj.data
        if aud is None:
            Gearoenix.terminate('Audio is not set in speaker: ', b_obj.name)
        aud = aud.sound
        if aud is None:
            Gearoenix.terminate('Sound is not set in speaker: ', b_obj.name)
        filepath = aud.filepath.strip()
        if filepath is None or len(filepath) == 0:
            Gearoenix.terminate('Audio is not specified yet in speaker: ', b_obj.name)
        if not filepath.endswith('.ogg'):
            Gearoenix.terminate('Use OGG instead of ', filepath)
        return filepath


@Gearoenix.register
class Light(Gearoenix.RenderObject):
    TYPE_CONE = 1
    TYPE_DIRECTIONAL = 2
    TYPE_POINT = 3

    @classmethod
    def init(cls):
        super().init()
        cls.DIRECTIONAL_PREFIX = cls.get_prefix() + 'directional-'
        cls.POINT_PREFIX = cls.get_prefix() + 'point-'
        cls.CONE_PREFIX = cls.get_prefix() + 'cone-'

    def __init__(self, b_obj):
        super().__init__(b_obj)
        if self.b_obj.type != 'LIGHT':
            Gearoenix.terminate('Light type is incorrect:', b_obj.name)
        if b_obj.name.startswith(self.DIRECTIONAL_PREFIX):
            if b_obj.data.type != 'SUN':
                Gearoenix.terminate(b_obj.name, "should be a sun light")
            self.my_type = self.TYPE_DIRECTIONAL
        elif b_obj.name.startswith(self.POINT_PREFIX):
            if b_obj.data.type != 'POINT':
                Gearoenix.terminate(b_obj.name, "should be a point light")
            self.my_type = self.TYPE_POINT
        else:
            Gearoenix.terminate('Unspecified type in:', b_obj.name)

    def write(self):
        super().write()
        color = self.b_obj.data.color
        strength = self.b_obj.data.energy
        Gearoenix.write_float(color[0] * strength)
        Gearoenix.write_float(color[1] * strength)
        Gearoenix.write_float(color[2] * strength)
        Gearoenix.write_bool(self.b_obj.data.use_shadow)
        if self.my_type == self.TYPE_POINT:
            Gearoenix.write_vector(self.b_obj.location)
        elif self.my_type == self.TYPE_DIRECTIONAL:
            v = self.b_obj.matrix_world @ mathutils.Vector((0.0, 0.0, -1.0, 0.0))
            v.normalize()
            Gearoenix.write_vector(v)


@Gearoenix.register
class Camera(Gearoenix.RenderObject):
    TYPE_PERSPECTIVE = 1
    TYPE_ORTHOGRAPHIC = 2

    @classmethod
    def init(cls):
        super().init()
        cls.PERSPECTIVE_PREFIX = cls.get_prefix() + 'perspective-'
        cls.ORTHOGRAPHIC_PREFIX = cls.get_prefix() + 'orthographic-'

    def __init__(self, b_obj):
        super().__init__(b_obj)
        if self.b_obj.type != 'CAMERA':
            Gearoenix.terminate('Camera type is incorrect:', b_obj.name)
        if b_obj.name.startswith(self.PERSPECTIVE_PREFIX):
            self.my_type = self.TYPE_PERSPECTIVE
            if b_obj.data.type != 'PERSP':
                Gearoenix.terminate('Camera type is incorrect:', b_obj.name)
        elif b_obj.name.startswith(self.ORTHOGRAPHIC_PREFIX):
            self.my_type = self.TYPE_ORTHOGRAPHIC
            if b_obj.data.type != 'ORTHO':
                Gearoenix.terminate('Camera type is incorrect:', b_obj.name)
        else:
            Gearoenix.terminate('Unspecified type in:', b_obj.name)

    def write(self):
        super().write()
        cam = self.b_obj.data
        Gearoenix.write_vector(self.b_obj.location)
        Gearoenix.log_info("Camera location is:", 
            str(self.b_obj.location))
        Gearoenix.write_vector(self.b_obj.matrix_world.to_quaternion(), 4)
        Gearoenix.log_info("Camera quaternion is:", 
            str(self.b_obj.matrix_world.to_quaternion()))
        Gearoenix.write_float(cam.clip_start)
        Gearoenix.write_float(cam.clip_end)
        if self.my_type == self.TYPE_PERSPECTIVE:
            Gearoenix.write_float(cam.angle_x)
        elif self.my_type == self.TYPE_ORTHOGRAPHIC:
            Gearoenix.write_float(cam.ortho_scale)
        else:
            Gearoenix.terminate('Unspecified type in:', self.b_obj.name)


@Gearoenix.register
class Constraint(Gearoenix.RenderObject):
    TYPE_PLACER = 1
    TYPE_TRACKER = 2
    TYPE_SPRING = 3
    TYPE_SPRING_JOINT = 4

    @classmethod
    def init(cls):
        super().init()
        cls.PLACER_PREFIX = cls.get_prefix() + 'placer-'

    def __init__(self, b_obj):
        super().__init__(b_obj)
        if b_obj.name.startswith(self.PLACER_PREFIX):
            self.my_type = self.TYPE_PLACER
            self.init_placer()
        else:
            Gearoenix.terminate('Unspecified type in:', b_obj.name)

    def write(self):
        super().write()
        if self.my_type == self.TYPE_PLACER:
            self.write_placer()
        else:
            Gearoenix.terminate('Unspecified type in:', self.b_obj.name)

    def init_placer(self):
        B_TYPE = 'EMPTY'
        DESC = 'Placer constraint'
        ATT_X_MIDDLE = 'x-middle'  # 0
        ATT_Y_MIDDLE = 'y-middle'  # 1
        ATT_X_RIGHT = 'x-right'  # 2
        ATT_X_LEFT = 'x-left'  # 3
        ATT_Y_UP = 'y-up'  # 4
        ATT_Y_DOWN = 'y-down'  # 5
        ATT_RATIO = 'ratio'
        if self.b_obj.type != B_TYPE:
            Gearoenix.terminate(DESC, 'type must be', B_TYPE, 'in object:', self.b_obj.name)
        if len(self.b_obj.children) < 1:
            Gearoenix.terminate(DESC, 'must have more than 0 children, in object:', self.b_obj.name)
        self.model_children = []
        for c in self.b_obj.children:
            ins = Gearoenix.Model.read(c)
            if ins is None:
                Gearoenix.terminate(DESC, 'can only have model as its child, in object:', self.b_obj.name)
            self.model_children.append(ins)
        self.attrs = [None for i in range(6)]
        if ATT_X_MIDDLE in self.b_obj:
            self.check_trans()
            self.attrs[0] = self.b_obj[ATT_X_MIDDLE]
        if ATT_Y_MIDDLE in self.b_obj:
            self.check_trans()
            self.attrs[1] = self.b_obj[ATT_Y_MIDDLE]
        if ATT_X_LEFT in self.b_obj:
            self.attrs[2] = self.b_obj[ATT_X_LEFT]
        if ATT_X_RIGHT in self.b_obj:
            self.attrs[3] = self.b_obj[ATT_X_RIGHT]
        if ATT_Y_UP in self.b_obj:
            self.attrs[4] = self.b_obj[ATT_Y_UP]
        if ATT_Y_DOWN in self.b_obj:
            self.attrs[5] = self.b_obj[ATT_Y_DOWN]
        if ATT_RATIO in self.b_obj:
            self.ratio = self.b_obj[ATT_RATIO]
        else:
            self.ratio = None
        self.placer_type = 0
        for i in range(len(self.attrs)):
            if self.attrs[i] is not None:
                self.placer_type |= (1 << i)
        if self.placer_type not in {4, 8, 33}:
            Gearoenix.terminate(DESC, 'must have meaningful combination, in object:', self.b_obj.name)

    def write_placer(self):
        Gearoenix.write_u64(self.placer_type)
        if self.ratio is not None:
            Gearoenix.write_float(self.ratio)
        if self.placer_type == 4:
            Gearoenix.write_float(self.attrs[2])
        elif self.placer_type == 8:
            Gearoenix.write_float(self.attrs[3])
        elif self.placer_type == 33:
            Gearoenix.write_float(self.attrs[0])
            Gearoenix.write_float(self.attrs[5])
        else:
            Gearoenix.terminate('It is not implemented, in object:', self.b_obj.name)
        childrenids = []
        for c in self.model_children:
            childrenids.append(c.my_id)
        childrenids.sort()
        Gearoenix.write_u64_array(childrenids)

    def check_trans(self):
        if Gearoenix.has_transformation(self.b_obj):
            Gearoenix.terminate('This object should not have any transformation, in:', self.b_obj.name)


@Gearoenix.register
class Collider:
    GHOST = 1
    MESH = 2
    PREFIX = 'collider-'
    CHILDREN = []

    def __init__(self, b_obj=None):
        if b_obj is None:
            if self.MY_TYPE == self.GHOST:
                return
            else:
                Gearoenix.terminate('Unexpected b_obj is None')
        if not b_obj.name.startswith(self.PREFIX):
            Gearoenix.terminate('Collider object name is wrong. In:', b_obj.name)
        self.b_obj = b_obj

    def write(self):
        Gearoenix.write_type_id(self.MY_TYPE)

    @classmethod
    def read(cls, pb_obj):
        collider_object = None
        for b_obj in pb_obj.children:
            for c in cls.CHILDREN:
                if b_obj.name.startswith(c.PREFIX):
                    if collider_object is not None:
                        Gearoenix.terminate('Only one collider is acceptable. In model:', pb_obj.name)
                    collider_object = c(b_obj)
        if collider_object is None:
            return Gearoenix.GhostCollider()
        return collider_object


@Gearoenix.register
class GhostCollider(Gearoenix.Collider):
    MY_TYPE = Gearoenix.Collider.GHOST
    PREFIX = Gearoenix.Collider.PREFIX + 'ghost-'


Gearoenix.Collider.CHILDREN.append(Gearoenix.GhostCollider)


@Gearoenix.register
class MeshCollider(Gearoenix.Collider):
    MY_TYPE = Gearoenix.Collider.MESH
    PREFIX = Gearoenix.Collider.PREFIX + 'mesh-'

    def __init__(self, b_obj):
        super().__init__(b_obj)
        self.b_obj = b_obj
        if b_obj.type != 'MESH':
            Gearoenix.terminate('Mesh collider must have mesh object type, In model:', b_obj.name)
        if has_transformation(b_obj):
            Gearoenix.terminate('Mesh collider can not have any transformation, in:', b_obj.name)
        msh = b_obj.data
        self.indices = []
        self.vertices = msh.vertices
        for p in msh.polygons:
            if len(p.vertices) > 3:
                Gearoenix.terminate('Object', b_obj.name, 'is not triangulated!')
            for i in p.vertices:
                self.indices.append(i)

    def write(self):
        super().write()
        Gearoenix.write_u64(len(self.vertices))
        for v in self.vertices:
            Gearoenix.write_vector(v.co)
        Gearoenix.write_u32_array(self.indices)


Gearoenix.Collider.CHILDREN.append(Gearoenix.MeshCollider)


@Gearoenix.register
class Texture(Gearoenix.ReferenceableObject):
    TYPE_2D = 1
    TYPE_3D = 2
    TYPE_CUBE = 3

    @classmethod
    def init(cls):
        super().init()
        cls.D2_PREFIX = cls.get_prefix() + '2d-'
        cls.D3_PREFIX = cls.get_prefix() + '3d-'
        cls.CUBE_PREFIX = cls.get_prefix() + 'cube-'

    def init_6_face(self):
        extension = self.name[len(self.name) - 4:]
        up_prefix = self.name[:len(self.name) - 4]
        if not up_prefix.endswith('-up'):
            Gearoenix.terminate(
                'Incorrect 6 face texture:', 
                self.b_obj.name,
                'cube texture file name must ends with',
                '-[face-name](up/down/left/right/front/back).[extension]')
        prefix = up_prefix[:len(up_prefix) - 3]
        self.img_up = Gearoenix.read_file(self.name)
        self.img_down = Gearoenix.read_file(prefix + '-down' + extension)
        self.img_left = Gearoenix.read_file(prefix + '-left' + extension)
        self.img_right = Gearoenix.read_file(prefix + '-right' + extension)
        self.img_front = Gearoenix.read_file(prefix + '-front' + extension)
        self.img_back = Gearoenix.read_file(prefix + '-back' + extension)

    def write_6_face(self):
        Gearoenix.write_file(self.img_up)
        Gearoenix.write_file(self.img_down)
        Gearoenix.write_file(self.img_left)
        Gearoenix.write_file(self.img_right)
        Gearoenix.write_file(self.img_front)
        Gearoenix.write_file(self.img_back)

    def __init__(self, b_obj):
        super().__init__(b_obj)
        if b_obj.name.startswith(self.D2_PREFIX):
            self.file = Gearoenix.read_file(self.name)
            self.my_type = self.TYPE_2D
        elif b_obj.name.startswith(self.D3_PREFIX):
            self.file = Gearoenix.read_file(self.name)
            self.my_type = self.TYPE_D3
        elif b_obj.name.startswith(self.CUBE_PREFIX):
            self.init_6_face()
            self.my_type = self.TYPE_CUBE
        else:
            Gearoenix.terminate('Unspecified texture type, in:', b_obj.name)

    def write(self):
        super().write()
        if self.my_type == self.TYPE_2D or self.my_type == self.TYPE_3D:
            Gearoenix.write_file(self.file)
        elif self.my_type == self.TYPE_CUBE:
            self.write_6_face()
        else:
            Gearoenix.terminate('Unspecified texture type, in:', self.b_obj.name)

    @staticmethod
    def get_name_from_b_obj(b_obj):
        if b_obj.type != 'IMAGE':
            Gearoenix.terminate('Unrecognized type for texture')
        filepath = bpy.path.abspath(b_obj.filepath_raw).strip()
        if filepath is None or len(filepath) == 0:
            Gearoenix.terminate('Filepass is empty:', b_obj.name)
        return filepath

    def is_cube(self):
        return self.my_type == self.TYPE_CUBE


@Gearoenix.register
class Font(Gearoenix.ReferenceableObject):
    TYPE_2D = 1
    TYPE_3D = 2

    @classmethod
    def init(cls):
        super().init()
        cls.D2_PREFIX = cls.get_prefix() + '2d-'
        cls.D3_PREFIX = cls.get_prefix() + '3d-'

    def __init__(self, b_obj):
        super().__init__(b_obj)
        if b_obj.name.startswith(self.D2_PREFIX):
            self.my_type = self.TYPE_2D
        elif b_obj.name.startswith(self.D3_PREFIX):
            self.my_type = self.TYPE_3D
        else:
            Gearoenix.terminate('Unspecified font type, in:', b_obj.name)
        self.file = Gearoenix.read_file(self.name)

    def write(self):
        super().write()
        Gearoenix.write_file(self.file)

    @staticmethod
    def get_name_from_b_obj(b_obj):
        filepath = None
        if str(type(b_obj)) == "<class 'bpy.types.VectorFont'>":
            filepath = bpy.path.abspath(b_obj.filepath).strip()
        else:
            Gearoenix.terminate('Unrecognized type for font')
        if filepath is None or len(filepath) == 0:
            Gearoenix.terminate('Filepass is empty:', b_obj.name)
        if not filepath.endswith('.ttf'):
            Gearoenix.terminate('Use TTF for font, in:', filepath)
        return filepath


@Gearoenix.register
class Material:

    FIELD_IS_FLOAT = 1
    FIELD_IS_TEXTURE = 2
    FIELD_IS_VECTOR = 3

    def __init__(self, b_obj):
        self.b_obj = b_obj
        if len(b_obj.material_slots) < 1:
            Gearoenix.terminate('There is no material:', b_obj.name)
        if len(b_obj.material_slots) > 1:
            Gearoenix.terminate('There must be only one material slot:', b_obj.name)
        mat = b_obj.material_slots[0]
        if mat.material is None:
            Gearoenix.terminate('Material does not exist in:', b_obj.name)
        mat = mat.material
        if mat.node_tree is None:
            Gearoenix.terminate('Material node tree does not exist in:', b_obj.name)
        node = mat.node_tree
        NODE_NAME = 'Principled BSDF'
        if NODE_NAME not in node.nodes:
            Gearoenix.terminate('Material', NODE_NAME, 'node does not exist in:', b_obj.name)
        node = node.nodes[NODE_NAME]
        if node is None:
            Gearoenix.terminate('Node is not correct in', b_obj.name)
        inputs = node.inputs
        if inputs is None:
            Gearoenix.terminate('Node inputs are not correct in', b_obj.name)
        def read_links(name):
            if name not in inputs or inputs[name] is None:
                Gearoenix.terminate('Node input', name, 'is not correct in', b_obj.name)
            i = inputs[name]
            if len(i.links) < 1:
                return i.default_value
            elif len(i.links) == 1:
                if i.links[0] is None or i.links[0].from_node is None or i.links[0].from_node.image is None:
                    Gearoenix.terminate('A link can be only a default or a texture link, wrong link in:', b_obj.name, 'link:', i.name)
                img = i.links[0].from_node.image
                txt = Gearoenix.Texture.read(img)
                if txt is None:
                    Gearoenix.terminate('Your texture name is wrong in:', b_obj.name, 'link:', i.name, 'texture:', img.name)
                return txt
            else:
                Gearoenix.terminate('Unexpected number of links in:', b_obj.name, 'link:', i.name)
        self.alpha = read_links('Alpha')
        self.base_color = read_links('Base Color')
        self.emission = read_links('Emission')
        self.metallic = read_links('Metallic')
        self.normal_map = read_links('Normal')
        self.roughness = read_links('Roughness')
        if isinstance(self.alpha, Gearoenix.Texture) and (not isinstance(self.base_color, Gearoenix.Texture) or self.alpha.my_id != self.base_color.my_id):
            Gearoenix.terminate('If "Alpha" is texture then it must point to the texture that "Base Color" is pointing:', b_obj.name)
        if isinstance(self.metallic, Gearoenix.Texture) != isinstance(self.roughness, Gearoenix.Texture):
            Gearoenix.terminate('"Metallic" and "Roughness" must be both scalar or texture:', b_obj.name)
        if isinstance(self.metallic, Gearoenix.Texture) and self.metallic.my_id != self.roughness.my_id:
            Gearoenix.terminate('"Metallic" and "Roughness" must be both pointing to the same texture:', b_obj.name)
        if not mat.use_backface_culling:
            Gearoenix.terminate('Matrial must be only back-face culling enabled in:', b_obj.name)
        if mat.blend_method not in {'CLIP', 'BLEND'}:
            Gearoenix.terminate('"Blend Mode" in material must be set to "Alpha Clip" or "Alpha Blend" in:', b_obj.name)
        self.is_tansparent = mat.blend_method == 'BLEND'
        if mat.shadow_method not in {'CLIP', 'NONE'}:
            Gearoenix.terminate('"Shadow Mode" in material must be set to "Alpha Clip" or "None" in:', b_obj.name)
        self.is_shadow_caster = mat.shadow_method != 'NONE'
        self.alpha_cutoff = mat.alpha_threshold

    def write(self):
        def write_link(l, s = 4):
            if isinstance(l, Gearoenix.Texture):
                Gearoenix.write_bool(True)
                Gearoenix.write_id(l.my_id)
                return
            Gearoenix.write_bool(False)
            if isinstance(l, float):
                Gearoenix.write_float(l)
            elif isinstance(l, bpy.types.bpy_prop_array):
                Gearoenix.write_vector(l, s)
            elif isinstance(l, mathutils.Vector):
                Gearoenix.write_vector(l, s)
            else:
                Gearoenix.terminate('Unexpected type for material input in:', self.b_obj.name)

        
        if isinstance(self.alpha, Gearoenix.Texture):
            Gearoenix.write_bool(True)
        else:
            Gearoenix.write_bool(False)
            Gearoenix.write_float(self.alpha)
        write_link(self.base_color)
        write_link(self.emission, 3)
        if isinstance(self.metallic, Gearoenix.Texture):
            Gearoenix.write_bool(True)
            Gearoenix.write_id(self.metallic.my_id)
        else:
            Gearoenix.write_bool(False)
            Gearoenix.write_float(self.metallic)
            Gearoenix.write_float(self.roughness)
        if isinstance(self.normal_map, Gearoenix.Texture):
            Gearoenix.write_bool(True)
            Gearoenix.write_id(self.normal.my_id)
        else:
            Gearoenix.write_bool(False)
        Gearoenix.write_bool(self.is_tansparent)
        Gearoenix.write_bool(self.is_shadow_caster)
        Gearoenix.write_float(self.alpha_cutoff)

    def has_same_attrs(self, other):
        return True

    def needs_normal(self):
        return True  # todo

    def needs_tangent(self):
        return True  # todo

    def needs_uv(self):
        return True  # todo


@Gearoenix.register
class Mesh(Gearoenix.UniRenderObject):
    TYPE_BASIC = 1

    @classmethod
    def init(cls):
        super().init()
        cls.BASIC_PREFIX = cls.get_prefix() + 'basic-'

    def __init__(self, b_obj):
        super().__init__(b_obj)
        self.box = Gearoenix.Aabb()
        if b_obj.name.startswith(self.BASIC_PREFIX):
            self.my_type = self.TYPE_BASIC
        else:
            Gearoenix.terminate('Unspecified mesh type, in:', b_obj.name)
        if b_obj.type != 'MESH':
            Gearoenix.terminate('Mesh must be of type MESH:', b_obj.name)
        if Gearoenix.has_transformation(b_obj):
            Gearoenix.terminate('Mesh must not have any transformation. in:', b_obj.name)
        if len(b_obj.children) != 0:
            Gearoenix.terminate('Mesh can not have children:', b_obj.name)
        self.mat = Gearoenix.Material(b_obj)
        if self.origin_instance is not None:
            if not self.mat.has_same_attrs(self.origin_instance.mat):
                Gearoenix.terminate('Different mesh attributes, in: ' + b_obj.name)
            return
        if b_obj.parent is not None:
            Gearoenix.terminate('Origin mesh can not have parent:', b_obj.name)
        msh = b_obj.data
        msh.calc_normals_split()
        msh.calc_tangents()
        nrm = self.mat.needs_normal()
        tng = self.mat.needs_tangent()
        uv = self.mat.needs_uv()
        vertices = dict()
        last_index = 0
        for p in msh.polygons:
            if len(p.vertices) > 3:
                Gearoenix.terminate('Object', b_obj.name, 'is not triangulated!')
            for i, li in zip(p.vertices, p.loop_indices):
                vertex = []
                v = msh.vertices[i].co
                self.box.put(v)
                vertex.append(v[0])
                vertex.append(v[1])
                vertex.append(v[2])
                if nrm:
                    normal = msh.loops[li].normal.normalized()
                    # Gearoenix.log_info(str(normal))
                    vertex.append(normal[0])
                    vertex.append(normal[1])
                    vertex.append(normal[2])
                if tng:
                    tangent = msh.loops[li].tangent.normalized()
                    # Gearoenix.log_info(str(tangent))
                    vertex.append(tangent[0])
                    vertex.append(tangent[1])
                    vertex.append(tangent[2])
                    vertex.append(msh.loops[li].bitangent_sign)
                if uv:
                    uv_leyers = msh.uv_layers
                    if len(uv_leyers) > 1 or len(uv_leyers) < 1:
                        Gearoenix.terminate('Unexpected number of uv layers in', b_obj.name)
                    tex_co = uv_leyers.active.data[li].uv
                    vertex.append(tex_co[0])
                    vertex.append(1.0 - tex_co[1])
                vertex = tuple(vertex)
                if vertex in vertices:
                    vertices[vertex].append(last_index)
                else:
                    vertices[vertex] = [last_index]
                last_index += 1
        self.indices = [0 for _ in range(last_index)]
        self.vertices = []
        last_index = 0
        for vertex, index_list in vertices.items():
            self.vertices.append(vertex)
            for i in index_list:
                self.indices[i] = last_index
            last_index += 1

    def write(self):
        super().write()
        Gearoenix.write_u64(len(self.vertices))
        for vertex in self.vertices:
            for e in vertex:
                Gearoenix.write_float(e)
        Gearoenix.write_u32_array(self.indices)
        self.box.write()


@Gearoenix.register
class Model(Gearoenix.RenderObject):
    TYPE_DYNAMIC = 1
    TYPE_STATIC = 2
    TYPE_WIDGET = 3
    # TYPES OF WIDGET
    TYPE_BUTTON = 1
    TYPE_EDIT = 2
    TYPE_TEXT = 3

    @classmethod
    def init(cls):
        super().init()
        cls.DYNAMIC_PREFIX = cls.get_prefix() + 'dynamic-'
        cls.STATIC_PREFIX = cls.get_prefix() + 'static-'
        cls.WIDGET_PREFIX = cls.get_prefix() + 'widget-'
        cls.BUTTON_PREFIX = cls.WIDGET_PREFIX + 'button-'
        cls.EDIT_PREFIX = cls.WIDGET_PREFIX + 'edit-'
        cls.TEXT_PREFIX = cls.WIDGET_PREFIX + 'text-'

    def init_widget(self):
        if self.b_obj.name.startswith(self.BUTTON_PREFIX):
            self.widget_type = self.TYPE_BUTTON
        elif self.b_obj.name.startswith(self.TEXT_PREFIX):
            self.widget_type = self.TYPE_TEXT
        elif self.b_obj.name.startswith(self.EDIT_PREFIX):
            self.widget_type = self.TYPE_EDIT
        else:
            Gearoenix.terminate('Unrecognized widget type:', self.b_obj.name)
        if self.widget_type == self.TYPE_EDIT or \
                self.widget_type == self.TYPE_TEXT:
            self.text = self.b_obj.data.body.strip()
            b_font = self.b_obj.data.font
            if b_font is None:
                Gearoenix.terminate('Font is none in:', self.b_obj.name)
            self.font = Gearoenix.Font.read(b_font)
            if self.font is None:
                Gearoenix.terminate('Font is incorrect in:', self.b_obj.name, 'font:', b_font.name)
            align_x = self.b_obj.data.align_x
            align_y = self.b_obj.data.align_y
            self.align = 0
            if align_x == 'LEFT':
                self.align += 3
            elif align_x == 'CENTER':
                self.align += 0
            elif align_x == 'RIGHT':
                self.align += 6
            else:
                Gearoenix.terminate('Unrecognized text horizontal alignment, in:', self.b_obj.name)
            if align_y == 'TOP':
                self.align += 3
            elif align_y == 'CENTER':
                self.align += 2
            elif align_y == 'BOTTOM':
                self.align += 1
            else:
                Gearoenix.terminate('Unrecognized text vertical alignment, in:', self.b_obj.name)
            self.font_mat = Gearoenix.Material(self.b_obj)
            self.font_space_character = self.b_obj.data.space_character - 1.0
            self.font_space_word = self.b_obj.data.space_word - 1.0
            self.font_space_line = self.b_obj.data.space_line

    def __init__(self, b_obj):
        super().__init__(b_obj)
        self.matrix = b_obj.matrix_world
        self.meshes = []
        self.model_children = []
        self.collider = Gearoenix.Collider.read(b_obj)
        for c in b_obj.children:
            ins = Gearoenix.Mesh.read(c)
            if ins is not None:
                self.meshes.append(ins)
                continue
            ins = Gearoenix.Model.read(c)
            if ins is not None:
                self.model_children.append(ins)
                continue
        if len(self.model_children) + len(self.meshes) < 1 and not b_obj.name.startswith(self.TEXT_PREFIX):
            Gearoenix.terminate('Waste model', b_obj.name)
        if b_obj.name.startswith(self.DYNAMIC_PREFIX):
            self.my_type = self.TYPE_DYNAMIC
        elif b_obj.name.startswith(self.STATIC_PREFIX):
            self.my_type = self.TYPE_STATIC
        elif b_obj.name.startswith(self.WIDGET_PREFIX):
            self.my_type = self.TYPE_WIDGET
            self.init_widget()
        else:
            Gearoenix.terminate('Unspecified model type, in:', b_obj.name)

    def write_widget(self):
        if self.widget_type == self.TYPE_TEXT or\
                self.widget_type == self.TYPE_EDIT:
            Gearoenix.write_string(self.text)
            Gearoenix.write_u8(self.align)
            Gearoenix.write_id(self.font.my_id)
            self.font_mat.write()

    def write(self):
        super().write()
        if self.my_type == self.TYPE_WIDGET:
            Gearoenix.write_u64(self.widget_type)
        Gearoenix.write_matrix(self.b_obj.matrix_world)
        # self.collider.write()
        Gearoenix.write_u64(len(self.meshes))
        for m in self.meshes:
            Gearoenix.write_id(m.my_id)
            m.mat.write()
        if self.my_type == self.TYPE_WIDGET:
            self.write_widget()
        Gearoenix.write_instances_ids(self.model_children)


@Gearoenix.register
class Skybox(Gearoenix.RenderObject):
    TYPE_CUBE = 1
    TYPE_EQUIRECTANGULAR = 2
    
    @classmethod
    def init(cls):
        super().init()
        # for future
        cls.CUBE_PREFIX = cls.get_prefix() + 'cube-'
        cls.EQUIRECTANGULAR_PREFIX = cls.get_prefix() + 'equirectangular-'

    def __init__(self, b_obj):
        super().__init__(b_obj)
        if b_obj.name.startswith(self.CUBE_PREFIX):
            self.my_type = self.TYPE_CUBE
        elif b_obj.name.startswith(self.EQUIRECTANGULAR_PREFIX):
            self.my_type = self.TYPE_EQUIRECTANGULAR
        else:
            Gearoenix.terminate('Unspecified skybox type, in:', b_obj.name)
        image = b_obj.material_slots[0].material.node_tree.nodes['Principled BSDF']
        image = image.inputs['Base Color'].links[0].from_node.image
        if self.TYPE_EQUIRECTANGULAR == self.my_type:
            self.image_file = bpy.path.abspath(image.filepath).strip()
        elif self.TYPE_CUBE == self.my_type:
            self.texture = Gearoenix.Texture.read(image)
            if self.texture is None:
                Gearoenix.terminate('texture not found for skybox:', b_obj.name)
            if not self.texture.is_cube():
                Gearoenix.terminate('texture must be cube for skybox:', b_obj.name)

    def write(self):
        super().write()
        if self.TYPE_EQUIRECTANGULAR == self.my_type:
            (env, irr, rad) = Gearoenix.create_sky_resources(self.image_file)
            Gearoenix.write_file_content(env.filename)
            Gearoenix.write_file_content(irr.filename)
            Gearoenix.write_file_content(rad.filename)
        elif self.TYPE_CUBE == self.my_type:
            Gearoenix.write_id(self.texture.my_id)


@Gearoenix.register
class Scene(Gearoenix.RenderObject):
    TYPE_GAME = 1
    TYPE_UI = 2

    @classmethod
    def init(cls):
        super().init()
        cls.GAME_PREFIX = cls.get_prefix() + 'game-'
        cls.UI_PREFIX = cls.get_prefix() + 'ui-'

    def __init__(self, b_obj):
        super().__init__(b_obj)
        self.models = []
        self.skybox = None
        self.cameras = []
        self.lights = []
        self.audios = []
        self.constraints = []
        for o in b_obj.objects:
            if o.parent is not None:
                continue
            ins = Gearoenix.Model.read(o)
            if ins is not None:
                self.models.append(ins)
                continue
            ins = Gearoenix.Skybox.read(o)
            if ins is not None:
                if self.skybox is not None:
                    Gearoenix.terminate('Only one skybox is acceptable in a scene, wrong scene is: ', b_obj.name)
                self.skybox = ins
                continue
            ins = Gearoenix.Camera.read(o)
            if ins is not None:
                self.cameras.append(ins)
                continue
            ins = Gearoenix.Light.read(o)
            if ins is not None:
                self.lights.append(ins)
                continue
            ins = Gearoenix.Audio.read(o)
            if ins is not None:
                self.audios.append(ins)
                continue
            ins = Gearoenix.Constraint.read(o)
            if ins is not None:
                self.constraints.append(ins)
                continue
        if b_obj.name.startswith(self.GAME_PREFIX):
            self.my_type = self.TYPE_GAME
        elif b_obj.name.startswith(self.UI_PREFIX):
            self.my_type = self.TYPE_UI
        else:
            Gearoenix.terminate('Unspecified scene type, in:', b_obj.name)
        if len(self.cameras) < 1:
            Gearoenix.terminate('Scene must have at least one camera, in:', b_obj.name)
        if len(self.lights) < 1:
            Gearoenix.terminate('Scene must have at least one light, in:', b_obj.name)
        self.boundary_left = None
        if 'left' in b_obj:
            self.boundary_left = b_obj['left']  # todo it must be calculated, remove it
            self.boundary_right = b_obj['right']  # todo it must be calculated, remove it
            self.boundary_up = b_obj['up']  # todo it must be calculated, remove it
            self.boundary_down = b_obj['down']  # todo it must be calculated, remove it
            self.boundary_front = b_obj['front']  # todo it must be calculated, remove it
            self.boundary_back = b_obj['back']  # todo it must be calculated, remove it
            self.grid_x_count = int(b_obj['x-grid-count'])
            self.grid_y_count = int(b_obj['y-grid-count'])
            self.grid_z_count = int(b_obj['z-grid-count'])

    def write(self):
        super().write()
        Gearoenix.write_instances_ids(self.cameras)
        Gearoenix.write_instances_ids(self.audios)
        Gearoenix.write_instances_ids(self.lights)
        Gearoenix.write_instances_ids(self.models)
        Gearoenix.write_bool(self.skybox is not None)
        if self.skybox is not None:
            Gearoenix.write_id(self.skybox.my_id)
        Gearoenix.write_instances_ids(self.constraints)
        Gearoenix.write_bool(self.boundary_left is not None)
        if self.boundary_left is not None:
            Gearoenix.write_float(self.boundary_up)
            Gearoenix.write_float(self.boundary_down)
            Gearoenix.write_float(self.boundary_left)
            Gearoenix.write_float(self.boundary_right)
            Gearoenix.write_float(self.boundary_front)
            Gearoenix.write_float(self.boundary_back)
            Gearoenix.write_u16(self.grid_x_count)
            Gearoenix.write_u16(self.grid_y_count)
            Gearoenix.write_u16(self.grid_z_count)

    @classmethod
    def read_all(cls):
        for s in bpy.data.scenes:
            super().read(s)


@Gearoenix.register
def write_tables():
    Gearoenix.Camera.write_table()
    Gearoenix.Audio.write_table()
    Gearoenix.Light.write_table()
    Gearoenix.Texture.write_table()
    Gearoenix.Font.write_table()
    Gearoenix.Mesh.write_table()
    Gearoenix.Model.write_table()
    Gearoenix.Skybox.write_table()
    Gearoenix.Constraint.write_table()
    Gearoenix.Scene.write_table()


@Gearoenix.register
def export_files():
    Gearoenix.initialize()
    Gearoenix.Audio.init()
    Gearoenix.Light.init()
    Gearoenix.Camera.init()
    Gearoenix.Texture.init()
    Gearoenix.Font.init()
    Gearoenix.Mesh.init()
    Gearoenix.Model.init()
    Gearoenix.Skybox.init()
    Gearoenix.Constraint.init()
    Gearoenix.Scene.init()
    Gearoenix.Scene.read_all()
    Gearoenix.write_bool(sys.byteorder == 'little')
    Gearoenix.write_id(Gearoenix.last_id)
    Gearoenix.tables_offset = Gearoenix.file_tell()
    Gearoenix.write_tables()
    Gearoenix.Camera.write_all()
    Gearoenix.Audio.write_all()
    Gearoenix.Light.write_all()
    Gearoenix.Texture.write_all()
    Gearoenix.Font.write_all()
    Gearoenix.Mesh.write_all()
    Gearoenix.Model.write_all()
    Gearoenix.Skybox.write_all()
    Gearoenix.Constraint.write_all()
    Gearoenix.Scene.write_all()
    Gearoenix.GX3D_FILE.flush()
    if Gearoenix.EXPORT_VULKUST:
        Gearoenix.RUST_FILE.flush()
    if Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE.flush()
    Gearoenix.GX3D_FILE.seek(Gearoenix.tables_offset)
    if Gearoenix.EXPORT_VULKUST:
        Gearoenix.RUST_FILE.seek(0)
    if Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE.seek(0)
    Gearoenix.write_tables()
    Gearoenix.GX3D_FILE.flush()
    Gearoenix.GX3D_FILE.close()
    if Gearoenix.EXPORT_VULKUST:
        Gearoenix.RUST_FILE.flush()
        Gearoenix.RUST_FILE.close()
    if Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE.flush()
        Gearoenix.CPP_FILE.close()
    gc.collect()


@Gearoenix.register
class Exporter(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    'This is a plug in for Gearoenix 3D file format'
    bl_idname = 'gearoenix_exporter.data_structure'
    bl_label = 'Export Gearoenix 3D'
    filename_ext = '.gx3d'
    filter_glob: bpy.props.StringProperty(
        default='*.gx3d',
        options={'HIDDEN'},
    )
    export_engine: bpy.props.EnumProperty(
        name='Game engine',
        description='This item select the game engine',
        items=(
            (str(Gearoenix.ENGINE_VULKUST), 'Vulkust', ''),
            (str(Gearoenix.ENGINE_GEAROENIX), 'Gearoenix', ''),
        ),
    )

    def execute(self, context):
        engine = int(self.export_engine)
        if engine == Gearoenix.ENGINE_GEAROENIX:
            Gearoenix.EXPORT_GEAROENIX = True
            Gearoenix.EXPORT_VULKUST = False
            Gearoenix.log_info('Exporting for Gearoenix engine')
        elif engine == Gearoenix.ENGINE_VULKUST:
            Gearoenix.EXPORT_VULKUST = True
            Gearoenix.EXPORT_GEAROENIX = False
            Gearoenix.log_info('Exporting for Vulkust engine')
        else:
            Gearoenix.terminate('Unexpected export engine')
        Gearoenix.EXPORT_FILE_PATH = self.filepath
        Gearoenix.find_tools()
        Gearoenix.export_files()
        return {'FINISHED'}


@Gearoenix.register
def menu_func_export(self, context):
    self.layout.operator(
        Gearoenix.Exporter.bl_idname, text='Gearoenix 3D Exporter (.gx3d)')


@Gearoenix.register
def register_plugin():
    bpy.utils.register_class(Gearoenix.Exporter)
    bpy.types.TOPBAR_MT_file_export.append(Gearoenix.menu_func_export)


if __name__ == '__main__':
    Gearoenix.register_plugin()
