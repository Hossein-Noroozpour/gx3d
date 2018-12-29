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

    last_id = 1024

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
def initialize_pathes():
    Gearoenix.GX3D_FILE = open(Gearoenix.EXPORT_FILE_PATH, mode='wb')
    dirstr = os.path.dirname(Gearoenix.EXPORT_FILE_PATH)
    filename = Gearoenix.EXPORT_FILE_PATH[len(dirstr) + 1:]
    pdirstr = os.path.dirname(dirstr)
    if Gearoenix.EXPORT_VULKUST:
        rsfile = filename.replace('.', '_') + '.rs'
        Gearoenix.RUST_FILE = open(pdirstr + '/src/' + rsfile, mode='w')
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
def write_instances_ids(inss):
    Gearoenix.write_u64(len(inss))
    for ins in inss:
        Gearoenix.write_u64(ins.my_id)


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
def get_origin_name(bobj):
    origin_name = bobj.name.strip().split('.')
    num_dot = len(origin_name)
    if num_dot > 2 or num_dot < 1:
        Gearoenix.terminate('Wrong name in:', bobj.name)
    elif num_dot == 1:
        return None
    try:
        int(origin_name[1])
    except:
        Gearoenix.terminate('Wrong name in:', bobj.name)
    return origin_name[0]


@Gearoenix.register
def is_zero(f):
    return -Gearoenix.EPSILON < f < Gearoenix.EPSILON


@Gearoenix.register
def has_transformation(bobj):
    m = bobj.matrix_world
    if bobj.parent is not None:
        m = bobj.parent.matrix_world.inverted() * m
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
        Gearoenix.RUST_FILE.write('#[cfg_attr(debug_assertions, derive(Debug))]\n')
        Gearoenix.RUST_FILE.write('#[repr(u64)]\n')
        Gearoenix.RUST_FILE.write('pub enum ' + mod_name + ' {\n')
        Gearoenix.RUST_FILE.write('    Unexpected = 0,\n')
    elif Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE.write('namespace ' + mod_name + '\n{\n')


@Gearoenix.register
def camelize_underlined(name):
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
        Gearoenix.RUST_FILE.write('    ' + Gearoenix.camelize_underlined(name) + ' = ' + str(int(item_id)) + ',\n')
    elif Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE.write('    const gearoenix::core::Id ' + name + ' = ' + str(item_id) + ';\n')


@Gearoenix.register
def write_end_modul():
    if Gearoenix.EXPORT_VULKUST:
        Gearoenix.RUST_FILE.write('}\n')
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
    # it will add following fiels:
    #     items      dict[name] = instance
    #     name       str
    #     my_id      int
    #     offset     int
    #     bobj       blender-object

    def __init__(self, bobj):
        self.offset = 0
        self.bobj = bobj
        self.my_id = Gearoenix.last_id
        Gearoenix.last_id += 1
        self.name = self.__class__.get_name_from_bobj(bobj)
        if not bobj.name.startswith(self.__class__.get_prefix()):
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
            Gearoenix.write_u64(item.my_id)
            Gearoenix.write_u64(item.offset)
            Gearoenix.log_info('  id:', item.my_id, 'offset:', item.offset)
            name = Gearoenix.const_string(item.name)[len(common_starting):]
            Gearoenix.write_name_id(name, item.my_id)
        Gearoenix.write_end_modul()

    @staticmethod
    def get_name_from_bobj(bobj):
        return bobj.name

    @classmethod
    def read(cls, bobj):
        name = cls.get_name_from_bobj(bobj)
        if not bobj.name.startswith(cls.get_prefix()):
            return None
        if name in cls.items:
            return None
        return cls(bobj)

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

    def __init__(self, bobj):
        self.origin_instance = None
        origin_name = Gearoenix.get_origin_name(bobj)
        if origin_name is None:
            return super().__init__(bobj)
        self.origin_instance = self.__class__.items[origin_name]
        self.name = bobj.name
        self.my_id = self.origin_instance.my_id
        self.my_type = self.origin_instance.my_type
        self.bobj = bobj

    def write(self):
        if self.origin_instance is not None:
            Gearoenix.terminate('This object must not written like this. in', self.name)
        super().write()

    @classmethod
    def read(cls, bobj):
        if not bobj.name.startswith(cls.get_prefix()):
            return None
        origin_name = Gearoenix.get_origin_name(bobj)
        if origin_name is None:
            return super().read(bobj)
        super().read(bpy.data.objects[origin_name])
        return cls(bobj)


