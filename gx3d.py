itemsbl_info = {
    "name": "Gearoenix Blender",
    "author": "Hossein Noroozpour",
    "version": (2, 0),
    "blender": (2, 7, 5),
    "api": 1,
    "location": "File > Export",
    "description": "Export several scene into a Gearoenix 3D file format.",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export",
}

# The philosophy behind this plugin is to import everything that is engaged
#    at least in one of the blender scene in a file. Plan is not to take
#    everything from blender and support every features of Blender.
#    Always best practises are the correct way of presenting data.

# todos:
#     - add the same anotation of skybox to other classes (low priority)

import ctypes
import enum
import io
import math
import os
import subprocess
import sys
import tempfile

import bpy
import bpy_extras
import mathutils

TYPE_BOOLEAN = ctypes.c_uint8
TYPE_BYTE = ctypes.c_uint8
TYPE_FLOAT = ctypes.c_float
TYPE_U64 = ctypes.c_uint64
TYPE_U32 = ctypes.c_uint32
TYPE_U16 = ctypes.c_uint16
TYPE_U8 = ctypes.c_uint8

STRING_CUTOFF = 'cutoff'

DEBUG_MODE = True

EPSILON = 0.0001


class GearoenixInfo:
    ENGINE_GEAROENIX = 0
    ENGINE_VRUST = 1

    EXPORT_VULKAN = False
    EXPORT_METAL = False
    EXPORT_FILE_PATH = None

    GX3D_FILE = None
    CPP_FILE = None
    CPP_ENUM_FILE = None
    RUST_FILE = None

    PATH_VRUST_SDK = None
    PATH_GEAROENIX_SDK = None
    PATH_SHADERS_DIR = None
    PATH_SHADER_COMPILER = None
    PATH_TOOLS_DIR = None
    PATH_TTF_BAKER = None


class Gearoenix:
    @classmethod
    def register_class(cls, c):
        exec("cls." + c.__name__ + " = c")


def terminate(*msgs):
    msg = ""
    for m in msgs:
        msg += str(m) + " "
    print("Error: " + msg)
    raise Exception(msg)


def initialize_pathes():
    if GearoenixInfo.ENGINE_GEAROENIX == GearoenixInfo.EXPORT_ENGINE:
        GearoenixInfo.PATH_GEAROENIX_SDK = os.environ.get("GEAROENIX_SDK")
        if GearoenixInfo.PATH_GEAROENIX_SDK is None:
            terminate("Gearoenix SDK environment variable not found")
        GearoenixInfo.PATH_TOOLS_DIR = GearoenixInfo.PATH_GEAROENIX_SDK + \
            "/tools/"
    else:
        GearoenixInfo.PATH_VRUST_SDK = os.environ.get("VRUST_SDK")
        if GearoenixInfo.PATH_VRUST_SDK is None:
            terminate("VRust SDK environment variable not found")
        terminate("not implemented yet.")
    GearoenixInfo.PATH_TTF_BAKER = GearoenixInfo.PATH_TOOLS_DIR + \
        "gearoenix-ttf-baker.exe"
    GearoenixInfo.GX3D_FILE = open(GearoenixInfo.EXPORT_FILE_PATH, mode='wb')
    GearoenixInfo.RUST_FILE = open(
        GearoenixInfo.EXPORT_FILE_PATH + ".rs", mode='w')
    GearoenixInfo.CPP_FILE = open(
        GearoenixInfo.EXPORT_FILE_PATH + ".hpp", mode='w')
    GearoenixInfo.CPP_ENUM_FILE = open(
        GearoenixInfo.EXPORT_FILE_PATH + "-enum.hpp", mode='w')


def log_info(*msgs):
    if DEBUG_MODE:
        msg = ""
        for m in msgs:
            msg += str(m) + " "
        print("Info: " + msg)


def write_cpp_enum(*msgs):
    msg = ""
    for m in msgs:
        msg += str(m) + " "
    GearoenixInfo.CPP_ENUM_FILE.write(msg + '\n')


def write_float(f):
    GearoenixInfo.GX3D_FILE.write(TYPE_FLOAT(f))


def write_u64(n):
    GearoenixInfo.GX3D_FILE.write(TYPE_U64(n))


def write_u32(n):
    GearoenixInfo.GX3D_FILE.write(TYPE_U32(n))


def write_u16(n):
    GearoenixInfo.GX3D_FILE.write(TYPE_U16(n))


def write_u8(n):
    GearoenixInfo.GX3D_FILE.write(TYPE_U8(n))


def write_instances_ids(inss):
    write_u64(len(inss))
    for ins in inss:
        write_u64(ins.my_id)


def write_vector(v, element_count=3):
    for i in range(element_count):
        write_float(v[i])


def write_matrix(matrix):
    for i in range(0, 4):
        for j in range(0, 4):
            write_float(matrix[j][i])


def write_u32_array(arr):
    write_u64(len(arr))
    for i in arr:
        write_u32(i)


def write_u64_array(arr):
    write_u64(len(arr))
    for i in arr:
        write_u64(i)


def write_bool(b):
    data = 0
    if b:
        data = 1
    GearoenixInfo.GX3D_FILE.write(TYPE_BOOLEAN(data))


def file_tell():
    return GearoenixInfo.GX3D_FILE.tell()


def limit_check(val, maxval=1.0, minval=0.0, obj=None):
    if val > maxval or val < minval:
        msg = "Out of range value"
        if obj is not None:
            msg += ", in object: " + obj.name
        terminate(msg)


def uint_check(s):
    try:
        if int(s) >= 0:
            return True
    except ValueError:
        terminate("Type error")
    terminate("Type error")


def get_origin_name(bobj):
    origin_name = bobj.name.strip().split('.')
    num_dot = len(origin_name)
    if num_dot > 2 or num_dot < 1:
        terminate("Wrong name in:", bobj.name)
    elif num_dot == 1:
        return None
    try:
        int(origin_name[1])
    except:
        terminate("Wrong name in:", bobj.name)
    return origin_name[0]


def is_zero(f):
    return -EPSILON < f < EPSILON


def has_transformation(bobj):
    m = bobj.matrix_world
    if bobj.parent is not None:
        m = bobj.parent.matrix_world.inverted() * m
    for i in range(4):
        for j in range(4):
            if i == j:
                if not is_zero(m[i][j] - 1.0):
                    return True
            elif not is_zero(m[i][j]):
                return True
    return False


def write_string(s):
    write_u64(len(s))
    for c in s:
        write_u8(int(ord(c)))


def const_string(s):
    ss = s.replace("-", "_")
    ss = ss.replace('/', '_')
    ss = ss.replace('.', '_')
    ss = ss.replace('C:\\', '_')
    ss = ss.replace('c:\\', '_')
    ss = ss.replace('\\', '_')
    ss = ss.upper()
    return ss


def read_file(f):
    return open(f, "rb").read()


def write_file(f):
    write_u64(len(f))
    GearoenixInfo.GX3D_FILE.write(f)


def enum_max_check(e):
    if e == e.MAX:
        terminate('UNEXPECTED')


def write_start_module(c):
    mod_name = c.__name__
    GearoenixInfo.RUST_FILE.write("pub mod " + mod_name + " {\n")
    GearoenixInfo.CPP_FILE.write("namespace " + mod_name + "\n{\n")


