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


class Gearoenix:
    TYPE_BOOLEAN = ctypes.c_uint8
    TYPE_OFFSET = ctypes.c_uint64
    TYPE_TYPE_ID = ctypes.c_uint64
    TYPE_SIZE = ctypes.c_uint64
    TYPE_COUNT = ctypes.c_uint64
    TYPE_BYTE = ctypes.c_uint8
    TYPE_FLOAT = ctypes.c_float
    TYPE_U32 = ctypes.c_uint32

    TEXTURE_TYPE_2D = 10
    TEXTURE_TYPE_CUBE = 20

    SPEAKER_TYPE_MUSIC = 10
    SPEAKER_TYPE_OBJECT = 20

    STRING_DYNAMIC_PART = 'dynamic-part'
    STRING_DYNAMIC_PARTED = 'dynamic-parted'
    STRING_CUTOFF = "cutoff"
    STRING_TRANSPARENT = "transparent"
    STRING_MESH = "mesh"
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

    MODE_DEBUG = True

    class Shading:
        class Reserved(enum.Enum):
            WHITE_POS = 0
            WHITE_POS_NRM = 1
            WHITE_POS_UV = 2
            WHITE_POS_NRM_UV = 3
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
                    shd.parent.out.write(
                        shd.parent.TYPE_TYPE_ID(shd.normalmap))

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
                    shd.diffuse_color = bmat.diffuse_color
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
                    shd.parent.write_vector(shd.diffuse_color)
                    return
                if self.D2 == self:
                    shd.parent.out.write(shd.parent.TYPE_TYPE_ID(shd.d2))
                if self.D3 == self:
                    shd.parent.out.write(shd.parent.TYPE_TYPE_ID(shd.d3))
                if self.CUBE == self:
                    shd.parent.out.write(shd.parent.TYPE_TYPE_ID(shd.cube))

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
                    shd.parent.out.write(shd.parent.TYPE_TYPE_ID(shd.spectxt))

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
                    shd.parent.out.write(
                        shd.parent.TYPE_FLOAT(shd.reflect_factor))
                if self == self.BAKED:
                    shd.parent.out.write(shd.parent.TYPE_TYPE_ID(shd.bakedenv))

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
                    shd.parent.out.write(
                        shd.parent.TYPE_FLOAT(shd.transparency))

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
            self.reserved = self.Reserved.WHITE_POS
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
                self.set_reserved(self.Reserved.WHITE_POS)
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
            self.parent.out.write(self.parent.TYPE_TYPE_ID(self.to_int()))
            if self.shading_data[0] == self.Lighting.RESERVED:
                self.reserved.write(self)
                return
            for e in self.shading_data:
                e.write(self)

    def __init__(self):
        pass

    class ErrorMsgBox(bpy.types.Operator):
        bl_idname = "gearoenix_exporter.message_box"
        bl_label = "Error"
        gearoenix_exporter_msg = 'Unknown Error!'

        def execute(self, context):
            self.report({'ERROR'},
                        Gearoenix.ErrorMsgBox.gearoenix_exporter_msg)
            return {'CANCELLED'}

    @classmethod
    def log(cls, *args):
        if cls.MODE_DEBUG:
            print(*args)

    @classmethod
    def show(cls, msg):
        cls.ErrorMsgBox.gearoenix_exporter_msg = msg
        bpy.ops.gearoenix_exporter.message_box()
        raise Exception(error)

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
        cls.out.write(cls.TYPE_SIZE(len(tmp)))
        cls.out.write(tmp)

    @staticmethod
    def const_string(s):
        return s.replace("-", "_").replace('/', '_').replace('.', '_').upper()

    @classmethod
    def write_bool(cls, b):
        data = 0
        if b:
            data = 1
        cls.out.write(cls.TYPE_BOOLEAN(data))

    @classmethod
    def write_vector(cls, v, element_count=3):
        for i in range(element_count):
            cls.out.write(cls.TYPE_FLOAT(v[i]))

    @classmethod
    def write_matrix(cls, matrix):
        for i in range(0, 4):
            for j in range(0, 4):
                cls.out.write(cls.TYPE_FLOAT(matrix[j][i]))

    @classmethod
    def write_offset_array(cls, arr):
        cls.out.write(cls.TYPE_COUNT(len(arr)))
        for o in arr:
            cls.out.write(cls.TYPE_OFFSET(o))

    @classmethod
    def write_shaders_table(cls):
        cls.out.write(cls.TYPE_COUNT(len(cls.shaders)))
        for shader_id, offset_obj in cls.shaders.items():
            offset, obj = offset_obj
            cls.out.write(cls.TYPE_TYPE_ID(shader_id))
            cls.out.write(cls.TYPE_OFFSET(offset))
            cls.log("Shader with id:", shader_id, "and offset:", offset)

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
                                cls.const_string(name) + " = " + str(item_id) +
                                ";\n")
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
                cls.out.write(cls.TYPE_TYPE_ID(1))
            else:
                cls.show("Camera with type '" + cam.type +
                         "' is not supported yet.")
            cls.out.write(cls.TYPE_FLOAT(obj.location[0]))
            cls.out.write(cls.TYPE_FLOAT(obj.location[1]))
            cls.out.write(cls.TYPE_FLOAT(obj.location[2]))
            cls.out.write(cls.TYPE_FLOAT(obj.rotation_euler[0]))
            cls.out.write(cls.TYPE_FLOAT(obj.rotation_euler[1]))
            cls.out.write(cls.TYPE_FLOAT(obj.rotation_euler[2]))
            cls.out.write(cls.TYPE_FLOAT(cam.clip_start))
            cls.out.write(cls.TYPE_FLOAT(cam.clip_end))
            cls.out.write(cls.TYPE_FLOAT(cam.angle_x / 2.0))

    @classmethod
    def write_speakers(cls):
        items = [i for i in range(len(cls.speakers))]
        for name, offset_id in cls.speakers.items():
            offset, iid, ttype = offset_id_type
            items[iid] = (name, ttype)
        for name, ttype in items:
            cls.speakers[name][0] = cls.out.tell()
            cls.out.write(cls.TYPE_TYPE_ID(ttype))
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
            cls.out.write(cls.TYPE_TYPE_ID(10))
            cls.out.write(cls.TYPE_FLOAT(sun.location[0]))
            cls.out.write(cls.TYPE_FLOAT(sun.location[1]))
            cls.out.write(cls.TYPE_FLOAT(sun.location[2]))
            cls.out.write(cls.TYPE_FLOAT(sun.rotation_euler[0]))
            cls.out.write(cls.TYPE_FLOAT(sun.rotation_euler[1]))
            cls.out.write(cls.TYPE_FLOAT(sun.rotation_euler[2]))
            cls.out.write(cls.TYPE_FLOAT(sun['near']))
            cls.out.write(cls.TYPE_FLOAT(sun['far']))
            cls.out.write(cls.TYPE_FLOAT(sun['size']))
            cls.write_vector(sun.data.color)

    @classmethod
    def write_binary_file(cls, name):
        f = open(name, "rb")
        f = f.read()
        cls.out.write(cls.TYPE_COUNT(len(f)))
        cls.out.write(f)

    @classmethod
    def write_textures(cls):
        items = [i for i in range(len(cls.textures))]
        for name, offset_id_type in cls.textures.items():
            offset, iid, ttype = offset_id_type
            items[iid] = [name, ttype]
        for name, ttype in items:
            cls.textures[name][0] = cls.out.tell()
            cls.out.write(cls.TYPE_TYPE_ID(ttype))
            if ttype == cls.TEXTURE_TYPE_2D:
                cls.log("txt2-----------------------", cls.out.tell())
                cls.write_binary_file(name)
            elif ttype == cls.TEXTURE_TYPE_CUBE:
                off_offs = cls.out.tell()
                img_offs = [0, 0, 0, 0, 0]
                for o in img_offs:
                    cls.out.write(cls.TYPE_OFFSET(o))
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
                    cls.out.write(cls.TYPE_OFFSET(o))
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
    def write_meshes(cls):
        items = [i for i in range(len(cls.meshes))]
        for name, (offset, iid) in cls.meshes.items():
            items[iid] = name
        for name in items:
            cls.meshes[name][0] = cls.out.tell()
            cls.write_mesh(name)

    @classmethod
    def write_mesh(cls, name):
        obj = bpy.data.objects[name]
        shd = cls.Shading(cls, obj.material_slots[0].material)
        msh = obj.data
        nrm = shd.needs_normal()
        uv = shd.needs_uv()
        vertices = dict()
        last_index = 0
        for p in msh.polygons:
            if len(p.vertices) > 3:
                cls.show("Object " + obj.name + " is not triangled!")
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
                        cls.show("Unexpected number of uv layers in " +
                                 obj.name)
                    texco = uv_lyrs.active.data[li].uv
                    vertex.append(texco[0])
                    vertex.append(texco[1])
                vertex = tuple(vertex)
                if vertex in vertices:
                    vertices[vertex].append(last_index)
                else:
                    vertices[vertex] = [last_index]
                last_index += 1
        indices = [0 for _ in range(last_index)]
        last_index = 0
        cls.out.write(cls.TYPE_COUNT(len(vertives[0])))
        cls.out.write(cls.TYPE_COUNT(len(vertices)))
        for vertex, index_list in vertices.items():
            for e in vertex:
                cls.out.write(cls.TYPE_FLOAT(e))
            for i in index_list:
                indices[i] = last_index
            last_index += 1
        cls.out.write(cls.TYPE_COUNT(len(indices)))
        for i in indices:
            cls.out.write(cls.TYPE_U32(i))

    @classmethod
    def write_model(cls, name):
        obj = bpy.data.objects[name]
        cls.write_matrix(obj.matrix_world)
        meshes = []
        children = []
        for c in obj.children:
            if c.name.startswith(cls.STRING_MESH + '-'):
                mesh_name = c.name.strip().split('.')
                if len(mesh_name) != 2:
                    cls.show("Wrong name in: " + c.name)
                try:
                    int(mesh_name[1])
                except:
                    cls.show("Wrong name in: " + c.name)
                mesh_name = mesh_name[0]
                shd = cls.Shading(cls, c.material_slots[0].material)
                mtx = c.matrix_world
                meshes.append((cls.meshes[mesh_name][1], shd, mtx))
            else:
                children.append(c.name)
        cls.out.write(cls.TYPE_COUNT(len(meshes)))
        for m in meshes:
            m[1].write()
            cls.out.write(cls.TYPE_TYPE_ID(m[0]))
        cls.out.write(cls.TYPE_COUNT(len(children)))
        for c in children:
            cls.out.write(cls.TYPE_TYPE_ID(cls.models[c][1]))

    @classmethod
    def write_models(cls):
        items = [i for i in range(len(cls.models))]
        for name, (offset, iid) in cls.models.items():
            items[iid] = name
        for name in items:
            cls.models[name][0] = cls.out.tell()
            cls.log("model with name:", name, " and offset:",
                    cls.models[name][0])
            cls.write_model(name)

    @classmethod
    def write_scenes(cls):
        items = [i for i in range(len(cls.scenes))]
        for name, offset_id in cls.scenes.items():
            offset, iid = offset_id
            items[iid] = name
        for name in items:
            cls.scenes[name][0] = cls.out.tell()
            cls.log("offset of scene with name", name, ":",
                    cls.scenes[name][0])
            scene = bpy.data.scenes[name]
            models = []
            cameras = []
            speakers = []
            lights = []
            for o in scene.objects:
                if o.parent is not None:
                    continue
                if o.type == "MESH" and \
                        not o.name.startswith(cls.STRING_MESH + '-'):
                    models.append(cls.models[o.name][1])
                elif o.type == "CAMERA":
                    cameras.append(cls.cameras[o.name][1])
                elif o.type == "SPEAKER":
                    speakers.append(cls.speakers[o.name][1])
                elif o.type == "LAMP":
                    lights.append(cls.lights[o.name][1])
            if len(lights) > 1:
                cls.show(
                    "Currently only one light is supported in game engine")
            if len(cameras) < 1:
                cls.show("At least one camera must exist.")
            cls.out.write(cls.TYPE_COUNT(len(cameras)))
            for c in cameras:
                cls.out.write(cls.TYPE_TYPE_ID(c))
            cls.out.write(cls.TYPE_COUNT(len(speakers)))
            for s in speakers:
                cls.out.write(cls.TYPE_TYPE_ID(s))
            cls.out.write(cls.TYPE_COUNT(len(lights)))
            for l in lights:
                cls.out.write(cls.TYPE_TYPE_ID(l))
            cls.out.write(cls.TYPE_COUNT(len(models)))
            for m in models:
                cls.out.write(cls.TYPE_TYPE_ID(m))
            cls.write_vector(scene.world.ambient_color, 3)

    @classmethod
    def read_mesh(cls, o):
        if o.type != 'MESH':
            return
        if not o.name.startswith(cls.STRING_MESH + "-"):
            return
        if len(o.name.strip().split(".")) == 2:
            try:
                return int(o.name.strip().split(".")[1])
            except:
                pass
        if o.parent is not None:
            cls.show("Mesh can not have parent: " + o.name)
        if len(o.children) != 0:
            cls.show("Mesh can not have children: " + o.name)
        if o.matrix_world != mathutils.Matrix():
            cls.show("Mesh must have identity transformation: "+ o.name)
        if o.name not in cls.meshes:
            cls.meshes[o.name] = [0, cls.last_mesh_id]
            cls.last_mesh_id += 1
            cls.read_materials(o)

    @classmethod
    def read_texture(cls, t) -> str:
        """It checks the correctness of a texture and returns its file path."""
        if t.type != 'IMAGE':
            cls.show("Only image textures is supported, please correct: " +
                     t.name)
        img = t.image
        if img is None:
            cls.show("Image is not set in texture: " + t.name)
        filepath = bpy.path.abspath(img.filepath_raw).strip()
        if filepath is None or len(filepath) == 0:
            cls.show("Image is not specified yet in texture: " + t.name)
        if not filepath.endswith(".png"):
            cls.show("Use PNG image instead of " + filepath)
        return filepath

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
    def read_model(cls, m):
        if m.type != 'MESH':
            return
        if m.name.startswith(cls.STRING_MESH + "-"):
            return
        if m.name in cls.models:
            return
        if len(m.children) == 0:
            cls.show("Model can not have no children: " + m.name)
        cls.models[m.name] = [0, cls.last_model_id]
        cls.last_model_id += 1

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
    def read_scenes(cls):
        for s in bpy.data.scenes:
            if s.name in cls.scenes:
                continue
            for o in s.objects:
                cls.read_mesh(o)
            for o in s.objects:
                if o.type == 'CAMERA':
                    cls.read_camera(o)
            for o in s.objects:
                if o.type == 'LAMP':
                    cls.read_light(o)
            for o in s.objects:
                if o.type == 'SPEAKER':
                    cls.read_speaker(o)
            for o in s.objects:
                cls.read_model(o)
            cls.scenes[s.name] = [0, cls.last_scene_id]
            cls.last_scene_id += 1

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
        cls.write_offset_array(cls.cameras_offsets)
        cls.write_offset_array(cls.speakers_offsets)
        cls.write_offset_array(cls.lights_offsets)
        cls.write_offset_array(cls.textures_offsets)
        cls.write_offset_array(cls.meshes_offsets)
        cls.write_offset_array(cls.models_offsets)
        cls.write_offset_array(cls.scenes_offsets)

    @classmethod
    def initialize_shaders(cls):
        s = cls.Shading(cls)
        s.print_all_enums()
        cls.shaders = dict()  # Id<discret>: [offset, obj]
        s = cls.Shading(cls)
        s.set_reserved(cls.Shading.Reserved.WHITE_POS)
        cls.shaders[s.to_int()] = [0, s]
        s = cls.Shading(cls)
        s.set_reserved(cls.Shading.Reserved.WHITE_POS_NRM)
        cls.shaders[s.to_int()] = [0, s]
        s = cls.Shading(cls)
        s.set_reserved(cls.Shading.Reserved.WHITE_POS_UV)
        cls.shaders[s.to_int()] = [0, s]
        s = cls.Shading(cls)
        s.set_reserved(cls.Shading.Reserved.WHITE_POS_NRM_UV)
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