@Gearoenix.register
class ReferenceableObject(Gearoenix.RenderObject):
    # It is going to implement those objects:
    #     Have a same data in all object
    # It adds following fields in addition to RenderObject fields:
    #     origin_instance instance

    def __init__(self, bobj):
        self.origin_instance = None
        self.name = self.__class__.get_name_from_bobj(bobj)
        if self.name not in self.__class__.items:
            return super().__init__(bobj)
        self.origin_instance = self.__class__.items[self.name]
        self.my_id = self.origin_instance.my_id
        self.my_type = self.origin_instance.my_type
        self.bobj = bobj

    @classmethod
    def read(cls, bobj):
        if not bobj.name.startswith(cls.get_prefix()):
            return None
        name = cls.get_name_from_bobj(bobj)
        if name not in cls.items:
            return super().read(bobj)
        return cls(bobj)

    def write(self):
        if self.origin_instance is not None:
            Gearoenix.terminate('This object must not written like this. in', self.name)
        super().write()

    def get_offset(self):
        if self.origin_instance is None:
            return self.offset
        return self.origin_instance.offset


@Gearoenix.register
class Audio(Gearoenix.ReferenceableObject):
    TYPE_MUSIC = 1
    TYPE_OBJECT = 2

    @classmethod
    def init(cls):
        super().init()
        cls.MUSIC_PREFIX = cls.get_prefix() + 'music-'
        cls.OBJECT_PREFIX = cls.get_prefix() + 'object-'

    def __init__(self, bobj):
        super().__init__(bobj)
        if bobj.startswith(self.MUSIC_PREFIX):
            self.my_type = self.TYPE_MUSIC
        elif bobj.startswith(self.OBJECT_PREFIX):
            self.my_type = self.TYPE_OBJECT
        else:
            Gearoenix.terminate('Unspecified type in:', bobj.name)
        self.file = read_file(self.name)

    def write(self):
        super().write()
        Gearoenix.write_file(self.file)

    @staticmethod
    def get_name_from_bobj(bobj):
        if bobj.type != 'SPEAKER':
            Gearoenix.terminate('Audio must be speaker: ', bobj.name)
        aud = bobj.data
        if aud is None:
            Gearoenix.terminate('Audio is not set in speaker: ', bobj.name)
        aud = aud.sound
        if aud is None:
            Gearoenix.terminate('Sound is not set in speaker: ', bobj.name)
        filepath = aud.filepath.strip()
        if filepath is None or len(filepath) == 0:
            Gearoenix.terminate('Audio is not specified yet in speaker: ', bobj.name)
        if not filepath.endswith('.ogg'):
            Gearoenix.terminate('Use OGG instead of ', filepath)
        return filepath


@Gearoenix.register
class Light(Gearoenix.RenderObject):
    TYPE_SUN = 1
    TYPE_POINT = 2
    TYPE_CONE = 3

    @classmethod
    def init(cls):
        super().init()
        cls.SUN_PREFIX = cls.get_prefix() + 'sun-'
        cls.POINT_PREFIX = cls.get_prefix() + 'point-'
        cls.CONE_PREFIX = cls.get_prefix() + 'cone-'

    def __init__(self, bobj):
        super().__init__(bobj)
        if self.bobj.type != 'LAMP':
            Gearoenix.terminate('Light type is incorrect:', bobj.name)
        if bobj.name.startswith(self.SUN_PREFIX):
            if bobj.data.type != 'SUN':
                Gearoenix.terminate(bobj.name, "should be a sun light")
            self.my_type = self.TYPE_SUN
        elif bobj.name.startswith(self.POINT_PREFIX):
            if bobj.data.type != 'POINT':
                Gearoenix.terminate(bobj.name, "should be a point light")
            self.my_type = self.TYPE_POINT
        else:
            Gearoenix.terminate('Unspecified type in:', bobj.name)

    def write(self):
        super().write()
        Gearoenix.write_bool(self.bobj.data.cycles.cast_shadow)
        if self.my_type == self.TYPE_POINT:
            Gearoenix.write_vector(self.bobj.location)
        elif self.my_type == self.TYPE_SUN:
            Gearoenix.write_vector(self.bobj.matrix_world.to_quaternion(), 4)
        inputs = self.bobj.data.node_tree.nodes['Emission'].inputs
        Gearoenix.write_vector(inputs['Color'].default_value)
        Gearoenix.write_float(inputs['Strength'].default_value)