def write_name_id(name, item_id):
    GearoenixInfo.RUST_FILE.write(
        "\tpub const " + name + ": u64 = " + str(item_id) + ";\n")
    GearoenixInfo.CPP_FILE.write(
        "\tconst gearoenix::core::Id " + name + " = " + str(item_id) + ";\n")


def write_end_modul():
    GearoenixInfo.RUST_FILE.write("}\n")
    GearoenixInfo.CPP_FILE.write("}\n")


def find_common_starting(s1, s2):
    s = ''
    l = min(len(s1), len(s2))
    for i in range(l):
        if s1[i] == s2[i]:
            s += s1[i]
        else:
            break
    return s


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


def read_ttf(f):
    tmp = GxTmpFile()
    args = [GearoenixInfo.PATH_TTF_BAKER, f, tmp.filename]
    if subprocess.run(args).returncode != 0:
        terminate("TTF file " + f + " can not convert to PNG.")
    return tmp.read()


class RenderObject:
    # each instance of this class must define:
    #     my_type    int
    # it will add following fiels:
    #     last_id    int
    #     items      dict[name] = instance
    #     name       str
    #     my_id      int
    #     offset     int
    #     bobj       blender-object

    def __init__(self, bobj):
        self.offset = 0
        self.bobj = bobj
        self.my_id = self.__class__.last_id
        self.__class__.last_id += 1
        self.name = self.__class__.get_name_from_bobj(bobj)
        if not bobj.name.startswith(self.__class__.get_prefix()):
            terminate("Unexpected name in ", self.__class__.__name__)
        if self.name in self.__class__.items:
            terminate(self.name, "is already in items.")
        self.__class__.items[self.name] = self

    @classmethod
    def get_prefix(cls):
        return cls.__name__.lower() + '-'

    def write(self):
        write_u64(self.my_type)

    @classmethod
    def write_all(cls):
        items = [i for i in range(len(cls.items))]
        for item in cls.items.values():
            items[item.my_id] = item
        for item in items:
            item.offset = GearoenixInfo.GX3D_FILE.tell()
            item.write()

    @classmethod
    def write_table(cls):
        write_start_module(cls)
        items = [i for i in range(len(cls.items))]
        common_starting = ''
        if len(cls.items) > 1:
            for k in cls.items.keys():
                common_starting = const_string(k)
        for item in cls.items.values():
            items[item.my_id] = item
            common_starting = find_common_starting(common_starting,
                                                   const_string(item.name))
        write_u64(len(items))
        for item in items:
            write_u64(item.offset)
            write_name_id(
                const_string(item.name)[len(common_starting):], item.my_id)
        write_end_modul()

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
        cls.last_id = 0
        cls.items = dict()

    def get_offset(self):
        return self.offset


class UniRenderObject(RenderObject):
    # It is going to implement those objects:
    #     Having an origin that their data is is mostly same
    #     Must be kept unique in all object to prevent data redundancy
    # It adds following fields in addition to RenderObject fields:
    #     origin_instance instance

    def __init__(self, bobj):
        self.origin_instance = None
        origin_name = get_origin_name(bobj)
        if origin_name is None:
            return super().__init__(bobj)
        self.origin_instance = self.__class__.items[origin_name]
        self.name = bobj.name
        self.my_id = self.origin_instance.my_id
        self.my_type = self.origin_instance.my_type
        self.bobj = bobj

    def write(self):
        if self.origin_instance is not None:
            terminate('This object must not written like this. in', self.name)
        super().write()

    @classmethod
    def read(cls, bobj):
        if not bobj.name.startswith(cls.get_prefix()):
            return None
        origin_name = get_origin_name(bobj)
        if origin_name is None:
            return super().read(bobj)
        super().read(bpy.data.objects[origin_name])
        return cls(bobj)


class ReferenceableObject(RenderObject):
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
            terminate('This object must not written like this. in', self.name)
        super().write()

    def get_offset(self):
        if self.origin_instance is None:
            return self.offset
        return self.origin_instance.offset


class Audio(ReferenceableObject):
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
            terminate('Unspecified type in:', bobl.name)
        self.file = read_file(self.name)

    def write(self):
        super().write()
        write_file(self.file)

    @staticmethod
    def get_name_from_bobj(bobj):
        if bobj.type != 'SPEAKER':
            terminate("Audio must be speaker: ", bobj.name)
        aud = bobj.data
        if aud is None:
            terminate("Audio is not set in speaker: ", bobj.name)
        aud = aud.sound
        if aud is None:
            terminate("Sound is not set in speaker: ", bobj.name)
        filepath = aud.filepath.strip()
        if filepath is None or len(filepath) == 0:
            terminate("Audio is not specified yet in speaker: ", bobj.name)
        if not filepath.endswith(".ogg"):
            terminate("Use OGG instead of ", filepath)
        return filepath


class Light(RenderObject):
    TYPE_SUN = 1

    @classmethod
    def init(cls):
        super().init()
        cls.SUN_PREFIX = cls.get_prefix() + 'sun-'

    def __init__(self, bobj):
        super().__init__(bobj)
        if self.bobj.type != 'LAMP':
            terminate('Light type is incorrect:', bobj.name)
        if bobj.name.startswith(self.SUN_PREFIX):
            self.my_type = self.TYPE_SUN
        else:
            terminate('Unspecified type in:', bobj.name)

    def write(self):
        super().write()
        write_vector(self.bobj.location)
        write_vector(self.bobj.rotation_euler)
        write_float(self.bobj['near'])
        write_float(self.bobj['far'])
        write_float(self.bobj['size'])
        write_vector(self.bobj.data.color)


class Camera(RenderObject):
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
            terminate('Camera type is incorrect:', bobj.name)
        if bobj.name.startswith(self.PERSPECTIVE_PREFIX):
            self.my_type = self.TYPE_PERSPECTIVE
            if bobj.data.type != 'PERSP':
                terminate('Camera type is incorrect:', bobj.name)
        elif bobj.name.startswith(self.ORTHOGRAPHIC_PREFIX):
            self.my_type = self.TYPE_ORTHOGRAPHIC
            if bobj.data.type != 'ORTHO':
                terminate('Camera type is incorrect:', bobj.name)
        else:
            terminate('Unspecified type in:', bobj.name)

    def write(self):
        super().write()
        cam = self.bobj.data
        write_vector(self.bobj.location)
        write_vector(self.bobj.rotation_euler)
        write_float(cam.clip_start)
        write_float(cam.clip_end)
        cam = self.bobj.data
        if self.my_type == self.TYPE_PERSPECTIVE:
            write_float(cam.angle_x / 2.0)
        elif self.my_type == self.TYPE_ORTHOGRAPHIC:
            write_float(cam.ortho_scale / 2.0)
        else:
            terminate('Unspecified type in:', bobj.name)


