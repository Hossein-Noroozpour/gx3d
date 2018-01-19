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


Collider.CHILDREN = [GhostCollider, MeshCollider]


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

    def __init__(self, bobj):
        super().__init__(bobj)

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

    def __init__(self, parent, bmat=None):
        self.parent = parent
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
            self.parent.show("Unexpected ", e)
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

    def write(self):
        super().write()
        self.occlusion.write()
        self.collider.write()
        write_instances_ids(self.model_children)
        write_instances_ids(self.meshes)
        for mesh in self.meshes:
            mesh.shd.write()


class BasicModel:
    PREFIX = Model.PREFIX + 'basic-'
    DESC = "Basic model"
    MY_TYPE = Model.TYPE_BASIC

    def __init__(self, bobj):
        super().__init__(bobj)


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
            if super().read(s) in not None:
                continue
            else:
                terminate("Unexpected scene", s.name)


class GameScene(Scene):
    PREFIX = Scene.PREFIX + 'game-'
    DESC = "Game scene"
    MY_TYPE = Scene.TYPE_GAME

    def __init__(self, bobj):
        super().__init__(bobj)

    def write(self):
        super().write()


Scene.CHILDREN.append(GameScene)


class UiScene(Scene):
    PREFIX = Scene.PREFIX + 'ui-'
    DESC = "UI scene"
    MY_TYPE = Scene.TYPE_UI

    def __init__(self, bobj):
        super().__init__(bobj)
        # todo add widget class for ui

    def write(self):
        super().write()
        # todo add widget class for ui


Scene.CHILDREN.append(UiScene)