@Gearoenix.register
class Camera(Gearoenix.RenderObject):
    TYPE_PERSPECTIVE = 1
    TYPE_ORTHOGRAPHIC = 2

    @classmethod
    def init(cls):
        super().init()
        cls.PERSPECTIVE_PREFIX = cls.get_prefix() + 'perspective-'
        cls.ORTHOGRAPHIC_PREFIX = cls.get_prefix() + 'orthographic-'

    def __init__(self, bobj):
        super().__init__(bobj)
        if self.bobj.type != 'CAMERA':
            Gearoenix.terminate('Camera type is incorrect:', bobj.name)
        if bobj.name.startswith(self.PERSPECTIVE_PREFIX):
            self.my_type = self.TYPE_PERSPECTIVE
            if bobj.data.type != 'PERSP':
                Gearoenix.terminate('Camera type is incorrect:', bobj.name)
        elif bobj.name.startswith(self.ORTHOGRAPHIC_PREFIX):
            self.my_type = self.TYPE_ORTHOGRAPHIC
            if bobj.data.type != 'ORTHO':
                Gearoenix.terminate('Camera type is incorrect:', bobj.name)
        else:
            Gearoenix.terminate('Unspecified type in:', bobj.name)

    def write(self):
        super().write()
        cam = self.bobj.data
        Gearoenix.write_vector(self.bobj.location)
        Gearoenix.log_info("Camera location is:", 
            str(self.bobj.location))
        Gearoenix.write_vector(self.bobj.matrix_world.to_quaternion(), 4)
        Gearoenix.log_info("Camera quaternion is:", 
            str(self.bobj.matrix_world.to_quaternion()))
        Gearoenix.write_float(cam.clip_start)
        Gearoenix.write_float(cam.clip_end)
        if self.my_type == self.TYPE_PERSPECTIVE:
            Gearoenix.write_float(cam.angle_x)
        elif self.my_type == self.TYPE_ORTHOGRAPHIC:
            Gearoenix.write_float(cam.ortho_scale)
        else:
            Gearoenix.terminate('Unspecified type in:', bobj.name)


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

    def __init__(self, bobj):
        super().__init__(bobj)
        if bobj.name.startswith(self.PLACER_PREFIX):
            self.my_type = self.TYPE_PLACER
            self.init_placer()
        else:
            Gearoenix.terminate('Unspecified type in:', bobj.name)

    def write(self):
        super().write()
        if self.my_type == self.TYPE_PLACER:
            self.write_placer()
        else:
            Gearoenix.terminate('Unspecified type in:', bobj.name)

    def init_placer(self):
        BTYPE = 'EMPTY'
        DESC = 'Placer constraint'
        ATT_X_MIDDLE = 'x-middle'  # 0
        ATT_Y_MIDDLE = 'y-middle'  # 1
        ATT_X_RIGHT = 'x-right'  # 2
        ATT_X_LEFT = 'x-left'  # 3
        ATT_Y_UP = 'y-up'  # 4
        ATT_Y_DOWN = 'y-down'  # 5
        ATT_RATIO = 'ratio'
        if self.bobj.type != BTYPE:
            Gearoenix.terminate(DESC, 'type must be', BTYPE, 'in object:', self.bobj.name)
        if len(self.bobj.children) < 1:
            Gearoenix.terminate(DESC, 'must have more than 0 children, in object:', self.bobj.name)
        self.model_children = []
        for c in self.bobj.children:
            ins = Gearoenix.Model.read(c)
            if ins is None:
                Gearoenix.terminate(DESC, 'can only have model as its child, in object:', self.bobj.name)
            self.model_children.append(ins)
        self.attrs = [None for i in range(6)]
        if ATT_X_MIDDLE in self.bobj:
            self.check_trans()
            self.attrs[0] = self.bobj[ATT_X_MIDDLE]
        if ATT_Y_MIDDLE in self.bobj:
            self.check_trans()
            self.attrs[1] = self.bobj[ATT_Y_MIDDLE]
        if ATT_X_LEFT in self.bobj:
            self.attrs[2] = self.bobj[ATT_X_LEFT]
        if ATT_X_RIGHT in self.bobj:
            self.attrs[3] = self.bobj[ATT_X_RIGHT]
        if ATT_Y_UP in self.bobj:
            self.attrs[4] = self.bobj[ATT_Y_UP]
        if ATT_Y_DOWN in self.bobj:
            self.attrs[5] = self.bobj[ATT_Y_DOWN]
        if ATT_RATIO in self.bobj:
            self.ratio = self.bobj[ATT_RATIO]
        else:
            self.ratio = None
        self.placer_type = 0
        for i in range(len(self.attrs)):
            if self.attrs[i] is not None:
                self.placer_type |= (1 << i)
        if self.placer_type not in {4, 8, 33}:
            Gearoenix.terminate(DESC, 'must have meaningful combination, in object:', self.bobj.name)

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
            Gearoenix.terminate('It is not implemented, in object:', self.bobj.name)
        childrenids = []
        for c in self.model_children:
            childrenids.append(c.my_id)
        childrenids.sort()
        Gearoenix.write_u64_array(childrenids)

    def check_trans(self):
        if Gearoenix.has_transformation(self.bobj):
            Gearoenix.terminate('This object should not have any transformation, in:', self.bobj.name)