class Constraint(RenderObject):
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
            terminate('Unspecified type in:', bobj.name)

    def write(self):
        super().write()
        if self.my_type == self.TYPE_PLACER:
            self.write_placer()
        else:
            terminate('Unspecified type in:', bobj.name)

    def init_placer(self):
        BTYPE = "EMPTY"
        DESC = 'Placer constraint'
        ATT_X_MIDDLE = 'x-middle'  # 0
        ATT_Y_MIDDLE = 'y-middle'  # 1
        ATT_X_RIGHT = 'x-right'  # 2
        ATT_X_LEFT = 'x-left'  # 3
        ATT_Y_UP = 'y-up'  # 4
        ATT_Y_DOWN = 'y-down'  # 5
        ATT_RATIO = 'ratio'
        if self.bobj.type != BTYPE:
            terminate(DESC, "type must be", BTYPE, "in object:",
                      self.bobj.name)
        if len(self.bobj.children) < 1:
            terminate(DESC, "must have more than 0 children, in object:",
                      self.bobj.name)
        self.model_children = []
        for c in self.bobj.children:
            ins = Gearoenix.Model.read(c)
            if ins is None:
                terminate(DESC, "can only have model as its child, in object:",
                          self.bobj.name)
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
        if self.placer_type not in {
                4, 8, 33,
        }:
            terminate(DESC, "must have meaningful combination, in object:",
                      self.bobj.name)

    def write_placer(self):
        write_u64(self.placer_type)
        if self.ratio is not None:
            write_float(self.ratio)
        if self.placer_type == 4:
            write_float(self.attrs[2])
        elif self.placer_type == 8:
            write_float(self.attrs[3])
        elif self.placer_type == 33:
            write_float(self.attrs[0])
            write_float(self.attrs[5])
        else:
            terminate("It is not implemented, in object:", self.bobj.name)
        childrenids = []
        for c in self.model_children:
            childrenids.append(c.my_id)
        childrenids.sort()
        write_u64_array(childrenids)

    def check_trans(self):
        if has_transformation(self.bobj):
            terminate("This object should not have any transformation, in:",
                      self.bobj.name)


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
                terminate("Unexpected bobj is None")
        if not bobj.name.startswith(self.PREFIX):
            terminate("Collider object name is wrong. In:", bobj.name)
        self.bobj = bobj

    def write(self):
        write_u64(self.MY_TYPE)
        pass

    @classmethod
    def read(cls, pbobj):
        collider_object = None
        for bobj in pbobj.children:
            for c in cls.CHILDREN:
                if bobj.name.startswith(c.PREFIX):
                    if collider_object is not None:
                        terminate("Only one collider is acceptable. In model:",
                                  pbobj.name)
                    collider_object = c(bobj)
        if collider_object is None:
            return GhostCollider()
        return collider_object


class GhostCollider(Collider):
    MY_TYPE = Collider.GHOST
    PREFIX = Collider.PREFIX + 'ghost-'


Collider.CHILDREN.append(GhostCollider)


class MeshCollider(Collider):
    MY_TYPE = Collider.MESH
    PREFIX = Collider.PREFIX + 'mesh-'

    def __init__(self, bobj):
        super().__init__(bobj)
        self.bobj = bobj
        if bobj.type != 'MESH':
            terminate('Mesh collider must have mesh object type, In model:',
                      bobj.name)
        if has_transformation(bobj):
            terminate('Mesh collider can not have any transformation, in:',
                      bobj.name)
        msh = bobj.data
        self.triangles = []
        for p in msh.polygons:
            triangle = []
            if len(p.vertices) > 3:
                terminate("Object", bobj.name, "is not triangled!")
            for i, li in zip(p.vertices, p.loop_indices):
                triangle.append(msh.vertices[i].co)
            self.triangles.append(triangle)

    def write(self):
        super().write()
        write_u64(len(self.triangles))
        for t in self.triangles:
            for pos in t:
                write_vector(pos)


Collider.CHILDREN.append(MeshCollider)


class Texture(ReferenceableObject):
    TYPE_2D = 1
    TYPE_3D = 2
    TYPE_CUBE = 3
    TYPE_BACKED_ENVIRONMENT = 4
    TYPE_NORMALMAP = 5
    TYPE_SPECULARE = 6

    @classmethod
    def init(cls):
        super().init()
        cls.D2_PREFIX = cls.get_prefix() + "2d-"
        cls.D3_PREFIX = cls.get_prefix() + "3d-"
        cls.CUBE_PREFIX = cls.get_prefix() + "cube-"
        cls.BACKED_ENVIRONMENT_PREFIX = cls.get_prefix() + "bkenv-"
        cls.NORMALMAP_PREFIX = cls.get_prefix() + "nrm-"
        cls.SPECULARE_PREFIX = cls.get_prefix() + "spec-"

    def init_6_face(self):
        if not self.name.endswith('-up.png'):
            terminate('Incorrect 6 face texture:', self.bobj.name)
        base_name = self.name[:len(self.name) - len('-up.png')]
        self.img_up = read_file(self.name)
        self.img_down = read_file(base_name + '-down.png')
        self.img_left = read_file(base_name + '-left.png')
        self.img_right = read_file(base_name + '-right.png')
        self.img_front = read_file(base_name + '-front.png')
        self.img_back = read_file(base_name + '-back.png')

    def write_6_face(self):
        write_file(self.img_up)
        write_file(self.img_down)
        write_file(self.img_left)
        write_file(self.img_right)
        write_file(self.img_front)
        write_file(self.img_back)

    def __init__(self, bobj):
        super().__init__(bobj)
        if bobj.name.startswith(self.D2_PREFIX):
            self.file = read_file(self.name)
            self.my_type = self.TYPE_2D
        elif bobj.name.startswith(self.D3_PREFIX):
            self.file = read_file(self.name)
            self.my_type = self.TYPE_D3
        elif bobj.name.startswith(self.CUBE_PREFIX):
            self.init_6_face()
            self.my_type = self.TYPE_CUBE
        elif bobj.name.startswith(self.BACKED_ENVIRONMENT_PREFIX):
            self.init_6_face()
            self.my_type = self.TYPE_BACKED_ENVIRONMENT
        elif bobj.name.startswith(self.NORMALMAP_PREFIX):
            self.file = read_file(self.name)
            self.my_type = self.TYPE_NORMALMAP
        elif bobj.name.startswith(self.SPECULARE_PREFIX):
            self.file = read_file(self.name)
            self.my_type = self.TYPE_SPECULARE
        else:
            terminate('Unspecified texture type, in:', bobl.name)

    def write(self):
        super().write()
        if self.my_type == self.TYPE_2D or \
                self.my_type == self.TYPE_3D or \
                self.my_type == self.TYPE_NORMALMAP or \
                self.my_type == self.TYPE_SPECULARE:
            write_file(self.file)
        elif self.my_type == self.TYPE_CUBE or \
                self.my_type == self.TYPE_BACKED_ENVIRONMENT:
            self.write_6_face()
        else:
            terminate('Unspecified texture type, in:', self.bobj.name)

    @staticmethod
    def get_name_from_bobj(bobj):
        filepath = None
        if bobj.type == 'IMAGE':
            img = bobj.image
            if img is None:
                terminate("Image is not set in texture:", bobj.name)
            filepath = bpy.path.abspath(bobj.image.filepath_raw).strip()
        else:
            terminate("Unrecognized type for texture")
        if filepath is None or len(filepath) == 0:
            terminate("Filepass is empty:", bobj.name)
        if not filepath.endswith(".png"):
            terminate("Use PNG for image, in:", filepath)
        return filepath