class Gearoenix:

    TEXTURE_TYPE_2D = 10
    TEXTURE_TYPE_CUBE = 20

    SPEAKER_TYPE_MUSIC = 10
    SPEAKER_TYPE_OBJECT = 20

    STRING_DYNAMIC_PART = 'dynamic-part'
    STRING_DYNAMIC_PARTED = 'dynamic-parted'
    STRING_CUTOFF = "cutoff"
    STRING_OCCLUSION = "occlusion"
    STRING_TRANSPARENT = "transparent"
    STRING_MESH = "mesh"
    STRING_MODEL = "model"
    STRING_ENGINE_SDK_VAR_NAME = 'GEAROENIX_SDK'
    STRING_VULKAN_SDK_VAR_NAME = 'VULKAN_SDK'
    STRING_COPY_POSTFIX_FORMAT = '.NNN'
    STRING_2D_TEXTURE = '2d'
    STRING_3D_TEXTURE = '3d'
    STRING_CUBE_TEXTURE = 'cube'
    STRING_NRM_TEXTURE = 'normal'
    STRING_SPEC_TEXTURE = 'spectxt'
    STRING_BAKED_ENV_TEXTURE = 'baked'
    STRING_CUBE_FACES = ["up", "down", "left", "right", "front", "back"]

    PATH_ENGINE_SDK = None
    PATH_GEAROENIX_SDK = None
    PATH_SHADERS_DIR = None
    PATH_SHADER_COMPILER = None

    @classmethod
    def limit_check(cls, val, maxval=1.0, minval=0.0, obj=None):
        if val > maxval or val < minval:
            msg = "Out of range value"
            if obj is not None:
                msg += " in object: " + obj.name
            cls.show(msg)

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
    def write_bool(cls, b):
        data = 0
        if b:
            data = 1
        cls.out.write(TYPE_BOOLEAN(data))

    @classmethod
    def write_shaders_table(cls):
        cls.out.write(TYPE_U64(len(cls.shaders)))
        for shader_id, offset_obj in cls.shaders.items():
            offset, obj = offset_obj
            cls.out.write(TYPE_U64(shader_id))
            cls.out.write(TYPE_U64(offset))
            cls.log("Shader with id:", shader_id, "and offset:", offset)

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
    def gather_cameras_offsets(cls):
        cls.cameras_offsets = cls.items_offsets(cls.cameras, "camera")

    @classmethod
    def gather_speakers_offsets(cls):
        cls.speakers_offsets = cls.items_offsets(cls.speakers, "speaker")

    @classmethod
    def gather_lights_offsets(cls):
        cls.lights_offsets = cls.items_offsets(cls.lights, "light")

    @classmethod
    def gather_textures_offsets(cls):
        cls.textures_offsets = cls.items_offsets(cls.textures, "texture")

    @classmethod
    def gather_meshes_offsets(cls):
        cls.meshes_offsets = cls.items_offsets(cls.meshes, "mesh")

    @classmethod
    def gather_models_offsets(cls):
        cls.models_offsets = cls.items_offsets(cls.models, "model")

    @classmethod
    def gather_scenes_offsets(cls):
        cls.scenes_offsets = cls.items_offsets(cls.scenes, "scene")

    @classmethod
    def write_shaders(cls):
        for shader_id in cls.shaders.keys():
            file_name = cls.shaders[shader_id][1].get_file_name()
            cls.shaders[shader_id][0] = cls.out.tell()
            if cls.export_metal:
                cls.show("TODO implementation changed")
                file_name = 'metal/' + file_name + '-%s.metal'
                file_name = cls.PATH_SHADERS_DIR + file_name
                cls.compile_shader('vert', file_name % 'vert')
                cls.compile_shader('frag', file_name % 'frag')
            elif cls.export_vulkan:
                cls.show("TODO implementation changed")
                file_name = 'vulkan/' + file_name + '.%s'
                file_name = cls.PATH_SHADERS_DIR + file_name
                cls.compile_shader('vert', file_name % 'vert')
                cls.compile_shader('frag', file_name % 'frag')

    @classmethod
    def write_cameras(cls):
        items = [i for i in range(len(cls.cameras))]
        for name, offset_id in cls.cameras.items():
            offset, iid = offset_id
            items[iid] = name
        for name in items:
            obj = bpy.data.objects[name]
            cam = obj.data
            cls.cameras[name][0] = cls.out.tell()
            if cam.type == 'PERSP':
                cls.out.write(TYPE_U64(1))
            elif cam.type == 'ORTHO':
                cls.out.write(TYPE_U64(2))
            else:
                cls.show("Camera with type '" + cam.type +
                         "' is not supported yet.")
            cls.out.write(TYPE_FLOAT(obj.location[0]))
            cls.out.write(TYPE_FLOAT(obj.location[1]))
            cls.out.write(TYPE_FLOAT(obj.location[2]))
            cls.out.write(TYPE_FLOAT(obj.rotation_euler[0]))
            cls.out.write(TYPE_FLOAT(obj.rotation_euler[1]))
            cls.out.write(TYPE_FLOAT(obj.rotation_euler[2]))
            cls.out.write(TYPE_FLOAT(cam.clip_start))
            cls.out.write(TYPE_FLOAT(cam.clip_end))
            if cam.type == 'PERSP':
                cls.out.write(TYPE_FLOAT(cam.angle_x / 2.0))
            elif cam.type == 'ORTHO':
                cls.out.write(TYPE_FLOAT(cam.ortho_scale / 2.0))

    @classmethod
    def write_speakers(cls):
        items = [i for i in range(len(cls.speakers))]
        for name, offset_id in cls.speakers.items():
            offset, iid, ttype = offset_id_type
            items[iid] = (name, ttype)
        for name, ttype in items:
            cls.speakers[name][0] = cls.out.tell()
            cls.out.write(TYPE_U64(ttype))
            cls.write_binary_file(name)

    @classmethod
    def write_lights(cls):
        items = [i for i in range(len(cls.lights))]
        for name, offset_id in cls.lights.items():
            offset, iid = offset_id
            items[iid] = name
        for name in items:
            sun = bpy.data.objects[name]
            cls.lights[name][0] = cls.out.tell()
            # This is temporary, only for keeping the design
            cls.out.write(TYPE_U64(10))
            cls.out.write(TYPE_FLOAT(sun.location[0]))
            cls.out.write(TYPE_FLOAT(sun.location[1]))
            cls.out.write(TYPE_FLOAT(sun.location[2]))
            cls.out.write(TYPE_FLOAT(sun.rotation_euler[0]))
            cls.out.write(TYPE_FLOAT(sun.rotation_euler[1]))
            cls.out.write(TYPE_FLOAT(sun.rotation_euler[2]))
            cls.out.write(TYPE_FLOAT(sun['near']))
            cls.out.write(TYPE_FLOAT(sun['far']))
            cls.out.write(TYPE_FLOAT(sun['size']))
            cls.write_vector(sun.data.color)

    @classmethod
    def write_binary_file(cls, name):
        f = open(name, "rb")
        f = f.read()
        cls.out.write(TYPE_U64(len(f)))
        cls.out.write(f)

    @classmethod
    def write_textures(cls):
        items = [i for i in range(len(cls.textures))]
        for name, offset_id_type in cls.textures.items():
            offset, iid, ttype = offset_id_type
            items[iid] = [name, ttype]
        for name, ttype in items:
            cls.textures[name][0] = cls.out.tell()
            cls.out.write(TYPE_U64(ttype))
            if ttype == cls.TEXTURE_TYPE_2D:
                cls.log("txt2-----------------------", cls.out.tell())
                cls.write_binary_file(name)
            elif ttype == cls.TEXTURE_TYPE_CUBE:
                off_offs = cls.out.tell()
                img_offs = [0, 0, 0, 0, 0]
                for o in img_offs:
                    cls.out.write(TYPE_U64(o))
                name = name.strip()
                raw_name = name[:len(name) - len("-up.png")]
                cls.write_binary_file(raw_name + "-up.png")
                img_offs[0] = cls.out.tell()
                cls.write_binary_file(raw_name + "-down.png")
                img_offs[1] = cls.out.tell()
                cls.write_binary_file(raw_name + "-left.png")
                img_offs[2] = cls.out.tell()
                cls.write_binary_file(raw_name + "-right.png")
                img_offs[3] = cls.out.tell()
                cls.write_binary_file(raw_name + "-front.png")
                img_offs[4] = cls.out.tell()
                cls.write_binary_file(raw_name + "-back.png")
                off_end = cls.out.tell()
                cls.out.seek(off_offs)
                for o in img_offs:
                    cls.out.write(TYPE_U64(o))
                cls.out.seek(off_end)

            else:
                cls.show("Unexpected texture type:", ttype)

    @staticmethod
    def check_uint(s):
        try:
            if int(s) >= 0:
                return True
        except ValueError:
            return False
        return False

    @classmethod
    def write_all_instances(cls, clsobj):
        items = [i for i in range(len(clsobj.ITEMS))]
        for item in clsobj.ITEMS.values():
            items[item.my_id] = item
        for item in items:
            item.offset = cls.out.tell()
            item.write()

    @classmethod
    def read_texture_cube(cls, slots, tname):
        """It checks the correctness of a 2d texture and add its
        up face to the textures and returns id"""
        t = slots[tname + '-' + cls.STRING_CUBE_FACES[0]].texture
        filepath = cls.read_texture(t)
        for i in range(1, 6):
            cls.read_texture(
                slots[tname + '-' + cls.STRING_CUBE_FACES[i]].texture)
        if filepath in cls.textures:
            if cls.textures[filepath][2] != cls.TEXTURE_TYPE_CUBE:
                cls.show("You have used a same image in two " +
                         "defferent texture type in " + t.name)
            else:
                return cls.textures[filepath][1]
        else:
            cls.textures[filepath] = [
                0, cls.last_texture_id, cls.TEXTURE_TYPE_CUBE
            ]
            tid = cls.last_texture_id
            cls.last_texture_id += 1
            return tid

    @classmethod
    def read_texture_2d(cls, t):
        """It checks the correctness of a 2d texture and add it
        to the textures and returns id"""
        filepath = cls.read_texture(t)
        if filepath in cls.textures:
            if cls.textures[filepath][2] != cls.TEXTURE_TYPE_2D:
                cls.show("You have used a same image in two defferent " +
                         "texture type in " + t.name)
            else:
                return cls.textures[filepath][1]
        else:
            cls.textures[filepath] = \
                [0, cls.last_texture_id, cls.TEXTURE_TYPE_2D]
            tid = cls.last_texture_id
            cls.last_texture_id += 1
            return tid

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
    def read_light(cls, o):
        l = o.data
        if l.type != 'SUN':
            cls.show("Only sun light is supported, change " + l.name)
        if l.name not in cls.lights:
            cls.lights[l.name] = [0, cls.last_light_id]
            cls.last_light_id += 1

    @classmethod
    def read_camera(cls, c):
        if c.name not in cls.cameras:
            cls.cameras[c.name] = [0, cls.last_camera_id]
            cls.last_camera_id += 1

    @classmethod
    def read_speaker(cls, s):
        speaker_type = cls.SPEAKER_TYPE_OBJECT
        if s.parent is None:
            speaker_type = cls.SPEAKER_TYPE_MUSIC
        name = bpy.path.abspath(s.data.sound.filepath)
        if name in cls.speakers:
            if cls.speakers[name][2] != speaker_type:
                cls.show("Same file for two different speaker, file: " + name)
        else:
            cls.speakers[name] = [0, cls.last_speaker_id, speaker_type]
            cls.last_speaker_id += 1

    @classmethod
    def write_tables(cls):
        cls.write_shaders_table()
        cls.gather_cameras_offsets()
        cls.gather_speakers_offsets()
        cls.gather_lights_offsets()
        cls.gather_textures_offsets()
        cls.gather_meshes_offsets()
        cls.gather_models_offsets()
        cls.gather_scenes_offsets()
        cls.write_u64_array(cls.cameras_offsets)
        cls.write_u64_array(cls.speakers_offsets)
        cls.write_u64_array(cls.lights_offsets)
        cls.write_u64_array(cls.textures_offsets)
        cls.write_u64_array(cls.meshes_offsets)
        cls.write_u64_array(cls.models_offsets)
        cls.write_instances_offsets(Placer)
        cls.write_u64_array(cls.scenes_offsets)

    @classmethod
    def initialize_shaders(cls):
        s = cls.Shading(cls)
        s.print_all_enums()
        cls.shaders = dict()  # Id<discret>: [offset, obj]
        s = cls.Shading(cls)
        s.set_reserved(cls.Shading.Reserved.DEPTH_POS)
        cls.shaders[s.to_int()] = [0, s]
        s = cls.Shading(cls)
        s.set_reserved(cls.Shading.Reserved.DEPTH_POS_NRM)
        cls.shaders[s.to_int()] = [0, s]
        s = cls.Shading(cls)
        s.set_reserved(cls.Shading.Reserved.DEPTH_POS_UV)
        cls.shaders[s.to_int()] = [0, s]
        s = cls.Shading(cls)
        s.set_reserved(cls.Shading.Reserved.DEPTH_POS_NRM_UV)
        cls.shaders[s.to_int()] = [0, s]

    @classmethod
    def write_file(cls):
        cls.initialize_shaders()
        cls.textures = dict()  # filepath: [offest, id<con>, type]
        cls.last_texture_id = 0
        cls.scenes = dict()  # name: [offset, id<con>]
        cls.last_scene_id = 0
        cls.meshes = dict()  # name: [offset, id<con>]
        cls.last_mesh_id = 0
        cls.models = dict()  # name: [offset, id<con>]
        cls.last_model_id = 0
        cls.cameras = dict()  # name: [offset, id<con>]
        cls.last_camera_id = 0
        cls.lights = dict()  # name: [offset, id<con>]
        cls.last_light_id = 0
        cls.speakers = dict()  # name: [offset, id<con>, type]
        cls.last_speaker_id = 0
        Placer.init()
        cls.read_scenes()
        cls.write_bool(sys.byteorder == 'little')
        tables_offset = cls.out.tell()
        cls.write_tables()
        cls.write_shaders()
        cls.write_cameras()
        cls.write_speakers()
        cls.write_lights()
        cls.write_textures()
        cls.write_meshes()
        cls.write_models()
        cls.write_all_instances(Placer)
        cls.write_scenes()
        cls.out.flush()
        cls.out.seek(tables_offset)
        cls.rust_code.seek(0)
        cls.cpp_code.seek(0)
        cls.write_tables()
        cls.out.flush()
        cls.out.close()
        cls.rust_code.flush()
        cls.rust_code.close()
        cls.cpp_code.flush()
        cls.cpp_code.close()

    class Exporter(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
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
            if self.export_vulkan or self.export_metal:
                Gearoenix.check_env()
            try:
                Gearoenix.export_vulkan = bool(self.export_vulkan)
                Gearoenix.export_metal = bool(self.export_metal)
                Gearoenix.out = open(self.filepath, mode='wb')
                Gearoenix.rust_code = open(self.filepath + ".rs", mode='w')
                Gearoenix.cpp_code = open(self.filepath + ".hpp", mode='w')
            except:
                cls.show('file %s can not be opened!' % self.filepath)
            Gearoenix.write_file()
            return {'FINISHED'}

    def menu_func_export(self, context):
        self.layout.operator(
            Gearoenix.Exporter.bl_idname, text="Gearoenix 3D Exporter (.gx3d)")

    @classmethod
    def register(cls):
        bpy.utils.register_class(cls.ErrorMsgBox)
        bpy.utils.register_class(cls.Exporter)
        bpy.types.INFO_MT_file_export.append(cls.menu_func_export)

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


if __name__ == "__main__":
    Gearoenix.register()