@Gearoenix.register
class Collider:
    GHOST = 1
    MESH = 2
    PREFIX = 'collider-'
    CHILDREN = []

    def __init__(self, bobj=None):
        if bobj is None:
            if self.MY_TYPE == self.GHOST:
                return
            else:
                Gearoenix.terminate('Unexpected bobj is None')
        if not bobj.name.startswith(self.PREFIX):
            Gearoenix.terminate('Collider object name is wrong. In:', bobj.name)
        self.bobj = bobj

    def write(self):
        Gearoenix.write_type_id(self.MY_TYPE)

    @classmethod
    def read(cls, pbobj):
        collider_object = None
        for bobj in pbobj.children:
            for c in cls.CHILDREN:
                if bobj.name.startswith(c.PREFIX):
                    if collider_object is not None:
                        Gearoenix.terminate('Only one collider is acceptable. In model:', pbobj.name)
                    collider_object = c(bobj)
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

    def __init__(self, bobj):
        super().__init__(bobj)
        self.bobj = bobj
        if bobj.type != 'MESH':
            Gearoenix.terminate('Mesh collider must have mesh object type, In model:', bobj.name)
        if has_transformation(bobj):
            Gearoenix.terminate('Mesh collider can not have any transformation, in:', bobj.name)
        msh = bobj.data
        self.indices = []
        self.vertices = msh.vertices
        for p in msh.polygons:
            if len(p.vertices) > 3:
                Gearoenix.terminate('Object', bobj.name, 'is not triangled!')
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
        prefix = self.CUBE_PREFIX
        up_prefix = prefix + 'up-'
        if not self.name.startswith(up_prefix):
            Gearoenix.terminate('Incorrect 6 face texture:', self.bobj.name)
        base_name = self.name[len(up_prefix):]
        self.img_up = Gearoenix.read_file(self.name)
        self.img_down = Gearoenix.read_file(prefix + 'down-' + base_name)
        self.img_left = Gearoenix.read_file(prefix + 'left-' + base_name)
        self.img_right = Gearoenix.read_file(prefix + 'right-' + base_name)
        self.img_front = Gearoenix.read_file(prefix + 'front-' + base_name)
        self.img_back = Gearoenix.read_file(prefix + 'back-' + base_name)

    def write_6_face(self):
        Gearoenix.write_file(self.img_up)
        Gearoenix.write_file(self.img_down)
        Gearoenix.write_file(self.img_left)
        Gearoenix.write_file(self.img_right)
        Gearoenix.write_file(self.img_front)
        Gearoenix.write_file(self.img_back)

    def __init__(self, bobj):
        super().__init__(bobj)
        if bobj.name.startswith(self.D2_PREFIX):
            self.file = Gearoenix.read_file(self.name)
            self.my_type = self.TYPE_2D
        elif bobj.name.startswith(self.D3_PREFIX):
            self.file = Gearoenix.read_file(self.name)
            self.my_type = self.TYPE_D3
        elif bobj.name.startswith(self.CUBE_PREFIX):
            self.init_6_face()
            self.my_type = self.TYPE_CUBE
        else:
            Gearoenix.terminate('Unspecified texture type, in:', bobl.name)

    def write(self):
        super().write()
        if self.my_type == self.TYPE_2D or self.my_type == self.TYPE_3D:
            Gearoenix.write_file(self.file)
        elif self.my_type == self.TYPE_CUBE:
            self.write_6_face()
        else:
            Gearoenix.terminate('Unspecified texture type, in:', self.bobj.name)

    @staticmethod
    def get_name_from_bobj(bobj):
        if bobj.type != 'IMAGE':
            Gearoenix.terminate('Unrecognized type for texture')
        filepath = bpy.path.abspath(bobj.filepath_raw).strip()
        if filepath is None or len(filepath) == 0:
            Gearoenix.terminate('Filepass is empty:', bobj.name)
        return filepath