class Font(ReferenceableObject):
    TYPE_2D = 1
    TYPE_3D = 2

    @classmethod
    def init(cls):
        super().init()
        cls.D2_PREFIX = cls.get_prefix() + "2d-"
        cls.D3_PREFIX = cls.get_prefix() + "3d-"

    def __init__(self, bobj):
        super().__init__(bobj)
        if bobj.name.startswith(self.D2_PREFIX):
            self.my_type = self.TYPE_2D
        elif bobj.name.startswith(self.D3_PREFIX):
            self.my_type = self.TYPE_D3
        else:
            terminate('Unspecified texture type, in:', bobl.name)
        self.file = read_ttf(self.name)

    def write(self):
        super().write()
        write_file(self.file)

    @staticmethod
    def get_name_from_bobj(bobj):
        filepath = None
        if str(type(bobj)) == "<class 'bpy.types.VectorFont'>":
            filepath = bpy.path.abspath(bobj.filepath).strip()
        else:
            terminate("Unrecognized type for font")
        if filepath is None or len(filepath) == 0:
            terminate("Filepass is empty:", bobj.name)
        if not filepath.endswith(".ttf"):
            terminate("Use TTF for font, in:", filepath)
        return filepath


class Shader:
    items = dict()  # int -> instance

    @classmethod
    def init(cls):
        cls.items = dict()

    @classmethod
    def read(cls, shd):
        my_id = shd.to_int()
        if my_id in cls.items:
            return None
        cls.items[my_id] = shd

    @classmethod
    def write_table(cls):
        pass
        # for k in cls.items.keys():
        #     write_u64(k)

    @classmethod
    def write_all(cls):
        # this is for future
        pass


