bl_info = {
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
TYPE_U64 = ctypes.c_uint64
TYPE_BYTE = ctypes.c_uint8
TYPE_FLOAT = ctypes.c_float
TYPE_U32 = ctypes.c_uint32

PATH_ENGINE_SDK = None
PATH_GEAROENIX_SDK = None
PATH_SHADERS_DIR = None
PATH_SHADER_COMPILER = None

EXPORT_VULKAN = False
EXPORT_METAL = False

GX3D_FILE = None
CPP_FILE = None
RUST_FILE = None

DEBUG_MODE = True

EPSILON = 0.0001


def terminate(*msgs):
    msg = ""
    for m in msgs:
        msg += str(m) + " "
    print("Error: " + msg)
    raise Exception(msg)


def log_info(*msgs):
    if DEBUG_MODE:
        msg = ""
        for m in msgs:
            msg += str(m) + " "
        print("Info: " + msg)


def write_instances_ids(inss):
    GX3D_FILE.write(TYPE_U64(len(inss)))
    for ins in inss:
        GX3D_FILE.write(TYPE_U64(ins.my_id))


def write_vector(v, element_count=3):
    for i in range(element_count):
        GX3D_FILE.write(TYPE_FLOAT(v[i]))


def write_matrix(matrix):
    for i in range(0, 4):
        for j in range(0, 4):
            GX3D_FILE.write(TYPE_FLOAT(matrix[j][i]))


def write_u64(n):
    GX3D_FILE.write(TYPE_U64(n))


def write_u32(n):
    GX3D_FILE.write(TYPE_U32(n))


def write_u32_array(arr):
    write_u64(len(arr))
    for i in arr:
        write_u32(i)


def write_u64_array(arr):
    write_u64(len(arr))
    for i in arr:
        write_u64(i)


def write_float(f):
    gx3GX3D_FILE.write(TYPE_FLOAT(f))


def write_bool(b):
    data = 0
    if b:
        data = 1
    GX3D_FILE.write(TYPE_BOOLEAN(data))


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
    for i in range(4)
        for j in range(4):
            if i == j:
                if not is_zero(m[i][j] - 1.0):
                    return True
            elif not is_zero(m[i][j]):
                return True
    return False


def const_string(s):
    return s.replace("-", "_").replace('/', '_').replace('.', '_').upper()


def read_file(f):
    return open(f, "rb").read()


def write_file(f):
    write_u64(len(f))
    GX3D_FILE.write(f)


class RenderObject:
    # each instance of this class must define:
    #     MY_TYPE    int
    #     LAST_ID    int
    #     ITEMS      dict[name] = instance
    #     DESC       str
    #     CHILDREN   [subclass]
    #     PREFIX     str
    # it will add following fiels:
    #     name       str
    #     my_id      int
    #     offset     int
    #     bobj       blender-object
    # The immediate subclass must:
    #     Be itself root of other type, like scene, model, mesh, ...
    #     Must have at least one child
    # Most of the times leaf classes only needs this:
    #     PREFIX
    #     DESC
    #     MY_TYPE

    def __init__(self, bobj):
        self.offset = 0
        self.bobj = bobj
        self.my_id = self.LAST_ID
        self.LAST_ID += 1
        self.name = self.get_name_from_bobj(bobj)
        if not bobj.name.startswith(self.PREFIX):
            terminate("Unexpected name in ", self.DESC)
        if self.name in self.ITEMS:
            terminate(self.name, "is already in items.")
        self.ITEMS[self.name] = self

    def write(self):
        GX3D_FILE.write(TYPE_U64(self.MY_TYPE))

    @classmethod
    def write_all(cls):
        items = [i for i in range(len(cls.ITEMS))]
        for item in cls.ITEMS.values():
            items[item.my_id] = item
        for item in items:
            item.offset = GX3D_FILE.tell()
            item.write()

    @classmethod
    def write_table(cls):
        items = [i for i in range(len(cls.ITEMS))]
        for item in cls.ITEMS.values():
            items[item.my_id] = item
        for item in items:
            write_u64(item.offset)

    @staticmethod
    def get_name_from_bobj(bobj):
        return bobj.name

    @classmethod
    def read(cls, bobj):
        name = cls.get_name_from_bobj(bobj)
        if not name.startswith(cls.PREFIX):
            return None
        if name in cls.ITEMS:
            return None
        cc = None
        for c in cls.CHILDREN:
            if name.startswith(c.PREFIX):
                cc = c
                break
        if cc is None:
            terminate("Type not found. ", cls.DESC, ":", bobj.name)
        return cc(bobj)

    @classmethod
    def init(cls):
        cls.LAST_ID = 0
        cls.ITEMS = dict()


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
            super().__init__(bobj)
        else:
            self.origin_instance = self.ITEMS[origin_name]
            self.name = bobj.name
            self.my_id = origin.my_id
            self.offset = 0
            self.bobj = bobj

    def write(self):
        super().write()
        if self.origin_instance is not None:
            GX3D_FILE.write(TYPE_U64(self.origin_instance.my_id))

    @classmethod
    def read(cls, bobj):
        if not bobj.name.startswith(cls.PREFIX):
            return None
        origin_name = get_origin_name(bobj)
        if origin_name is None:
            return super().read(bobj)
        super().read(bobj[origin_name])
        cc = None
        for c in cls.CHILDREN:
            if bobj.name.startswith(c.PREFIX):
                cc = c
                break
        if cc is None:
            terminate("Type not found. ", cls.DESC, ":", bobj.name)
        return cc(bobj)


class ReferenceableObject(RenderObject):
    # It is going to implement those objects:
    #     Have a same data in all object

    def __init__(self, bobj):
        self.name = self.get_name_from_bobj(bobj)
        if self.name not in self.ITEMS:
            return super().__init__(bobj)
        self.my_id = origin.my_id
        self.offset = 0
        self.bobj = bobj

    @classmethod
    def read(cls, bobj):
        if not bobj.name.startswith(cls.PREFIX):
            return None
        name = self.get_name_from_bobj(bobj)
        if self.name not in cls.ITEMS:
            return super().read(bobj)
        cc = None
        for c in cls.CHILDREN:
            if bobj.name.startswith(c.PREFIX):
                cc = c
                break
        if cc is None:
            terminate("Type not found. ", cls.DESC, ":", bobj.name)
        return cc(bobj)


class Audio(ReferenceableObject):
    PREFIX = 'aud-'
    LAST_ID = 0
    ITEMS = dict()  # name: instance
    DESC = "Audio"
    CHILDREN = []
    MY_TYPE = 0
    TYPE_MUSIC = 1
    TYPE_OBJECT = 2

    def __init__(self, bobj):
        super().__init__(bobj)
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


class MusicAudio(Audio):
    PREFIX = Audio.PREFIX + 'music-'
    DESC = "Music object"
    MY_TYPE = Audio.TYPE_MUSIC

    def __init__(self, bobj):
        super().__init__(bobj)


Audio.CHILDREN.append(MusicAudio)


class Light(RenderObject):
    PREFIX = 'light-'
    LAST_ID = 0
    ITEMS = dict()  # name: instance
    DESC = "Light"
    CHILDREN = []
    MY_TYPE = 0
    TYPE_SUN = 1

    def __init__(self, bobj):
        super().__init__(bobj)
        if self.bobj.type != 'LAMP':
            terminate('Light type is incorrect:', bobj.name)

    def write(self):
        super().write()
        write_vector(self.bobj.location)
        write_vector(self.bobj.rotation_euler)
        write_vector(self.bobj.data.color)
        write_float(self.bobj['near'])
        write_float(self.bobj['far'])
        write_float(self.bobj['size'])


class SunLight(Light):
    PREFIX = Light.PREFIX + 'sun-'
    DESC = "Sun light"
    MY_TYPE = Light.TYPE_SUN

    def __init__(self, bobj):
        super().__init__(bobj)
        if self.bobj.data.type != 'SUN':
            terminate('Light type is incorrect:', bobj.name)


Light.CHILDREN.append(SunLight)


class Camera(RenderObject):
    PREFIX = 'cam-'
    LAST_ID = 0
    ITEMS = dict()  # name: instance
    DESC = "Camera"
    CHILDREN = []
    MY_TYPE = 0
    TYPE_PERSPECTIVE = 1
    TYPE_ORTHOGRAPHIC = 2

    def __init__(self, bobj):
        super().__init__(bobj)
        if self.bobj.type != 'CAMERA':
            terminate('Camera type is incorrect:', bobj.name)

    def write(self):
        super().write()
        cam = self.bobj.data
        write_vector(self.bobj.location)
        write_vector(self.bobj.rotation_euler)
        write_float(cam.clip_start)
        write_float(cam.clip_end)


class PerspectiveCamera(Camera):
    PREFIX = Camera.PREFIX + 'pers-'
    DESC = "Perspective camera"
    MY_TYPE = Camera.TYPE_PERSPECTIVE

    def __init__(self, bobj):
        super().__init__(bobj)
        if self.bobj.data.type != 'PERSP':
            terminate('Camera type is incorrect:', bobj.name)

    def write(self):
        super().write()
        cam = self.bobj.data
        write_float(cam.angle_x / 2.0)


Camera.CHILDREN.append(PerspectiveCamera)


class OrthographicCamera(Camera):
    PREFIX = Camera.PREFIX + 'ortho-'
    DESC = "Orthographic camera"
    MY_TYPE = Camera.TYPE_ORTHOGRAPHIC

    def __init__(self, bobj):
        super().__init__(bobj)
        if self.bobj.data.type != 'ORTHO':
            terminate('Camera type is incorrect:', bobj.name)

    def write(self):
        super().write()
        cam = self.bobj.data
        write_float(cam.ortho_scale / 2.0)


Camera.CHILDREN.append(OrthographicCamera)


class Constraint:

    PLACER = TYPE_U64(1)
    TRACKER = TYPE_U64(2)
    SPRING = TYPE_U64(3)
    SPRING_JOINT = TYPE_U64(4)


class Placer:
    PARENT = Constraint
    PREFIX = "placer-"
    DESC = "Placer object"
    BTYPE = "EMPTY"
    ATT_X_MIDDLE = 'x-middle'  # 0
    ATT_Y_MIDDLE = 'y-middle'  # 1
    ATT_X_RIGHT = 'x-right'  # 2
    ATT_X_LEFT = 'x-left'  # 3
    ATT_Y_UP = 'y-up'  # 4
    ATT_Y_DOWN = 'y-down'  # 5
    ATT_RATIO = 'ratio'
    LAST_ID = 0
    ITEMS = dict()  # name: instance

    def __init__(self, obj, gear):
        if not obj.name.startswith(self.PREFIX):
            gear.show(self.DESC + " name didn't start with " + self.PREFIX +
                      " in object: " + obj.name)
        if obj.type != self.BTYPE:
            gear.show(self.DESC + " type must be " + self.BTYPE +
                      " in object: " + obj.name)
        if gear.has_transformation(obj):
            gear.show(self.DESC + " should not have any transformation, " +
                      "in object: " + obj.name)
        if len(obj.children) < 1:
            gear.show(self.DESC + " must have more than 0 children, " +
                      "in object: " + obj.name)
        for c in obj.children:
            if not c.name.startswith(gear.STRING_MODEL + "-"):
                gear.show(self.DESC + " can only have model as its " +
                          "child, in object: " + obj.name)
        self.attrs = [None for i in range(6)]
        if self.ATT_X_MIDDLE in obj:
            self.attrs[0] = obj[self.ATT_X_MIDDLE]
            gear.limit_check(self.attrs[0], 0.8, 0.0, obj)
        if self.ATT_Y_MIDDLE in obj:
            gear.show("Not implemented, in object: " + obj.name)
        if self.ATT_X_LEFT in obj:
            gear.show("Not implemented, in object: " + obj.name)
        if self.ATT_X_RIGHT in obj:
            gear.show("Not implemented, in object: " + obj.name)
        if self.ATT_Y_UP in obj:
            gear.show("Not implemented, in object: " + obj.name)
        if self.ATT_Y_DOWN in obj:
            self.attrs[5] = obj[self.ATT_Y_DOWN]
            gear.limit_check(self.attrs[5], 0.8, 0.0, obj)
        if self.ATT_RATIO in obj:
            self.ratio = obj[self.ATT_RATIO]
        else:
            gear.show(self.DESC + " must have " + self.ATT_RATIO +
                      " properties, in object: " + obj.name)
        self.type_id = 0
        for i in range(len(self.attrs)):
            if self.attrs[i] is not None:
                self.type_id |= (1 << i)
        print(self.type_id)
        if self.type_id not in {33, }:
            gear.show(self.DESC + " must have meaningful combination, " +
                      "in object: " + obj.name)
        self.obj = obj
        self.my_id = self.LAST_ID
        self.offset = 0
        self.LAST_ID += 1
        self.gear = gear

    def write(self):
        self.gear.log(self.DESC + " is being written with offset: " + str(
            self.offset))
        self.gear.out.write(Constraint.PLACER)
        self.gear.out.write(TYPE_U64(self.type_id))
        self.gear.out.write(TYPE_FLOAT(self.ratio))
        if self.type_id == 33:
            self.gear.out.write(TYPE_FLOAT(self.attrs[0]))
            self.gear.out.write(TYPE_FLOAT(self.attrs[5]))
        else:
            self.show("It is not implemented, in object: " + obj.name)
        childrenids = []
        for c in self.obj.children:
            childrenids.append(self.gear.models[c.name][1])
        childrenids.sort()
        self.gear.write_u64_array(childrenids)

    @classmethod
    def read(cls, obj, gear):
        if not obj.name.startswith(cls.PREFIX):
            return
        if obj.name in cls.ITEMS:
            return
        cls.ITEMS[obj.name] = Placer(obj, gear)

    @classmethod
    def init(cls):
        cls.LAST_ID = 0
        cls.ITEMS = dict()  # name: instance


Constraint.CHILDREN = [Placer]


class Collider:
    GHOST = TYPE_U64(1)
    MESH = TYPE_U64(2)
    PREFIX = 'collider-'
    CHILDREN = []

    def __init__(self, obj, gear):
        if not obj.name.startswith(self.PREFIX):
            gear.show("Collider object name is wrong. In: " + obj.name)
        self.obj = obj
        self.gear = gear

    def write(self):
        pass

    @classmethod
    def read(cls, pobj, gear):
        collider_object = None
        found = 0
        for c in pobj.children:
            if c.name.startswith(cls.PREFIX):
                found += 1
                collider_object = c
        if found > 1:
            cls.show("More than one collider is acceptable. " + "In model: " +
                     pobj.name)
        if found == 0:
            return GhostCollider(gear)
        if collider_object.name.startswith(MeshCollider.PREFIX):
            return MeshCollider(collider_object, gear)
        gear.show("Collider type not recognized in model: " + pobj.name)


class GhostCollider:
    PARENT = Collider

    def __init__(self, gear):
        self.gear = gear
        pass

    def write(self):
        self.gear.out.write(Collider.GHOST)


Collider.CHILDREN.append(GhostCollider)


class MeshCollider:
    PARENT = Collider
    PREFIX = 'collider-mesh-'

    def __init__(self, obj, gear):
        self.obj = obj
        self.gear = gear
        if not obj.name.startswith(self.PREFIX):
            gear.show("Collider object name is wrong. In: " + obj.name)
        if obj.type != 'MESH':
            cls.show('Mesh collider must have mesh object type' + 'In model: '
                     + obj.name)
        for i in range(3):
            if obj.location[i] != 0.0 or obj.rotation_euler[i] != 0.0:
                gear.show('Mesh collider not have any transformation' +
                          obj.name)
        msh = obj.data
        self.triangles = []
        for p in msh.polygons:
            triangle = []
            if len(p.vertices) > 3:
                cls.show("Object " + obj.name + " is not triangled!")
            for i, li in zip(p.vertices, p.loop_indices):
                triangle.append(msh.vertices[i].co)
            self.triangles.append(triangle)

    def write(self):
        self.gear.out.write(Collider.MESH)
        self.gear.out.write(TYPE_U64(len(self.triangles)))
        for t in self.triangles:
            for pos in t:
                self.gear.write_vector(pos)


Collider.CHILDREN.append(MeshCollider)


class Texture(RenderObject):
    PREFIX = 'txt-'
    LAST_ID = 0
    ITEMS = dict()  # name: instance
    DESC = "Texture"
    CHILDREN = []
    MY_TYPE = 0
    TYPE_2D = 1
    TYPE_3D = 2
    TYPE_CUBE = 3
    TYPE_BACKED_ENVIRONMENT = 4

    def __init__(self, bobj):
        super().__init__(bobj)
        self.file = read_file(self.name)

    def write(self):
        super().write()
        write_file(self.file)

    @staticmethod
    def get_name_from_bobj(bobj):
        if bobj.type != 'IMAGE':
            terminate("Texture must be image: ", bobj.name)
        img = bobj.image
        if img is None:
            terminate("Image is not set in texture: ", bobj.name)
        filepath = bpy.path.abspath(bobj.image.filepath_raw).strip()
        if filepath is None or len(filepath) == 0:
            terminate("Image is not specified yet in texture: ", bobj.name)
        if not filepath.endswith(".png"):
            terminate("Use PNG image instead of ", filepath)
        return filepath


class D2Texture(Texture):
    PREFIX = Texture.PREFIX + '2d-'
    DESC = "2D texture"
    MY_TYPE = Mesh.TYPE_2D

    def __init__(self, bobj):
        super().__init__(bobj)


Texture.CHILDREN.append(D2Texture)


class CubeTexture(Texture):
    PREFIX = Texture.PREFIX + 'cube-'
    DESC = "Cube texture"
    MY_TYPE = Mesh.TYPE_CUBE

    def __init__(self, bobj):
        super().__init__(bobj)
        if not self.name.startswith('-up.png'):
            terminate('Incorrect cube texture:', bobj.name)
        base_name = self.name[:len(self.name) - len('-up.png')]
        self.img_down = read_file(base_name + '-down.png')
        self.img_left = read_file(base_name + '-left.png')
        self.img_right = read_file(base_name + '-right.png')
        self.img_front = read_file(base_name + '-front.png')
        self.img_back = read_file(base_name + '-back.png')

    def write(self):
        super().write()
        write_file(self.img_down)
        write_file(self.img_left)
        write_file(self.img_right)
        write_file(self.img_front)
        write_file(self.img_back)


Texture.CHILDREN.append(CubeTexture)


class BackedEnvironmentTexture(CubeTexture):
    PREFIX = Texture.PREFIX + 'bkenv-'
    DESC = "Backed environment texture"
    MY_TYPE = Mesh.TYPE_BACKED_ENVIRONMENT

    def __init__(self, bobj):
        super().__init__(bobj)


Texture.CHILDREN.append(BackedEnvironmentTexture)


class Shader:
    ITEMS = dict()  # int -> instance

    @classmethod
    def init(cls):
        cls.ITEMS = dict()

    @classmethod
    def read(cls, shd):
        my_id = shd.to_int()
        if my_id in cls.ITEMS:
            return None
        cls.ITEMS[my_id] = shd


class Shading:
    class Reserved(enum.Enum):
        DEPTH_POS = 0
        DEPTH_POS_NRM = 1
        DEPTH_POS_UV = 2
        DEPTH_POS_NRM_UV = 3
        MAX = 4

        def needs_normal(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return False

        def needs_uv(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return False

        def needs_tangent(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return False

        def write(self, shd):
            return

    class Lighting(enum.Enum):
        RESERVED = 0
        SHADELESS = 1
        DIRECTIONAL = 2
        NORMALMAPPED = 3
        MAX = 4

        def needs_normal(self):
            if self == self.RESERVED:
                raise Exception('I can not judge about reserved.')
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return self == self.DIRECTIONAL or self == self.NORMALMAPPED

        def needs_uv(self):
            if self == self.RESERVED:
                raise Exception('I can not judge about reserved.')
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return self == self.NORMALMAPPED

        def needs_tangent(self):
            if self == self.RESERVED:
                raise Exception('I can not judge about reserved.')
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return self == self.NORMALMAPPED

        def translate(self, gear, bmat, shd):
            found = 0
            nrm_txt = None
            for k in bmat.texture_slots.keys():
                if k.endswith('-' + gear.STRING_NRM_TEXTURE):
                    found += 1
                    nrm_txt = bmat.texture_slots[k].texture
            normal_found = False
            if found == 1:
                normal_found = True
            elif found > 1:
                gear.show("Two normal found for material" + bmat.name)
            shadeless = bmat.use_shadeless
            if shadeless and normal_found:
                gear.show(
                    "One material can not have both normal-map texture " +
                    "and have a shadeless lighting, error found in " +
                    "material: " + bmat.name)
            if shadeless:
                return self.SHADELESS
            if not normal_found:
                return self.DIRECTIONAL
            shd.normalmap = gear.read_texture_2d(nrm_txt)
            return self.NORMALMAPPED

        def write(self, shd):
            if self.NORMALMAPPED == self:
                shd.parent.out.write(TYPE_U64(shd.normalmap))

    class Texturing(enum.Enum):
        COLORED = 0
        D2 = 1
        D3 = 2
        CUBE = 3
        MAX = 4

        def needs_normal(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return False

        def needs_uv(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return self == self.D2

        def needs_tangent(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return False

        def translate(self, gear, bmat, shd):
            d2_found = 0
            d2txt = None
            d3_found = 0
            d3txt = None
            cube_found = [0 for i in range(6)]
            cubetxt = None
            for k in bmat.texture_slots.keys():
                if k.endswith('-' + gear.STRING_2D_TEXTURE):
                    d2_found += 1
                    d2txt = bmat.texture_slots[k].texture
                elif k.endswith('-' + gear.STRING_3D_TEXTURE):
                    d3_found += 1
                    d3txt = bmat.texture_slots[k].texture
                else:
                    for i in range(6):
                        stxt = '-' + gear.STRING_CUBE_TEXTURE + \
                            '-' + gear.STRING_CUBE_FACES[i]
                        if k.endswith(stxt):
                            cube_found[i] += 1
                            cubetxt = k[:len(k) - len(stxt)] + \
                                '-' + gear.STRING_CUBE_TEXTURE
            if d2_found > 1:
                gear.show(
                    "Number of 2D texture is more than 1 in material: " +
                    bmat.name)
            d2_found = d2_found == 1
            if d3_found > 1:
                gear.show(
                    "Number of 3D texture is more than 1 in material: " +
                    bmat.name)
            d3_found = d3_found == 1
            for i in range(6):
                if cube_found[i] > 1:
                    gear.show("Number of " + gear.STRING_CUBE_FACES[i] +
                              " face for cube texture is " +
                              "more than 1 in material: " + bmat.name)
                cube_found[i] = cube_found[i] == 1
            for i in range(1, 6):
                if cube_found[0] != cube_found[i]:
                    gear.show("Incomplete cube texture in material: " +
                              bmat.name)
            cube_found = cube_found[0]
            found = 0
            if d2_found:
                found += 1
            if d3_found:
                found += 1
            if cube_found:
                found += 1
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
                gear.show(
                    "Each material only can have one of 2D, 3D or Cube " +
                    "textures, Error in material: ", bmat.name)
            if d2_found:
                shd.d2 = gear.read_texture_2d(d2txt)
                return self.D2
            if d3_found:
                shd.d3 = gear.read_texture_3d(d3txt)
                return self.D3
            if cube_found:
                shd.cube = gear.read_texture_cube(bmat.texture_slots,
                                                  cubetxt)
                return self.CUBE

        def write(self, shd):
            if self.COLORED == self:
                shd.parent.write_vector(shd.diffuse_color, 4)
                return
            if self.D2 == self:
                shd.parent.out.write(TYPE_U64(shd.d2))
            if self.D3 == self:
                shd.parent.out.write(TYPE_U64(shd.d3))
            if self.CUBE == self:
                shd.parent.out.write(TYPE_U64(shd.cube))

    class Speculating(enum.Enum):
        MATTE = 0
        SPECULATED = 1
        SPECTXT = 2
        MAX = 3

        def needs_normal(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return self != self.MATTE

        def needs_uv(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return self == self.SPECTXT

        def needs_tangent(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return False

        def translate(self, gear, bmat, shd):
            found = 0
            txt = None
            for k in bmat.texture_slots.keys():
                if k.endswith('-' + gear.STRING_SPEC_TEXTURE):
                    found += 1
                    txt = bmat.texture_slots[k].texture
            if found > 1:
                gear.show(
                    "Each material only can have one secular texture, " +
                    "Error in material: ", bmat.name)
            if found == 1:
                shd.spectxt = gear.read_texture_2d(txt)
                return self.SPECTXT
            if bmat.specular_intensity > 0.001:
                shd.specular_color = bmat.specular_color
                shd.specular_factors = mathutils.Vector(
                    (0.7, 0.9, bmat.specular_intensity))
                return self.SPECULATED
            return self.MATTE

        def write(self, shd):
            if self.SPECULATED == self:
                shd.parent.write_vector(shd.specular_color)
                shd.parent.write_vector(shd.specular_factors)
                return
            if self.SPECTXT == self:
                shd.parent.out.write(TYPE_U64(shd.spectxt))

    class EnvironmentMapping(enum.Enum):
        NONREFLECTIVE = 0
        BAKED = 1
        REALTIME = 2
        MAX = 3

        def needs_normal(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return self != self.NONREFLECTIVE

        def needs_uv(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return False

        def needs_tangent(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return False

        def translate(self, gear, bmat, shd):
            baked_found = [0 for i in range(6)]
            bakedtxt = None
            for k in bmat.texture_slots.keys():
                for i in range(6):
                    stxt = '-' + gear.STRING_BAKED_ENV_TEXTURE + \
                        '-' + gear.STRING_CUBE_FACES[i]
                    if k.endswith(stxt):
                        baked_found[i] += 1
                        bakedtxt = k[:len(k) - len(stxt)] + \
                            '-' + gear.STRING_BAKED_ENV_TEXTURE
            for i in range(6):
                if baked_found[i] > 1:
                    gear.show("Number of " + gear.STRING_CUBE_FACES[i] +
                              " face for baked texture is " +
                              "more than 1 in material: " + bmat.name)
                baked_found[i] = baked_found[i] == 1
                if baked_found[0] != baked_found[i]:
                    gear.show("Incomplete cube texture in material: " +
                              bmat.name)
            baked_found = baked_found[0]
            reflective = bmat.raytrace_mirror is not None and \
                bmat.raytrace_mirror.use and \
                bmat.raytrace_mirror.reflect_factor > 0.001
            if baked_found and not reflective:
                gear.show(
                    "A material must set amount of reflectivity and " +
                    "then have a baked-env texture. Error in material: " +
                    bmat.name)
            if baked_found:
                shd.reflect_factor = bmat.raytrace_mirror.reflect_factor
                shd.bakedenv = gear.read_texture_cube(bmat.texture_slots,
                                                      bakedtxt)
                return self.BAKED
            if reflective:
                shd.reflect_factor = bmat.raytrace_mirror.reflect_factor
                return self.REALTIME
            return self.NONREFLECTIVE

        def write(self, shd):
            if self == self.BAKED or self == self.REALTIME:
                shd.parent.out.write(TYPE_FLOAT(shd.reflect_factor))
            if self == self.BAKED:
                shd.parent.out.write(TYPE_U64(shd.bakedenv))

    class Shadowing(enum.Enum):
        SHADOWLESS = 0
        CASTER = 1
        FULL = 2
        MAX = 3

        def needs_normal(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return self == self.FULL

        def needs_uv(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return False

        def needs_tangent(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return False

        def translate(self, gear, bmat, shd):
            caster = bmat.use_cast_shadows
            receiver = bmat.use_shadows
            if not caster and receiver:
                gear.show("A material can not be receiver but not " +
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
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return False

        def needs_uv(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return self == self.CUTOFF

        def needs_tangent(self):
            if self == self.MAX:
                raise Exception('UNEXPECTED')
            return False

        def translate(self, gear, bmat, shd):
            trn = gear.STRING_TRANSPARENT in bmat
            ctf = gear.STRING_CUTOFF in bmat
            if trn and ctf:
                gear.show("A material can not be transparent and cutoff " +
                          "in same time. Error in material: " + bmat.name)
            if trn:
                shd.transparency = bmat[gear.STRING_TRANSPARENT]
                return self.TRANSPARENT
            if ctf:
                shd.transparency = bmat[gear.STRING_CUTOFF]
                return self.CUTOFF
            return self.OPAQUE

        def write(self, shd):
            if self == self.TRANSPARENT or self == self.CUTOFF:
                shd.parent.out.write(TYPE_FLOAT(shd.transparency))

    def __init__(self, bmat=None):
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
        if bmat is None:
            self.set_reserved(self.Reserved.DEPTH_POS)
        else:
            for i in range(len(self.shading_data)):
                self.shading_data[i] = self.shading_data[i].translate(
                    parent, bmat, self)

    def set_lighting(self, e):
        if not isinstance(e, self.Lighting) or e.MAX == e:
            self.parent.show("Unexpected ", e)
        self.shading_data[0] = e

    def get_lighting(self):
        if self.is_reserved():
            return self.Lighting.MAX
        return self.shading_data[0]

    def set_texturing(self, e):
        if not isinstance(e, self.Texturing) or e.MAX == e:
            self.parent.show("Unexpected ", e)
        self.shading_data[1] = e

    def get_texturing(self):
        if self.is_reserved():
            return self.Texturing.MAX
        return self.shading_data[1]

    def set_speculating(self, e):
        if not isinstance(e, self.Speculating) or e.MAX == e:
            self.parent.show("Unexpected ", e)
        self.shading_data[2] = e

    def get_speculating(self):
        if self.is_reserved():
            return self.Speculating.MAX
        return self.shading_data[2]

    def set_environment_mapping(self, e):
        if not isinstance(e, self.EnvironmentMapping) or e.MAX == e:
            self.parent.show("Unexpected ", e)
        self.shading_data[3] = e

    def get_environment_mapping(self):
        if self.is_reserved():
            return self.EnvironmentMapping.MAX
        return self.shading_data[3]

    def set_shadowing(self, e):
        if not isinstance(e, self.Shadowing) or e.MAX == e:
            self.parent.show("Unexpected ", e)
        self.shading_data[4] = e

    def get_shadowing(self):
        if self.is_reserved():
            return self.Shadowing.MAX
        return self.shading_data[4]

    def set_transparency(self, e):
        if not isinstance(e, self.Transparency) or e.MAX == e:
            self.parent.show("Unexpected ", e)
        self.shading_data[5] = e

    def get_transparency(self):
        if self.is_reserved():
            return self.Transparency.MAX
        return self.shading_data[5]

    def set_reserved(self, e):
        if not isinstance(e, self.Reserved) or e.MAX == e:
            terminate("Unexpected ", e)
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
                # print(pre)
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
        self.parent.log("ALL ENUMS")
        for k in sorted(all_enums):
            if 'MAX' not in k:
                self.parent.log(k, "=", all_enums[k], ",")
        self.parent.log("END OF ALL ENUMS")

    def get_enum_name(self):
        result = ""
        if self.is_reserved():
            result = self.reserved.name + '_'
        else:
            for e in self.shading_data:
                result += e.name + '_'
        result = result[0:len(result) - 1]
        self.parent.log(result, ' = ', self.to_int())
        return result

    def get_file_name(self):
        result = self.get_enum_name()
        result = result.lower().replace('_', '-')
        self.parent.log(result, ' = ', self.to_int())
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

    def write(self):
        self.parent.out.write(TYPE_U64(self.to_int()))
        if self.shading_data[0] == self.Lighting.RESERVED:
            self.reserved.write(self)
            return
        for e in self.shading_data:
            e.write(self)


class Mesh(UniRenderObject):
    PREFIX = 'mesh-'
    LAST_ID = 0
    ITEMS = dict()  # name: instance
    DESC = "Mesh"
    CHILDREN = []
    MY_TYPE = 0
    TYPE_BASIC = 1

    def __init__(self, bobj):
        super().__init__(bobj)
        if bobj.type != 'MESH':
            terminate('Mesh must be of type MESH:', bobj.name)
        if has_transformation(bobj):
            terminate("Mesh must not have any transformation. in:", bobj.name)
        if len(bobj.children) != 0:
            terminate("Mesh can not have children:", bobj.name)
        self.shd = Shading(bobj.material_slots[0].material)
        if self.origin_instance in not None:
            if not self.shd.is_same(self.origin_instance.shd):
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


class BasicMesh(Mesh):
    PREFIX = Mesh.PREFIX + 'basic-'
    DESC = "Basic mesh"
    MY_TYPE = Mesh.TYPE_BASIC

    def __init__(self, bobj):
        super().__init__(bobj)


Mesh.CHILDREN.append(BasicMesh)


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
        self.radius -= center
        self.center = bobj.parent.matrix_world.inverted() * center

    @classmethod
    def read(cls, bobj):
        for c in bobj.children:
            if bobj.name.startswith(cls.PREFIX):
                return cls(bobj)
        terminate("Occlusion not found in: ", bobj.name)


class Model(RenderObject):
    PREFIX = 'model-'
    LAST_ID = 0
    ITEMS = dict()  # name: instance
    DESC = "Model"
    CHILDREN = []
    MY_TYPE = 0
    TYPE_BASIC = 1
    TYPE_WIDGET = 1

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
            ins = Model.read(c)
            if ins is not None:
                self.model_children.append(ins)
                continue
        if len(self.model_children) + len(self.meshes) < 1:
            terminate('Waste model', bobj.name)

    def write(self):
        super().write()
        self.occlusion.write()
        self.collider.write()
        write_instances_ids(self.model_children)
        write_instances_ids(self.meshes)
        for mesh in self.meshes:
            mesh.shd.write()


class BasicModel(Model):
    PREFIX = Model.PREFIX + 'basic-'
    DESC = "Basic model"
    MY_TYPE = Model.TYPE_BASIC

    def __init__(self, bobj):
        super().__init__(bobj)


Model.CHILDREN.append(BasicModel)


class WidgetModel(Model):
    PREFIX = Model.PREFIX + 'widget-'
    DESC = "Widget model"
    MY_TYPE = Model.TYPE_WIDGET

    def __init__(self, bobj):
        super().__init__(bobj)


Model.CHILDREN.append(WidgetModel)


class Scene(RenderObject):
    PREFIX = 'scene-'
    LAST_ID = 0
    ITEMS = dict()  # name: instance
    DESC = "Scene"
    CHILDREN = []
    MY_TYPE = 0
    TYPE_GAME = 1
    TYPE_UI = 2

    def __init__(self, bobj):
        super().__init__(bobj)
        self.models = []
        self.cameras = []
        self.lights = []
        self.audios = []
        self.constraints = []
        for o in bobj.objects:
            if o.parent is not None:
                continue
            ins = Model.read(o)
            if ins is not None:
                self.models.append(ins)
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

    def write(self):
        super().write()
        write_vector(self.bobj.world.ambient_color)
        write_instances_ids(self.cameras)
        write_instances_ids(self.audios)
        write_instances_ids(self.lights)
        write_instances_ids(self.models)
        write_instances_ids(self.constraints)

    @classmethod
    def read_all(cls):
        for s in bpy.data.scenes:
            super().read(s)


class GameScene(Scene):
    PREFIX = Scene.PREFIX + 'game-'
    DESC = "Game scene"
    MY_TYPE = Scene.TYPE_GAME

    def __init__(self, bobj):
        super().__init__(bobj)


Scene.CHILDREN.append(GameScene)


class UiScene(Scene):
    PREFIX = Scene.PREFIX + 'ui-'
    DESC = "UI scene"
    MY_TYPE = Scene.TYPE_UI

    def __init__(self, bobj):
        super().__init__(bobj)


Scene.CHILDREN.append(UiScene)


class Gearoenix:

    @classmethod
    def check_env(cls):
        cls.PATH_ENGINE_SDK = os.environ.get(cls.STRING_ENGINE_SDK_VAR_NAME)
        if cls.PATH_ENGINE_SDK is None:
            cls.show('"' + cls.STRING_ENGINE_SDK_VAR_NAME +
                     '" variable is not set!')
        cls.PATH_SHADERS_DIR = cls.PATH_ENGINE_SDK + '/vulkan/shaders/'
        if sys.platform == 'darwin':
            cls.PATH_SHADER_COMPILER = "xcrun"
        else:
            cls.PATH_VULKAN_SDK = os.environ.get(
                cls.STRING_VULKAN_SDK_VAR_NAME)
            if cls.PATH_VULKAN_SDK is None:
                cls.show('"' + cls.STRING_VULKAN_SDK_VAR_NAME +
                         '" variable is not set!')
                return False
            cls.PATH_SHADER_COMPILER = \
                cls.PATH_VULKAN_SDK + '/bin/glslangValidator'
        return True

    @classmethod
    def compile_shader(cls, stage, shader_name):
        tmp = cls.TmpFile()
        args = None
        if sys.platform == 'darwin':
            args = [
                cls.PATH_SHADER_COMPILER, '-sdk', 'macosx', 'metal',
                shader_name, '-o', tmp.filename
            ]
        else:
            args = [
                cls.PATH_SHADER_COMPILER, '-V', '-S', stage, shader_name, '-o',
                tmp.filename
            ]
        if subprocess.run(args).returncode != 0:
            cls.show('Shader %s can not be compiled!' % shader_name)
        if sys.platform == "darwin":
            tmp2 = tmp
            tmp = cls.TmpFile()
            args = [
                cls.PATH_SHADER_COMPILER, '-sdk', 'macosx', 'metallib',
                tmp2.filename, '-o', tmp.filename
            ]
            if subprocess.run(args).returncode != 0:
                cls.show('Shader %s can not be build!' % shader_name)
        tmp = tmp.read()
        cls.log("Shader '", shader_name, "'is compiled has length of: ",
                len(tmp))
        cls.out.write(TYPE_U64(len(tmp)))
        cls.out.write(tmp)

    @classmethod
    def write_instances_offsets(cls, clsobj):
        offsets = [i for i in range(len(clsobj.ITEMS))]
        mod_name = clsobj.__name__
        cls.rust_code.write("pub mod " + mod_name + " {\n")
        cls.cpp_code.write("namespace " + mod_name + "\n{\n")
        for name, instance in clsobj.ITEMS.items():
            offset = instance.offset
            item_id = instance.my_id
            name = cls.const_string(name)
            cls.rust_code.write("\tpub const " + name + ": u64 = " + str(
                item_id) + ";\n")
            cls.cpp_code.write("\tconst gearoenix::core::Id " + name + " = " +
                               str(item_id) + ";\n")
            offsets[item_id] = offset
        cls.rust_code.write("}\n")
        cls.cpp_code.write("}\n")
        cls.write_u64_array(offsets)

    @classmethod
    def items_offsets(cls, items, mod_name):
        offsets = [i for i in range(len(items))]
        cls.rust_code.write("pub mod " + mod_name + " {\n")
        cls.cpp_code.write("namespace " + mod_name + "\n{\n")
        for name, offset_id in items.items():
            offset, item_id = offset_id[0:2]
            cls.rust_code.write("\tpub const " + cls.const_string(name) +
                                ": u64 = " + str(item_id) + ";\n")
            cls.cpp_code.write("\tconst gearoenix::core::Id " +
                               cls.const_string(name) + " = " + str(
                                   item_id) + ";\n")
            offsets[item_id] = offset
        cls.rust_code.write("}\n")
        cls.cpp_code.write("}\n")
        return offsets

    @classmethod
    def write_all_instances(cls, clsobj):
        items = [i for i in range(len(clsobj.ITEMS))]
        for item in clsobj.ITEMS.values():
            items[item.my_id] = item
        for item in items:
            item.offset = cls.out.tell()
            item.write()

    @classmethod
    def read_materials(cls, m):
        if m.type != 'MESH':
            return
        material_count = len(m.material_slots.keys())
        if material_count == 1:
            s = cls.Shading(cls, m.material_slots[0].material)
            sid = s.to_int()
            if sid in cls.shaders:
                return
            cls.shaders[sid] = [0, s]
        else:
            cls.show("Unexpected number of materials in mesh " + m.name)

    @classmethod
    class TmpFile:
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


def write_tables(cls):
    Shader.write_table()
    Camera.write_table()
    Audio.write_table()
    Light.write_table()
    Texture.write_table()
    Mesh.write_table()
    Model.write_table()
    Constraint.write_table()
    Scene.write_table()


def initialize_shaders(cls):
    Shader.init()
    s = Shading()
    s.print_all_enums()
    s = Shading()
    s.set_reserved(Shading.Reserved.DEPTH_POS)
    Shader.read(s)
    s = Shading()
    s.set_reserved(Shading.Reserved.DEPTH_POS_NRM)
    Shader.read(s)
    s = Shading()
    s.set_reserved(Shading.Reserved.DEPTH_POS_UV)
    Shader.read(s)
    s = Shading()
    s.set_reserved(Shading.Reserved.DEPTH_POS_NRM_UV)
    Shader.read(s)


def write_file():
    initialize_shaders()
    Audio.init()
    Light.init()
    Camera.init()
    Texture.init()
    Meshe.init()
    Model.init()
    Constraint.init()
    Scene.init()
    Scene.read_all()
    write_bool(sys.byteorder == 'little')
    tables_offset = GX3D_FILE.tell()
    write_tables()
    Shader.write_all()
    Camera.write_all()
    Audio.write_all()
    Light.write_all()
    Texture.write_all()
    Mesh.write_all()
    Model.write_all()
    Constraint.write_all()
    Scene.write_all()
    GX3D_FILE.flush()
    GX3D_FILE.seek(tables_offset)
    RUST_FILE.seek(0)
    CPP_FILE.seek(0)
    write_tables()
    GX3D_FILE.flush()
    GX3D_FILE.close()
    RUST_FILE.flush()
    RUST_FILE.close()
    CPP_FILE.flush()
    CPP_FILE.close()


class GearoenixExporter(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    """This is a plug in for Gearoenix 3D file format"""
    bl_idname = "gearoenix_exporter.data_structure"
    bl_label = "Export Gearoenix 3D"
    filename_ext = ".gx3d"
    filter_glob = bpy.props.StringProperty(
        default="*.gx3d",
        options={'HIDDEN'}, )
    export_vulkan = bpy.props.BoolProperty(
        name="Enable Vulkan",
        description="This item enables data exporting for Vulkan engine.",
        default=False,
        options={'ANIMATABLE'},
        subtype='NONE',
        update=None)
    export_metal = bpy.props.BoolProperty(
        name="Enable Metal",
        description="This item enables data exporting for Metal engine.",
        default=False,
        options={'ANIMATABLE'},
        subtype='NONE',
        update=None)

    def execute(self, context):
        Gearoenix.export_vulkan = bool(self.export_vulkan)
        Gearoenix.export_metal = bool(self.export_metal)
        GX3D_FILE = open(self.filepath, mode='wb')
        RUST_FILE = open(self.filepath + ".rs", mode='w')
        CPP_FILE = open(self.filepath + ".hpp", mode='w')
        write_file()
        return {'FINISHED'}


def menu_func_export(self, context):
    self.layout.operator(
        GearoenixExporter.bl_idname,
        text="Gearoenix 3D Exporter (.gx3d)")


def register_plugin():
    bpy.utils.register_class(GearoenixExporter)
    bpy.types.INFO_MT_file_export.append(menu_func_export)


if __name__ == "__main__":
    register_plugin()