@Gearoenix.register
class Font(Gearoenix.ReferenceableObject):
    TYPE_2D = 1
    TYPE_3D = 2

    @classmethod
    def init(cls):
        super().init()
        cls.D2_PREFIX = cls.get_prefix() + '2d-'
        cls.D3_PREFIX = cls.get_prefix() + '3d-'

    def __init__(self, bobj):
        super().__init__(bobj)
        if bobj.name.startswith(self.D2_PREFIX):
            self.my_type = self.TYPE_2D
        elif bobj.name.startswith(self.D3_PREFIX):
            self.my_type = self.TYPE_D3
        else:
            Gearoenix.terminate('Unspecified texture type, in:', bobl.name)
        self.file = read_ttf(self.name)

    def write(self):
        super().write()
        Gearoenix.write_file(self.file)

    @staticmethod
    def get_name_from_bobj(bobj):
        filepath = None
        if str(type(bobj)) == "<class 'bpy.types.VectorFont'>":
            filepath = bpy.path.abspath(bobj.filepath).strip()
        else:
            Gearoenix.terminate('Unrecognized type for font')
        if filepath is None or len(filepath) == 0:
            Gearoenix.terminate('Filepass is empty:', bobj.name)
        if not filepath.endswith('.ttf'):
            Gearoenix.terminate('Use TTF for font, in:', filepath)
        return filepath