class Shading:
    class Reserved(enum.Enum):
        DEPTH_POS = 0
        DEPTH_POS_NRM = 1
        DEPTH_POS_UV = 2
        DEPTH_POS_NRM_UV = 3
        FONT_COLORED = 4
        SKYBOX_BASIC = 5
        MAX = 6

        def needs_normal(self):
            enum_max_check(self)
            return False

        def needs_uv(self):
            enum_max_check(self)
            if self == self.FONT_COLORED:
                return True
            return False

        def needs_tangent(self):
            enum_max_check(self)
            return False

        def translate_font(self, shd):
            class FontData:
                pass

            shd.font = FontData()
            color = shd.bmat.diffuse_color
            alpha = shd.bmat.alpha
            shd.font.color = (color[0], color[1], color[2], alpha)
            return self.FONT_COLORED

        def translate_sky(self, shd):
            txt = None
            for s in shd.bmat.texture_slots:
                if s is None:
                    continue
                if txt is not None:
                    terminate("Only one texture is supported for skybox, in:",
                              shd.bmat.name)
                txt = s.texture
                if txt is None:
                    terminate("Unexpected")
                txt = Texture.read(txt)
                if txt is None:
                    terminate("Unexpected")
                if txt.my_type != Texture.TYPE_CUBE:
                    terminate("Only texture cube is supported for cube, in:",
                              shd.bmat.name)

            class SkyData:
                pass

            shd.sky = SkyData()
            shd.sky.txt = txt
            return self.SKYBOX_BASIC

        def translate(self, shd):
            if isinstance(shd.gxobj, Gearoenix.Model) and \
                shd.gxobj.my_type == Gearoenix.Model.TYPE_WIDGET and (
                    shd.gxobj.widget_type == Gearoenix.Model.TYPE_TEXT or
                    shd.gxobj.widget_type == Gearoenix.Model.TYPE_EDIT):
                return self.translate_font(shd)
            elif isinstance(shd.gxobj, Gearoenix.Skybox):
                return self.translate_sky(shd)
            else:
                terminate("Unexpected reserved material in:", shd.bmat.name)

        def write(self, shd):
            if self == self.FONT_COLORED:
                write_vector(shd.font.color, 4)
            elif self == self.SKYBOX_BASIC:
                write_u64(shd.sky.txt.my_id)
            return

    class Lighting(enum.Enum):
        RESERVED = 0
        SHADELESS = 1
        DIRECTIONAL = 2
        NORMALMAPPED = 3
        MAX = 4

        def check_reserved(self):
            if self == self.RESERVED:
                terminate('I can not judge about reserved.')

        def needs_normal(self):
            enum_max_check(self)
            self.check_reserved()
            return self == self.DIRECTIONAL or self == self.NORMALMAPPED

        def needs_uv(self):
            enum_max_check(self)
            self.check_reserved()
            return self == self.NORMALMAPPED

        def needs_tangent(self):
            enum_max_check(self)
            self.check_reserved()
            return self == self.NORMALMAPPED

        def translate(self, bmat, shd):
            nrm_txt = None
            for s in bmat.texture_slots:
                if s is None:
                    continue
                txt = s.texture
                if txt is None:
                    continue
                ins = Texture.read(txt)
                if ins is None:
                    continue
                if ins.my_type == Texture.TYPE_NORMALMAP:
                    if nrm_txt is not None:
                        terminate('Only one normal map is accepted in:',
                                  bmat.name)
                    nrm_txt = ins
            shadeless = bmat.use_shadeless
            if shadeless and nrm_txt is not None:
                terminate("One material can not have both normal-map texture",
                          "and have a shadeless lighting, error found in ",
                          "material:", bmat.name)
            if shadeless:
                return self.SHADELESS
            if nrm_txt is None:
                return self.DIRECTIONAL
            shd.normalmap = nrm_txt
            return self.NORMALMAPPED

        def write(self, shd):
            if self.NORMALMAPPED == self:
                write_u64(shd.normalmap.my_id)

    class Texturing(enum.Enum):
        COLORED = 0
        D2 = 1
        D3 = 2
        CUBE = 3
        MAX = 4

        def needs_normal(self):
            enum_max_check(self)
            return False

        def needs_uv(self):
            enum_max_check(self)
            return self == self.D2

        def needs_tangent(self):
            enum_max_check(self)
            return False

        def translate(self, bmat, shd):
            d2txt = None
            d3txt = None
            cubetxt = None
            for s in bmat.texture_slots:
                if s is None:
                    continue
                txt = s.texture
                if txt is None:
                    continue
                ins = Texture.read(txt)
                if ins is None:
                    continue
                if ins.my_type == Texture.TYPE_CUBE:
                    if cubetxt is not None:
                        terminate("Only one cube texture is expected:",
                                  bmat.name)
                    cubetxt = ins
                elif ins.my_type == Texture.TYPE_2D:
                    if d2txt is not None:
                        terminate("Only one 2d texture is expected:",
                                  bmat.name)
                    d2txt = ins
                elif ins.my_type == Texture.TYPE_3D:
                    if d3txt is not None:
                        terminate("Only one 3d texture is expected:",
                                  bmat.name)
                    d3txt = ins
            found = 0
            result = self.COLORED
            if d2txt is not None:
                shd.d2 = d2txt
                found += 1
                result = self.D2
            if d3txt is not None:
                shd.d3 = d3txt
                found += 1
                result = self.D3
            if cubetxt is not None:
                shd.cube = cubetxt
                found += 1
                result = self.CUBE
            if found == 0:
                shd.diffuse_color = []
                shd.diffuse_color.append(bmat.diffuse_color[0])
                shd.diffuse_color.append(bmat.diffuse_color[1])
                shd.diffuse_color.append(bmat.diffuse_color[2])
                if bmat.use_transparency:
                    shd.diffuse_color.append(bmat.alpha)
                else:
                    shd.diffuse_color.append(1.0)
                return self.COLORED
            if found > 1:
                terminate("Each material only can have one of 2D, 3D or Cube",
                          "textures, Error in material:", bmat.name)
            return result

        def write(self, shd):
            if self.COLORED == self:
                write_vector(shd.diffuse_color, 4)
            elif self.D2 == self:
                write_u64(shd.d2.my_id)
            elif self.D3 == self:
                write_u64(shd.d3.my_id)
            elif self.CUBE == self:
                write_u64(shd.cube.my_id)

    class Speculating(enum.Enum):
        MATTE = 0
        SPECULATED = 1
        SPECTXT = 2
        MAX = 3

        def needs_normal(self):
            enum_max_check(self)
            return self != self.MATTE

        def needs_uv(self):
            enum_max_check(self)
            return self == self.SPECTXT

        def needs_tangent(self):
            enum_max_check(self)
            return False

        def translate(self, bmat, shd):
            spectxt = None
            for s in bmat.texture_slots:
                if s is None:
                    continue
                txt = s.texture
                ins = Texture.read(txt)
                if ins is None:
                    continue
                if ins.my_type == Texture.TYPE_SPECULARE:
                    if spectxt is not None:
                        terminate('Only one speculare texture is expected in:',
                                  bmat.name)
                    spectxt = ins
            if spectxt is not None:
                shd.spectxt = spectxt
                return self.SPECTXT
            if not is_zero(bmat.specular_intensity):
                shd.specular_color = bmat.specular_color
                shd.specular_factors = mathutils.Vector(
                    (0.7, 0.9, bmat.specular_intensity))
                return self.SPECULATED
            return self.MATTE

        def write(self, shd):
            if self.SPECULATED == self:
                write_vector(shd.specular_color)
                write_vector(shd.specular_factors)
            elif self.SPECTXT == self:
                write_u64(shd.spectxt.my_id)

    class EnvironmentMapping(enum.Enum):
        NONREFLECTIVE = 0
        BAKED = 1
        REALTIME = 2
        MAX = 3

        def needs_normal(self):
            enum_max_check(self)
            return self != self.NONREFLECTIVE

        def needs_uv(self):
            enum_max_check(self)
            return False

        def needs_tangent(self):
            enum_max_check(self)
            return False

        def translate(self, bmat, shd):
            bakedtxt = None
            for s in bmat.texture_slots:
                if s is None:
                    continue
                txt = s.texture
                if txt is None:
                    continue
                txt = Texture.read(txt)
                if txt is None:
                    continue
                if txt.my_type == Texture.TYPE_BACKED_ENVIRONMENT:
                    if bakedtxt is not None:
                        terminate('Only one baked environment is accepted in:',
                                  bmat.name)
                    bakedtxt = txt
            reflective = bmat.raytrace_mirror is not None and \
                bmat.raytrace_mirror.use and \
                not is_zero(bmat.raytrace_mirror.reflect_factor)
            if bakedtxt is not None and not reflective:
                terminate("A material must set amount of reflectivity and",
                          "then have a baked-env texture. Error in material:",
                          bmat.name)
            if bakedtxt is not None:
                shd.reflect_factor = bmat.raytrace_mirror.reflect_factor
                shd.bakedenv = bakedtxt
                return self.BAKED
            if reflective:
                shd.reflect_factor = bmat.raytrace_mirror.reflect_factor
                return self.REALTIME
            return self.NONREFLECTIVE

        def write(self, shd):
            if self == self.BAKED or self == self.REALTIME:
                write_float(shd.reflect_factor)
            if self == self.BAKED:
                write_u64(shd.bakedenv.my_id)

    class Shadowing(enum.Enum):
        SHADOWLESS = 0
        CASTER = 1
        FULL = 2
        MAX = 3

        def needs_normal(self):
            enum_max_check(self)
            return self == self.FULL

        def needs_uv(self):
            enum_max_check(self)
            return False

        def needs_tangent(self):
            enum_max_check(self)
            return False

        def translate(self, bmat, shd):
            caster = bmat.use_cast_shadows
            receiver = bmat.use_shadows
            if not caster and receiver:
                terminate("A material can not be receiver but not " +
                          "caster. Error in material: " + bmat.name)
            if not caster:
                return self.SHADOWLESS
            if receiver:
                return self.FULL
            return self.CASTER

        def write(self, shd):
            return

    class Transparency(enum.Enum):
        OPAQUE = 1
        TRANSPARENT = 2
        CUTOFF = 3
        MAX = 4

        def needs_normal(self):
            enum_max_check(self)
            return False

        def needs_uv(self):
            enum_max_check(self)
            return self == self.CUTOFF

        def needs_tangent(self):
            enum_max_check(self)
            return False

        def translate(self, bmat, shd):
            trn = bmat.use_transparency and bmat.alpha < 1.0
            ctf = STRING_CUTOFF in bmat
            if trn and ctf:
                terminate("A material can not be transparent and cutoff in",
                          "same time. Error in material:", bmat.name)
            if trn:
                return self.TRANSPARENT
            if ctf:
                shd.transparency = bmat[STRING_CUTOFF]
                return self.CUTOFF
            return self.OPAQUE

        def write(self, shd):
            if self == self.CUTOFF:
                write_float(shd.transparency)

    def __init__(self, bmat=None, gxobj=None):
        self.shading_data = [
            self.Lighting.SHADELESS,
            self.Texturing.COLORED,
            self.Speculating.MATTE,
            self.EnvironmentMapping.NONREFLECTIVE,
            self.Shadowing.SHADOWLESS,
            self.Transparency.OPAQUE,
        ]
        self.reserved = self.Reserved.DEPTH_POS
        self.normalmap = None
        self.diffuse_color = None
        self.d2 = None
        self.d3 = None
        self.cube = None
        self.specular_color = None
        self.specular_factors = None
        self.spectxt = None
        self.reflect_factor = None
        self.bakedenv = None
        self.transparency = None
        self.bmat = bmat
        self.gxobj = gxobj
        if bmat is None:
            self.set_reserved(self.Reserved.DEPTH_POS)
        elif gxobj is not None:
            self.set_reserved(self.Reserved.DEPTH_POS.translate(self))
        else:
            for i in range(len(self.shading_data)):
                e = self.shading_data[i].translate(bmat, self)
                self.shading_data[i] = e

    def set_lighting(self, e):
        if not isinstance(e, self.Lighting) or e.MAX == e:
            terminate("Unexpected ", e, bmat.name)
        self.shading_data[0] = e

    def get_lighting(self):
        if self.is_reserved():
            return self.Lighting.MAX
        return self.shading_data[0]

    def set_texturing(self, e):
        if not isinstance(e, self.Texturing) or e.MAX == e:
            terminate("Unexpected ", e, bmat.name)
        self.shading_data[1] = e

    def get_texturing(self):
        if self.is_reserved():
            return self.Texturing.MAX
        return self.shading_data[1]

    def set_speculating(self, e):
        if not isinstance(e, self.Speculating) or e.MAX == e:
            terminate("Unexpected ", e, bmat.name)
        self.shading_data[2] = e

    def get_speculating(self):
        if self.is_reserved():
            return self.Speculating.MAX
        return self.shading_data[2]

    def set_environment_mapping(self, e):
        if not isinstance(e, self.EnvironmentMapping) or e.MAX == e:
            terminate("Unexpected ", e, bmat.name)
        self.shading_data[3] = e

    def get_environment_mapping(self):
        if self.is_reserved():
            return self.EnvironmentMapping.MAX
        return self.shading_data[3]

    def set_shadowing(self, e):
        if not isinstance(e, self.Shadowing) or e.MAX == e:
            terminate("Unexpected ", e, bmat.name)
        self.shading_data[4] = e

    def get_shadowing(self):
        if self.is_reserved():
            return self.Shadowing.MAX
        return self.shading_data[4]

    def set_transparency(self, e):
        if not isinstance(e, self.Transparency) or e.MAX == e:
            terminate("Unexpected ", e, bmat.name)
        self.shading_data[5] = e

    def get_transparency(self):
        if self.is_reserved():
            return self.Transparency.MAX
        return self.shading_data[5]

    def set_reserved(self, e):
        if not isinstance(e, self.Reserved) or e.MAX == e:
            terminate("Unexpected ", e, self.bmat)
        self.shading_data[0] = self.Lighting.RESERVED
        self.reserved = e

    def is_reserved(self):
        return self.shading_data[0] == self.Lighting.RESERVED

    def to_int(self):
        if self.is_reserved():
            return int(self.reserved.value)
        result = int(self.Reserved.MAX.value)
        coef = int(1)
        for e in self.shading_data:
            result += int(e.value) * coef
            coef *= int(e.MAX.value)
        return result

    def print_all_enums(self):
        all_enums = dict()

        def sub_print(es, pre, shd):
            if len(es) == 0:
                shd.shading_data = pre
                all_enums[shd.get_enum_name()] = shd.to_int()
            else:
                for e in es[0]:
                    sub_print(es[1:], pre + [e], shd)

        sub_print([
            self.Lighting, self.Texturing, self.Speculating,
            self.EnvironmentMapping, self.Shadowing, self.Transparency
        ], [], self)
        self.shading_data[0] = self.Lighting.RESERVED
        for e in self.Reserved:
            self.reserved = e
            all_enums[self.get_enum_name()] = self.to_int()
        log_info("Writing all enums")
        for k in sorted(all_enums):
            if 'MAX' not in k:
                write_cpp_enum(k, "=", all_enums[k], ",")
        log_info("End of writing all enums")

    def get_enum_name(self):
        result = ""
        if self.is_reserved():
            result = self.reserved.name + '_'
        else:
            for e in self.shading_data:
                result += e.name + '_'
        result = result[0:len(result) - 1]
        return result

    def get_file_name(self):
        result = self.get_enum_name()
        result = result.lower().replace('_', '-')
        return result

    def needs_normal(self):
        if self.is_reserved():
            return self.reserved.needs_normal()
        for e in self.shading_data:
            if e.needs_normal():
                return True
        return False

    def needs_uv(self):
        if self.is_reserved():
            return self.reserved.needs_uv()
        for e in self.shading_data:
            if e.needs_uv():
                return True
        return False

    def needs_tangent(self):
        if self.is_reserved():
            return self.reserved.needs_tangent()
        for e in self.shading_data:
            if e.needs_tangent():
                return True
        return False

    def has_same_attrs(self, o):
        return self.needs_normal() == o.needs_normal() and \
            self.needs_uv() == o.needs_uv() and \
            self.needs_tangent() == o.needs_tangent()

    def write(self):
        write_u64(self.to_int())
        if self.shading_data[0] == self.Lighting.RESERVED:
            self.reserved.write(self)
            return
        for e in self.shading_data:
            e.write(self)


class Mesh(UniRenderObject):
    TYPE_BASIC = 1

    def __init__(self, bobj):
        super().__init__(bobj)
        self.my_type = self.TYPE_BASIC
        if bobj.type != 'MESH':
            terminate('Mesh must be of type MESH:', bobj.name)
        if has_transformation(bobj):
            terminate("Mesh must not have any transformation. in:", bobj.name)
        if len(bobj.children) != 0:
            terminate("Mesh can not have children:", bobj.name)
        self.shd = Shading(bobj.material_slots[0].material)
        if self.origin_instance is not None:
            if not self.shd.has_same_attrs(self.origin_instance.shd):
                terminate("Different mesh attributes, in: " + bobj.name)
            return
        if bobj.parent is not None:
            terminate("Mesh can not have parent:", bobj.name)
        msh = bobj.data
        nrm = self.shd.needs_normal()
        uv = self.shd.needs_uv()
        vertices = dict()
        last_index = 0
        for p in msh.polygons:
            if len(p.vertices) > 3:
                terminate("Object " + bobj.name + " is not triangled!")
            for i, li in zip(p.vertices, p.loop_indices):
                vertex = []
                v = msh.vertices[i].co
                vertex.append(v[0])
                vertex.append(v[1])
                vertex.append(v[2])
                if nrm:
                    normal = msh.vertices[i].normal.normalized()
                    vertex.append(normal[0])
                    vertex.append(normal[1])
                    vertex.append(normal[2])
                if uv:
                    uv_lyrs = msh.uv_layers
                    if len(uv_lyrs) > 1 or len(uv_lyrs) < 1:
                        terminate("Unexpected number of uv layers in ",
                                  bobj.name)
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
        write_u64(len(self.vertices[0]))
        write_u64(len(self.vertices))
        for vertex in self.vertices:
            for e in vertex:
                write_float(e)
        write_u32_array(self.indices)


class Occlusion:
    PREFIX = 'occlusion-'

    def __init__(self, bobj):
        if bobj.empty_draw_type != 'SPHERE':
            terminate("The only acceptable shape for an occlusion is " +
                      "sphere. in: " + bobj.name)
        center = bobj.matrix_world * mathutils.Vector((0.0, 0.0, 0.0))
        radius = bobj.empty_draw_size
        radius = mathutils.Vector((radius, radius, radius))
        radius = bobj.matrix_world * radius
        radius -= center
        self.radius = radius
        self.center = bobj.parent.matrix_world.inverted() * center

    @classmethod
    def read(cls, bobj):
        for c in bobj.children:
            if c.name.startswith(cls.PREFIX):
                return cls(c)
        terminate("Occlusion not found in: ", bobj.name)

    def write(self):
        write_vector(self.radius)
        write_vector(self.center)