@Gearoenix.register
class Material:

    FIELD_IS_FLOAT = 1
    FIELD_IS_TEXTURE = 2
    FIELD_IS_VECTOR = 3

    def __init__(self, bobj):
        self.inputs = {
            'Alpha': [None, 1],
            'AlphaCutoff': [None, 2],
            'AlphaMode': [None, 3],
            'BaseColor': [None, 4],
            'BaseColorFactor': [None, 5],
            'DoubleSided': [None, 6],
            'Emissive': [None, 7],
            'EmissiveFactor': [None, 8],
            'MetallicFactor': [None, 9],
            'MetallicRoughness': [None, 10],
            'Normal': [None, 11],
            'NormalScale': [None, 12],
            'Occlusion': [None, 13],
            'OcclusionStrength': [None, 14],
            'RoughnessFactor': [None, 15],
        }
        if len(bobj.material_slots) < 1:
            Gearoenix.terminate('There is no material:', bobl.name)
        if len(bobj.material_slots) > 1:
            Gearoenix.terminate('There must be only one material slot:', bobl.name)
        mat = bobj.material_slots[0]
        if mat.material is None:
            Gearoenix.terminate('Material does not exist in:', bobj.name)
        mat = mat.material
        if mat.node_tree is None:
            Gearoenix.terminate('Material node tree does not exist in:', bobj.name)
        node = mat.node_tree
        if 'Group' not in node.nodes:
            Gearoenix.terminate('Material main group node does not exist in:', bobj.name)
        node = node.nodes['Group']
        for input in self.inputs.keys():
            if input not in node.inputs:
                Gearoenix.terminate('Material is incorrect in:', bobj.name)
        for k in self.inputs.keys():
            input = node.inputs[k]
            if len(input.links) < 1:
                self.inputs[k][0] = input.default_value
            elif len(input.links) == 1:
                img = input.links[0].from_node.image
                txt = Gearoenix.Texture.read(img)
                self.inputs[k][0] = txt
            else:
                Gearoenix.terminate('Unexpected number of links in:', input)

    def write(self):
        Gearoenix.log_info("Matrial properties are:", self.inputs)
        for v, i in self.inputs.values():
            Gearoenix.write_u8(i)
            if isinstance(v, Gearoenix.Texture):
                Gearoenix.write_type_id(self.FIELD_IS_TEXTURE)
                Gearoenix.write_u64(v.my_id)
            elif isinstance(v, float):
                Gearoenix.write_type_id(self.FIELD_IS_FLOAT)
                Gearoenix.write_float(v)
            elif isinstance(v, bpy.types.bpy_prop_array):
                Gearoenix.write_type_id(self.FIELD_IS_VECTOR)
                Gearoenix.write_vector(v, 4)
            elif isinstance(v, mathutils.Vector):
                Gearoenix.write_type_id(self.FIELD_IS_VECTOR)
                Gearoenix.write_vector(v, 4)
            else:
                Gearoenix.terminate('Unexpected type for material input in:', self.bobj.name)

    def has_same_attrs(self, other):
        for sv, ov in zip(self.inputs.values(), other.inputs.values()):
            if isinstance(sv, Gearoenix.Texture) != isinstance(ov, Gearoenix.Texture):
                return False
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

    def __init__(self, bobj):
        super().__init__(bobj)
        if bobj.name.startswith(self.BASIC_PREFIX):
            self.my_type = self.TYPE_BASIC
        else:
            Gearoenix.terminate('Unspecified mesh type, in:', bobl.name)
        if bobj.type != 'MESH':
            Gearoenix.terminate('Mesh must be of type MESH:', bobj.name)
        if Gearoenix.has_transformation(bobj):
            Gearoenix.terminate('Mesh must not have any transformation. in:', bobj.name)
        if len(bobj.children) != 0:
            Gearoenix.terminate('Mesh can not have children:', bobj.name)
        self.mat = Gearoenix.Material(bobj)
        if self.origin_instance is not None:
            if not self.mat.has_same_attrs(self.origin_instance.mat):
                Gearoenix.terminate('Different mesh attributes, in: ' + bobj.name)
            return
        if bobj.parent is not None:
            Gearoenix.terminate('Origin mesh can not have parent:', bobj.name)
        msh = bobj.data
        msh.calc_normals_split()
        msh.calc_tangents()
        nrm = self.mat.needs_normal()
        tng = self.mat.needs_tangent()
        uv = self.mat.needs_uv()
        vertices = dict()
        last_index = 0
        self.occlusion_radius = 0.0
        for p in msh.polygons:
            if len(p.vertices) > 3:
                Gearoenix.terminate('Object', bobj.name, 'is not triangled!')
            for i, li in zip(p.vertices, p.loop_indices):
                vertex = []
                v = msh.vertices[i].co
                occlusion_radius = v.length
                if occlusion_radius > self.occlusion_radius:
                    self.occlusion_radius = occlusion_radius
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
                    uv_lyrs = msh.uv_layers
                    if len(uv_lyrs) > 1 or len(uv_lyrs) < 1:
                        Gearoenix.terminate('Unexpected number of uv layers in', bobj.name)
                    texco = uv_lyrs.active.data[li].uv
                    vertex.append(texco[0])
                    vertex.append(1.0 - texco[1])
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
        Gearoenix.write_u8(len(self.vertices[0]))
        Gearoenix.write_u64(len(self.vertices))
        for vertex in self.vertices:
            for e in vertex:
                Gearoenix.write_float(e)
        Gearoenix.write_u32_array(self.indices)
        Gearoenix.write_float(self.occlusion_radius)