@Gearoenix.register_class
class Model(RenderObject):
    TYPE_BASIC = 1
    TYPE_WIDGET = 2
    TYPE_BUTTON = 3
    TYPE_TEXT = 4
    TYPE_EDIT = 5

    @classmethod
    def init(cls):
        super().init()
        cls.BASIC_PREFIX = cls.get_prefix() + 'basic-'
        cls.WIDGET_PREFIX = cls.get_prefix() + 'widget-'
        cls.BUTTON_PREFIX = cls.WIDGET_PREFIX + 'button-'
        cls.TEXT_PREFIX = cls.WIDGET_PREFIX + 'text-'
        cls.EDIT_PREFIX = cls.WIDGET_PREFIX + 'edit-'

    def init_widget(self):
        if self.bobj.name.startswith(self.BUTTON_PREFIX):
            self.widget_type = self.TYPE_BUTTON
        elif self.bobj.name.startswith(self.TEXT_PREFIX):
            self.widget_type = self.TYPE_TEXT
        elif self.bobj.name.startswith(self.EDIT_PREFIX):
            self.widget_type = self.TYPE_EDIT
        else:
            terminate('Unrecognized widget type:', self.bobj.name)
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
                terminate("Unrecognized text horizontal alignment, in:",
                          self.bobj.name)
            if align_y == 'TOP':
                self.align += 3
            elif align_y == 'CENTER':
                self.align += 2
            elif align_y == 'BOTTOM':
                self.align += 1
            else:
                terminate("Unrecognized text vertical alignment, in:",
                          self.bobj.name)
            self.font_shd = Shading(self.bobj.material_slots[0].material, self)
            self.font_space_character = self.bobj.data.space_character - 1.0
            self.font_space_word = self.bobj.data.space_word - 1.0
            self.font_space_line = self.bobj.data.space_line

    def __init__(self, bobj):
        super().__init__(bobj)
        self.matrix = bobj.matrix_world
        self.occlusion = Occlusion.read(bobj)
        self.meshes = []
        self.model_children = []
        self.collider = Collider.read(bobj)
        for c in bobj.children:
            ins = Mesh.read(c)
            if ins is not None:
                self.meshes.append(ins)
                continue
            ins = Gearoenix.Model.read(c)
            if ins is not None:
                self.model_children.append(ins)
                continue
        if len(self.model_children) + len(self.meshes) < 1 and \
                not bobj.name.startswith(self.TEXT_PREFIX):
            terminate('Waste model', bobj.name)
        if bobj.name.startswith(self.BASIC_PREFIX):
            self.my_type = self.TYPE_BASIC
        elif bobj.name.startswith(self.WIDGET_PREFIX):
            self.my_type = self.TYPE_WIDGET
            self.init_widget()
        else:
            terminate('Unspecified model type, in:', bobj.name)
        self.is_rigid_body = bobj.rigid_body is not None:
        if self.is_rigid_body:
            if self.collider.MY_TYPE = Collider.GHOST:
                terminate("Unexpected collider for rigid body, in:", bobj.name)
            self.is_rigid_body_dynamic = bobj.rigid_body.enabled

    def write_widget(self):
        if self.widget_type == self.TYPE_TEXT or\
                self.widget_type == self.TYPE_EDIT:
            write_string(self.text)
            write_u8(self.align)
            write_float(self.font_space_character)
            write_float(self.font_space_word)
            write_float(self.font_space_line)
            write_u64(self.font.my_id)
            self.font_shd.write()

    def write(self):
        super().write()
        if self.my_type == self.TYPE_WIDGET:
            write_u64(self.widget_type)
        write_matrix(self.bobj.matrix_world)
        self.occlusion.write()
        self.collider.write()
        write_instances_ids(self.model_children)
        write_instances_ids(self.meshes)
        write_bool(self.is_rigid_body)
        if self.is_rigid_body:
            write_bool(self.is_rigid_body_dynamic)
        for mesh in self.meshes:
            mesh.shd.write()
        if self.my_type == self.TYPE_WIDGET:
            self.write_widget()


@Gearoenix.register_class
class Skybox(RenderObject):
    TYPE_BASIC = 1

    def __init__(self, bobj):
        super().__init__(bobj)
        self.my_type = 1
        self.mesh = None
        for c in bobj.children:
            if self.mesh is not None:
                terminate("Only one mesh is accepted.")
            self.mesh = Mesh.read(c)
            if self.mesh is None:
                terminate("Only one mesh is accepted.")
        self.mesh.shd = Shading(self.mesh.bobj.material_slots[0].material,
                                self)

    def write(self):
        super().write()
        write_u64(self.mesh.my_id)
        self.mesh.shd.write()


class Scene(RenderObject):
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
                    terminate("Only one skybox is acceptable in a scene",
                              "wrong scene is: ", bobj.name)
                self.skybox = ins
                continue
            ins = Camera.read(o)
            if ins is not None:
                self.cameras.append(ins)
                continue
            ins = Light.read(o)
            if ins is not None:
                self.lights.append(ins)
                continue
            ins = Audio.read(o)
            if ins is not None:
                self.audios.append(ins)
                continue
            ins = Constraint.read(o)
            if ins is not None:
                self.constraints.append(ins)
                continue
        if bobj.name.startswith(self.GAME_PREFIX):
            self.my_type = self.TYPE_GAME
        elif bobj.name.startswith(self.UI_PREFIX):
            self.my_type = self.TYPE_UI
        else:
            terminate('Unspecified scene type, in:', bobj.name)
        if len(self.cameras) < 1:
            terminate('Scene must have at least one camera, in:', bobj.name)
        if len(self.lights) < 1:
            terminate('Scene must have at least one light, in:', bobj.name)
        self.boundary_left = None
        if 'left' in bobj:
            self.boundary_left = bobj['left']
            self.boundary_right = bobj['right']
            self.boundary_up = bobj['up']
            self.boundary_down = bobj['down']
            self.boundary_front = bobj['front']
            self.boundary_back = bobj['back']
            self.grid_x_count = int(bobj['x-grid-count'])
            self.grid_y_count = int(bobj['y-grid-count'])
            self.grid_z_count = int(bobj['z-grid-count'])

    def write(self):
        super().write()
        write_vector(self.bobj.world.ambient_color)
        write_instances_ids(self.cameras)
        write_instances_ids(self.audios)
        write_instances_ids(self.lights)
        write_instances_ids(self.models)
        write_bool(self.skybox is not None)
        if self.skybox is not None:
            write_u64(self.skybox.my_id)
        write_instances_ids(self.constraints)
        write_bool(self.boundary_left is not None)
        if self.boundary_left is not None:
            write_float(self.boundary_up)
            write_float(self.boundary_down)
            write_float(self.boundary_left)
            write_float(self.boundary_right)
            write_float(self.boundary_front)
            write_float(self.boundary_back)
            write_u16(self.grid_x_count)
            write_u16(self.grid_y_count)
            write_u16(self.grid_z_count)

    @classmethod
    def read_all(cls):
        for s in bpy.data.scenes:
            super().read(s)