@Gearoenix.register
class Occlusion:
    PREFIX = 'occlusion-'

    def __init__(self, bobj):
        if bobj.empty_draw_type != 'SPHERE':
            Gearoenix.terminate('The only acceptable shape for an occlusion is sphere. in:', bobj.name)
        if Gearoenix.has_transformation(bobj):
            Gearoenix.terminate('Occlusion can not have transformation. in:', bobj.name)
        radius = bobj.empty_draw_size
        radius = mathutils.Vector((radius, radius, radius))
        radius = bobj.matrix_world * radius
        self.radius = max(radius[0], max(radius[1], radius[2]))

    @classmethod
    def read(cls, bobj):
        for c in bobj.children:
            if c.name.startswith(cls.PREFIX):
                return cls(c)
        Gearoenix.terminate('Occlusion not found in: ', bobj.name)

    def write(self):
        Gearoenix.write_float(self.radius)


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
        if self.bobj.name.startswith(self.BUTTON_PREFIX):
            self.widget_type = self.TYPE_BUTTON
        elif self.bobj.name.startswith(self.TEXT_PREFIX):
            self.widget_type = self.TYPE_TEXT
        elif self.bobj.name.startswith(self.EDIT_PREFIX):
            self.widget_type = self.TYPE_EDIT
        else:
            Gearoenix.terminate('Unrecognized widget type:', self.bobj.name)
        if self.widget_type == self.TYPE_EDIT or \
                self.widget_type == self.TYPE_TEXT:
            self.text = self.bobj.data.body.strip()
            self.font = Font.read(self.bobj.data.font)
            align_x = self.bobj.data.align_x
            align_y = self.bobj.data.align_y
            self.align = 0
            if align_x == 'LEFT':
                self.align += 3
            elif align_x == 'CENTER':
                self.align += 0
            elif align_x == 'RIGHT':
                self.align += 6
            else:
                Gearoenix.terminate('Unrecognized text horizontal alignment, in:', self.bobj.name)
            if align_y == 'TOP':
                self.align += 3
            elif align_y == 'CENTER':
                self.align += 2
            elif align_y == 'BOTTOM':
                self.align += 1
            else:
                Gearoenix.terminate('Unrecognized text vertical alignment, in:', self.bobj.name)
            self.font_mat = Gearoenix.Material(self.bobj.material_slots[0].material)
            self.font_space_character = self.bobj.data.space_character - 1.0
            self.font_space_word = self.bobj.data.space_word - 1.0
            self.font_space_line = self.bobj.data.space_line

    def __init__(self, bobj):
        super().__init__(bobj)
        self.matrix = bobj.matrix_world
        self.occlusion = Gearoenix.Occlusion.read(bobj)
        self.meshes = []
        self.model_children = []
        self.collider = Gearoenix.Collider.read(bobj)
        for c in bobj.children:
            ins = Gearoenix.Mesh.read(c)
            if ins is not None:
                self.meshes.append(ins)
                continue
            ins = Gearoenix.Model.read(c)
            if ins is not None:
                self.model_children.append(ins)
                continue
        if len(self.model_children) + len(self.meshes) < 1 and not bobj.name.startswith(self.TEXT_PREFIX):
            Gearoenix.terminate('Waste model', bobj.name)
        if bobj.name.startswith(self.DYNAMIC_PREFIX):
            self.my_type = self.TYPE_DYNAMIC
        elif bobj.name.startswith(self.STATIC_PREFIX):
            self.my_type = self.TYPE_STATIC
        elif bobj.name.startswith(self.WIDGET_PREFIX):
            self.my_type = self.TYPE_WIDGET
            self.init_widget()
        else:
            Gearoenix.terminate('Unspecified model type, in:', bobj.name)

    def write_widget(self):
        if self.widget_type == self.TYPE_TEXT or\
                self.widget_type == self.TYPE_EDIT:
            Gearoenix.write_string(self.text)
            Gearoenix.write_u8(self.align)
            Gearoenix.write_float(self.font_space_character)
            Gearoenix.write_float(self.font_space_word)
            Gearoenix.write_float(self.font_space_line)
            Gearoenix.write_u64(self.font.my_id)
            self.font_mat.write()

    def write(self):
        super().write()
        if self.my_type == self.TYPE_WIDGET:
            Gearoenix.write_u64(self.widget_type)
        Gearoenix.write_matrix(self.bobj.matrix_world)
        self.occlusion.write()
        self.collider.write()
        Gearoenix.write_instances_ids(self.meshes)
        for m in self.meshes:
            m.mat.write()
        if self.my_type == self.TYPE_WIDGET:
            self.write_widget()
        Gearoenix.write_instances_ids(self.model_children)