# class Gearoenix:
#     @classmethod
#     def check_env(cls):
#         cls.PATH_ENGINE_SDK = os.environ.get(cls.STRING_ENGINE_SDK_VAR_NAME)
#         if cls.PATH_ENGINE_SDK is None:
#             cls.show('"' + cls.STRING_ENGINE_SDK_VAR_NAME +
#                      '" variable is not set!')
#         cls.PATH_SHADERS_DIR = cls.PATH_ENGINE_SDK + '/vulkan/shaders/'
#         if sys.platform == 'darwin':
#             cls.PATH_SHADER_COMPILER = "xcrun"
#         else:
#             cls.PATH_VULKAN_SDK = os.environ.get(
#                 cls.STRING_VULKAN_SDK_VAR_NAME)
#             if cls.PATH_VULKAN_SDK is None:
#                 cls.show('"' + cls.STRING_VULKAN_SDK_VAR_NAME +
#                          '" variable is not set!')
#                 return False
#             cls.PATH_SHADER_COMPILER = \
#                 cls.PATH_VULKAN_SDK + '/bin/glslangValidator'
#         return True
#
#     @classmethod
#     def compile_shader(cls, stage, shader_name):
#         tmp = cls.TmpFile()
#         args = None
#         if sys.platform == 'darwin':
#             args = [
#                 cls.PATH_SHADER_COMPILER, '-sdk', 'macosx', 'metal',
#                 shader_name, '-o', tmp.filename
#             ]
#         else:
#             args = [
#                 cls.PATH_SHADER_COMPILER, '-V', '-S', stage, shader_name, '-o',
#                 tmp.filename
#             ]
#         if subprocess.run(args).returncode != 0:
#             cls.show('Shader %s can not be compiled!' % shader_name)
#         if sys.platform == "darwin":
#             tmp2 = tmp
#             tmp = cls.TmpFile()
#             args = [
#                 cls.PATH_SHADER_COMPILER, '-sdk', 'macosx', 'metallib',
#                 tmp2.filename, '-o', tmp.filename
#             ]
#             if subprocess.run(args).returncode != 0:
#                 cls.show('Shader %s can not be build!' % shader_name)
#         tmp = tmp.read()
#         cls.log("Shader '", shader_name, "'is compiled has length of: ",
#                 len(tmp))
#         cls.out.write(TYPE_U64(len(tmp)))
#         cls.out.write(tmp)
#
#     @classmethod
#     def write_instances_offsets(cls, clsobj):
#         offsets = [i for i in range(len(clsobj.items))]
#         mod_name = clsobj.__name__
#         cls.rust_code.write("pub mod " + mod_name + " {\n")
#         cls.cpp_code.write("namespace " + mod_name + "\n{\n")
#         for name, instance in clsobj.items.items():
#             offset = instance.offset
#             item_id = instance.my_id
#             name = cls.const_string(name)
#             cls.rust_code.write(
#                 "\tpub const " + name + ": u64 = " + str(item_id) + ";\n")
#             cls.cpp_code.write("\tconst gearoenix::core::Id " + name + " = " +
#                                str(item_id) + ";\n")
#             offsets[item_id] = offset
#         cls.rust_code.write("}\n")
#         cls.cpp_code.write("}\n")
#         cls.write_u64_array(offsets)
#
#     @classmethod
#     def items_offsets(cls, items, mod_name):
#         offsets = [i for i in range(len(items))]
#         cls.rust_code.write("pub mod " + mod_name + " {\n")
#         cls.cpp_code.write("namespace " + mod_name + "\n{\n")
#         for name, offset_id in items.items():
#             offset, item_id = offset_id[0:2]
#             cls.rust_code.write("\tpub const " + cls.const_string(name) +
#                                 ": u64 = " + str(item_id) + ";\n")
#             cls.cpp_code.write(
#                 "\tconst gearoenix::core::Id " + cls.const_string(name) +
#                 " = " + str(item_id) + ";\n")
#             offsets[item_id] = offset
#         cls.rust_code.write("}\n")
#         cls.cpp_code.write("}\n")
#         return offsets
#
#     @classmethod
#     def write_all_instances(cls, clsobj):
#         items = [i for i in range(len(clsobj.items))]
#         for item in clsobj.items.values():
#             items[item.my_id] = item
#         for item in items:
#             item.offset = cls.out.tell()
#             item.write()
#
#     @classmethod
#     def read_materials(cls, m):
#         if m.type != 'MESH':
#             return
#         material_count = len(m.material_slots.keys())
#         if material_count == 1:
#             s = cls.Shading(cls, m.material_slots[0].material)
#             sid = s.to_int()
#             if sid in cls.shaders:
#                 return
#             cls.shaders[sid] = [0, s]
#         else:
#             cls.show("Unexpected number of materials in mesh " + m.name)


def write_tables():
    Shader.write_table()
    Camera.write_table()
    Audio.write_table()
    Light.write_table()
    Texture.write_table()
    Font.write_table()
    Mesh.write_table()
    Gearoenix.Model.write_table()
    Gearoenix.Skybox.write_table()
    Constraint.write_table()
    Scene.write_table()


def initialize_shaders():
    Shader.init()
    s = Shading()
    s.print_all_enums()
    s = Shading()
    s.set_reserved(Shading.Reserved.DEPTH_POS)
    # Shader.read(s)
    s = Shading()
    s.set_reserved(Shading.Reserved.DEPTH_POS_NRM)
    # Shader.read(s)
    s = Shading()
    s.set_reserved(Shading.Reserved.DEPTH_POS_UV)
    # Shader.read(s)
    s = Shading()
    s.set_reserved(Shading.Reserved.DEPTH_POS_NRM_UV)
    # Shader.read(s)


def export_files():
    initialize_pathes()
    initialize_shaders()
    Audio.init()
    Light.init()
    Camera.init()
    Texture.init()
    Font.init()
    Mesh.init()
    Gearoenix.Model.init()
    Gearoenix.Skybox.init()
    Constraint.init()
    Scene.init()
    Scene.read_all()
    write_bool(sys.byteorder == 'little')
    tables_offset = file_tell()
    write_tables()
    Shader.write_all()
    Camera.write_all()
    Audio.write_all()
    Light.write_all()
    Texture.write_all()
    Font.write_all()
    Mesh.write_all()
    Gearoenix.Model.write_all()
    Gearoenix.Skybox.write_all()
    Constraint.write_all()
    Scene.write_all()
    GearoenixInfo.GX3D_FILE.flush()
    GearoenixInfo.GX3D_FILE.seek(tables_offset)
    GearoenixInfo.RUST_FILE.seek(0)
    GearoenixInfo.CPP_FILE.seek(0)
    write_tables()
    GearoenixInfo.GX3D_FILE.flush()
    GearoenixInfo.GX3D_FILE.close()
    GearoenixInfo.RUST_FILE.flush()
    GearoenixInfo.RUST_FILE.close()
    GearoenixInfo.CPP_FILE.flush()
    GearoenixInfo.CPP_FILE.close()
    GearoenixInfo.CPP_ENUM_FILE.flush()
    GearoenixInfo.CPP_ENUM_FILE.close()


class GearoenixExporter(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    """This is a plug in for Gearoenix 3D file format"""
    bl_idname = "gearoenix_exporter.data_structure"
    bl_label = "Export Gearoenix 3D"
    filename_ext = ".gx3d"
    filter_glob = bpy.props.StringProperty(
        default="*.gx3d",
        options={'HIDDEN'},
    )
    export_vulkan = bpy.props.BoolProperty(
        name="Enable Vulkan",
        description="This item enables data exporting for Vulkan engine",
        default=False,
        options={'ANIMATABLE'},
        subtype='NONE',
        update=None)
    export_metal = bpy.props.BoolProperty(
        name="Enable Metal",
        description="This item enables data exporting for Metal engine",
        default=False,
        options={'ANIMATABLE'},
        subtype='NONE',
        update=None)
    export_engine = bpy.props.EnumProperty(
        name="Game engine",
        description="This item select the game engine",
        items=((str(GearoenixInfo.ENGINE_GEAROENIX), 'Gearoenix', ''), (str(
            GearoenixInfo.ENGINE_VRUST), 'VRust', '')))

    def execute(self, context):
        GearoenixInfo.EXPORT_VULKAN = bool(self.export_vulkan)
        GearoenixInfo.EXPORT_METAL = bool(self.export_metal)
        GearoenixInfo.EXPORT_ENGINE = int(self.export_engine)
        GearoenixInfo.EXPORT_FILE_PATH = self.filepath
        export_files()
        return {'FINISHED'}


def menu_func_export(self, context):
    self.layout.operator(
        GearoenixExporter.bl_idname, text="Gearoenix 3D Exporter (.gx3d)")


def register_plugin():
    bpy.utils.register_class(GearoenixExporter)
    bpy.types.INFO_MT_file_export.append(menu_func_export)


if __name__ == "__main__":
    register_plugin()