@Gearoenix.register
class Skybox(Gearoenix.RenderObject):
    TYPE_BASIC = 1

    def __init__(self, bobj):
        super().__init__(bobj)
        self.my_type = 1
        self.mesh = None
        for c in bobj.children:
            if self.mesh is not None:
                Gearoenix.terminate('Only one mesh is accepted.')
            self.mesh = Mesh.read(c)
            if self.mesh is None:
                Gearoenix.terminate('Only one mesh is accepted.')
        self.mesh.mat = Shading(self.mesh.bobj.material_slots[0].material, self)

    def write(self):
        super().write()
        Gearoenix.write_u64(self.mesh.my_id)
        self.mesh.mat.write()


@Gearoenix.register
class Scene(Gearoenix.RenderObject):
    TYPE_GAME = 1
    TYPE_UI = 2

    @classmethod
    def init(cls):
        super().init()
        cls.GAME_PREFIX = cls.get_prefix() + 'game-'
        cls.UI_PREFIX = cls.get_prefix() + 'ui-'

    def __init__(self, bobj):
        super().__init__(bobj)
        self.models = []
        self.skybox = None
        self.cameras = []
        self.lights = []
        self.audios = []
        self.constraints = []
        for o in bobj.objects:
            if o.parent is not None:
                continue
            ins = Gearoenix.Model.read(o)
            if ins is not None:
                self.models.append(ins)
                continue
            ins = Gearoenix.Skybox.read(o)
            if ins is not None:
                if self.skybox is not None:
                    Gearoenix.terminate('Only one skybox is acceptable in a scene, wrong scene is: ', bobj.name)
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
        if bobj.name.startswith(self.GAME_PREFIX):
            self.my_type = self.TYPE_GAME
        elif bobj.name.startswith(self.UI_PREFIX):
            self.my_type = self.TYPE_UI
        else:
            Gearoenix.terminate('Unspecified scene type, in:', bobj.name)
        if len(self.cameras) < 1:
            Gearoenix.terminate('Scene must have at least one camera, in:', bobj.name)
        if len(self.lights) < 1:
            Gearoenix.terminate('Scene must have at least one light, in:', bobj.name)
        self.boundary_left = None
        if 'left' in bobj:
            self.boundary_left = bobj['left']  # todo it must be calculated, remove it
            self.boundary_right = bobj['right']  # todo it must be calculated, remove it
            self.boundary_up = bobj['up']  # todo it must be calculated, remove it
            self.boundary_down = bobj['down']  # todo it must be calculated, remove it
            self.boundary_front = bobj['front']  # todo it must be calculated, remove it
            self.boundary_back = bobj['back']  # todo it must be calculated, remove it
            self.grid_x_count = int(bobj['x-grid-count'])
            self.grid_y_count = int(bobj['y-grid-count'])
            self.grid_z_count = int(bobj['z-grid-count'])

    def write(self):
        super().write()
        Gearoenix.write_instances_ids(self.cameras)
        Gearoenix.write_instances_ids(self.audios)
        Gearoenix.write_instances_ids(self.lights)
        Gearoenix.write_instances_ids(self.models)
        Gearoenix.write_bool(self.skybox is not None)
        if self.skybox is not None:
            Gearoenix.write_u64(self.skybox.my_id)
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
    Gearoenix.initialize_pathes()
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
    filter_glob = bpy.props.StringProperty(
        default='*.gx3d',
        options={'HIDDEN'},
    )
    export_engine = bpy.props.EnumProperty(
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
            Gearoenix.log_info('Exporting for Gearoenix engine')
        elif engine == Gearoenix.ENGINE_VULKUST:
            Gearoenix.EXPORT_VULKUST = True
            Gearoenix.log_info('Exporting for Vulkust engine')
        else:
            Gearoenix.terminate('Unexpected export engine')
        Gearoenix.EXPORT_FILE_PATH = self.filepath
        Gearoenix.export_files()
        return {'FINISHED'}


@Gearoenix.register
def menu_func_export(self, context):
    self.layout.operator(
        Gearoenix.Exporter.bl_idname, text='Gearoenix 3D Exporter (.gx3d)')


@Gearoenix.register
def register_plugin():
    bpy.utils.register_class(Gearoenix.Exporter)
    bpy.types.INFO_MT_file_export.append(Gearoenix.menu_func_export)


if __name__ == '__main__':
    Gearoenix.register_plugin()
