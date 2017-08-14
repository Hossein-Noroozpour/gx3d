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

    # Shader ID bytes
    #     0-(light-mode) white: 0, solid: 1, directional: 2
    #     1-(texturing) colored: 1, textured: 2
    #     2-(speculation) speculated: 1, not-speculated: 2
    #     3-(environment) nocube: 0, cubetexture: 1, realtimecube: 2
    #     4-(shadowing) shadowless: 0, full: 1, receiver: 2, caster: 3
    #     5-(trancparency) opaque:0, transparent:2, cutoff: 3,
    SHADER_PARTS_COUNT = 6

    STRING_DYNAMIC_PART = 'dynamic-part'
    STRING_DYNAMIC_PARTED = 'dynamic-parted'
    STRING_CUTOFF = "cutoff"
    STRING_TRANSPARENT = "transparent"
    STRING_VERTICES_BUFFER_SIZE = "vertices-size"
    STRING_INDICES_BUFFER_SIZE = "indices-size"
    STRING_UNIFORM_BUFFER_SIZE = "uniform-size"
    STRING_ENGINE_SDK_VAR_NAME = 'VULKUST_SDK'
    STRING_VULKAN_SDK_VAR_NAME = 'VULKAN_SDK'
    STRING_COPY_POSTFIX_FORMAT = '.NNN'
    STRING_CUBE_TEXTURE_FACES = [
        "up", "down", "left", "right", "front", "back"
    ]

    PATH_ENGINE_SDK = None
    PATH_VULKAN_SDK = None
    PATH_SHADERS_DIR = None
    PATH_SHADER_COMPILER = None

    MODE_DEBUG = True

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
            return False
        cls.PATH_SHADERS_DIR = cls.PATH_ENGINE_SDK + '/vulkust/src/shaders/'
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

    @staticmethod
    def shader_id_to_int(shd):
        i = 0
        for sh in shd:
            i <<= 8
            i |= sh
        print("shader id in int is:", i)

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
        cls.log("Shader '", shader_name,
                "'is compiled has length of: ", len(tmp))
        cls.out.write(cls.TYPE_SIZE(len(tmp)))
        cls.out.write(tmp)

    @staticmethod
    def const_string(s):
        return s.replace("-", "_").upper()

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
        for shader_id, offset in cls.shaders.items():
            if len(shader_id) != 6:
                cls.show("Unwxpected number of shader id elements in " + str(
                    shader_id))
            for i in shader_id:
                cls.out.write(cls.TYPE_BYTE(i))
            cls.out.write(cls.TYPE_OFFSET(offset))
            cls.log("Shader with id:", shader_id, "and offset:", offset)

    @classmethod
    def items_offsets(cls, items, mod_name):
        offsets = [i for i in range(len(items))]
        cls.rust_code.write("pub mod " + mod_name + " {\n")
        for name, offset_id in items.items():
            offset, item_id = offset_id[0:2]
            cls.rust_code.write("\tpub const " + cls.const_string(name) +
                                ": u64 = " + str(item_id) + ";\n")
            offsets[item_id] = offset
        cls.rust_code.write("}\n")
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
    def gather_models_offsets(cls):
        cls.models_offsets = cls.items_offsets(cls.models, "model")

    @classmethod
    def gather_scenes_offsets(cls):
        cls.scenes_offsets = cls.items_offsets(cls.scenes, "scene")

    @classmethod
    def shader_id_to_file(cls, shader_id):
        (light, txt, spec, env, shw, trn) = shader_id
        file_name = ""
        error = "shader id error"
        if light == 0:
            return "white"
        if light == 1:
            file_name += "solid-"
        elif light == 2:
            file_name += "directional-"
        else:
            cls.show(error)
        if txt == 1:
            file_name += "colored-"
        elif txt == 2:
            file_name += "textured-"
        else:
            cls.show(error)
        if spec == 1:
            file_name += "speculated-"
        elif spec == 2:
            file_name += "not-speculated-"
        else:
            cls.show(error)
        if env == 0:
            file_name += "no-"
        elif env == 1:
            file_name += "cube-texture-"
        elif env == 2:
            file_name += "realtime-cube-"
        else:
            cls.show(error)
        if shw == 0:
            file_name += "shadeless-"
        elif shw == 1:
            file_name += "full-"
        elif shw == 2:
            file_name += "receiver-"
        elif shw == 3:
            file_name += "caster-"
        else:
            cls.show(error)
        if trn == 0:
            file_name += "opaque"
        elif trn == 1:
            file_name += "transparent"
        elif trn == 2:
            file_name += "cutoff"
        else:
            cls.show(error)
        return file_name

    @classmethod
    def write_shaders(cls):
        for shader_id in cls.shaders.keys():
            file_name = cls.shader_id_to_file(shader_id)
            cls.shaders[shader_id] = cls.out.tell()
            if sys.platform == "darwin":
                file_name = 'metal/' + file_name + '-%s.metal'
            else:
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
            if cam.type != 'PERSP':
                cls.show("Camera with type '" + cam.type +
                         "' is not supported yet.")
            cls.out.write(cls.TYPE_FLOAT(cam.angle))
            cls.out.write(cls.TYPE_FLOAT(cam.clip_start))
            cls.out.write(cls.TYPE_FLOAT(cam.clip_end))
            cls.out.write(cls.TYPE_FLOAT(obj.location[0]))
            cls.out.write(cls.TYPE_FLOAT(obj.location[1]))
            cls.out.write(cls.TYPE_FLOAT(obj.location[2]))
            cls.out.write(cls.TYPE_FLOAT(obj.rotation_euler[0]))
            cls.out.write(cls.TYPE_FLOAT(obj.rotation_euler[1]))
            cls.out.write(cls.TYPE_FLOAT(obj.rotation_euler[2]))

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
            cls.out.write(cls.TYPE_FLOAT(sun['near']))
            cls.out.write(cls.TYPE_FLOAT(sun['far']))
            cls.out.write(cls.TYPE_FLOAT(sun['size']))
            cls.out.write(cls.TYPE_FLOAT(sun.location[0]))
            cls.out.write(cls.TYPE_FLOAT(sun.location[1]))
            cls.out.write(cls.TYPE_FLOAT(sun.location[2]))
            cls.out.write(cls.TYPE_FLOAT(sun.rotation_euler[0]))
            cls.out.write(cls.TYPE_FLOAT(sun.rotation_euler[1]))
            cls.out.write(cls.TYPE_FLOAT(sun.rotation_euler[2]))

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
                cls.write_binary_file(name)
            elif ttype == cls.TEXTURE_TYPE_CUBE:
                name = name.split()
                raw_name = name[:len(name) - len("-up.png")]
                cls.write_binary_file(raw_name + "-up.png")
                cls.write_binary_file(raw_name + "-down.png")
                cls.write_binary_file(raw_name + "-left.png")
                cls.write_binary_file(raw_name + "-right.png")
                cls.write_binary_file(raw_name + "-front.png")
                cls.write_binary_file(raw_name + "-back.png")

    @staticmethod
    def check_uint(s):
        try:
            if int(s) >= 0:
                return True
        except ValueError:
            return False
        return False

    @classmethod
    def assert_copied_model(cls, name):
        psf = cls.STRING_COPY_POSTFIX_FORMAT
        lpsf = len(psf)
        ln = len(name)
        if ln > lpsf and name[ln - lpsf] == psf[0] and \
                cls.check_uint(name[ln - (lpsf - 1):]):
            origin = name[:ln - lpsf]
            origin = bpy.data.objects[origin]
            if origin.parent is not None:
                cls.show("Object " + origin + " must be root because it is " +
                         "copied in " + name)
            if origin.matrix_world != mathutils.Matrix():
                cls.show("Object " + origin + " must not have any " +
                         "transformation because it is copied in " + name)
            return origin
        return None

    @classmethod
    def assert_model_name(cls, name):
        # this is True for now but in future it may change
        pass

    @staticmethod
    def material_needs_normal(shd):
        return shd[0] == 2 or shd[2] == 1 or shd[3] != 0

    @staticmethod
    def material_needs_uv(shd):
        return shd[1] == 2

    @classmethod
    def write_material_texture_ids(cls, obj, shd):
        if shd[1] != 2 and shd[3] != 1:
            return
        cube_texture = None
        texture_2d = None
        materials_count = len(obj.material_slots.keys())
        has_cube = materials_count > len(cls.STRING_CUBE_TEXTURE_FACES)
        if has_cube:
            for mat in obj.material_slots.keys():
                m = obj.material_slots[mat].material
                if has_cube and m.name.endswith(
                        "-" + cls.STRING_CUBE_TEXTURE_FACES[0]):
                    name = bpy.path.abspath(
                        m.texture_slots[0].texture.image.filepath_raw)
                    cube_texture = cls.textures[name][1]
                    continue
                sm = m.name.split("-")
                if ("-" not in m.name) or len(sm) < 2 or \
                        (sm[len(sm) - 1] not in cls.STRING_CUBE_TEXTURE_FACES):
                    name = bpy.path.abspath(
                        m.texture_slots[0].texture.image.filepath_raw)
                    texture_2d = cls.textures[name][1]
                    continue
        else:
            m = obj.material_slots[0].material
            n = bpy.path.abspath(m.texture_slots[0].texture.image.filepath_raw)
            texture_2d = cls.textures[n][1]
        if cube_texture is not None:
            cls.out.write(cls.TYPE_TYPE_ID(cube_texture))
        if texture_2d is not None:
            cls.out.write(cls.TYPE_TYPE_ID(texture_2d))

    @classmethod
    def get_info_material(cls, obj):
        slots = obj.material_slots
        materials_count = len(slots.keys())
        if materials_count == 1:
            return slots[0].material
        for mat in slots.keys():
            m = slots[mat].material
            sm = m.name.split("-")
            if ("-" not in m.name) or len(sm) < 2 or \
                    (sm[len(sm) - 1] not in cls.STRING_CUBE_TEXTURE_FACES):
                return m

    @classmethod
    def get_up_face_material(cls, obj):
        slots = obj.material_slots
        materials_count = len(slots.keys())
        if materials_count < len(cls.STRING_CUBE_TEXTURE_FACES):
            return None
        for mat in slots.keys():
            m = slots[mat].material
            if m.name.endswith("-" + cls.STRING_CUBE_TEXTURE_FACES[0]):
                return m

    @classmethod
    def write_material_data(cls, obj, shd):
        for i in shd:
            cls.out.write(cls.TYPE_BYTE(i))
        cls.write_material_texture_ids(obj, shd)
        if shd[1] == 1:
            cls.write_vector(cls.get_info_material(obj).diffuse_color)
        if shd[2] == 1:
            cls.write_vector(cls.get_info_material(obj).specular_color)
            cls.out.write(
                cls.TYPE_FLOAT(cls.get_info_material(obj).specular_intensity))
        if shd[3] != 0:
            cls.out.write(
                cls.TYPE_FLOAT(
                    cls.get_up_face_material(obj)
                    .raytrace_mirror.reflect_factor))
        if shd[5] == 2:
            info = cls.get_info_material(obj)
            cls.out.write(cls.TYPE_FLOAT(info[cls.STRING_TRANSPARENT]))
        elif shd[5] == 3:
            info = cls.get_info_material(obj)
            cls.out.write(cls.TYPE_FLOAT(info[cls.STRING_CUTOFF]))

    @classmethod
    def write_mesh(cls, obj, shd, matrix):
        cls.log("before material: ", cls.out.tell())
        cls.write_material_data(obj, shd)
        cls.log("after material: ", cls.out.tell())
        msh = obj.data
        nrm = cls.material_needs_normal(shd)
        uv = cls.material_needs_uv(shd)
        vertices = dict()
        last_index = 0
        for p in msh.polygons:
            if len(p.vertices) > 3:
                cls.show("Object " + obj.name + " is not triangled!")
            for i, li in zip(p.vertices, p.loop_indices):
                vertex = []
                v = matrix * msh.vertices[i].co
                vertex.append(v[0])
                vertex.append(v[1])
                vertex.append(v[2])
                if nrm:
                    normal = msh.vertices[i].normal
                    normal = mathutils.Vector((normal[0], normal[1], normal[2],
                                               0.0))
                    normal = matrix * normal
                    normal = normal.normalized()
                    vertex.append(normal[0])
                    vertex.append(normal[1])
                    vertex.append(normal[2])
                if uv:
                    uv_lyrs = msh.uv_layers
                    if len(uv_lyrs) > 1 or len(uv_lyrs) < 1:
                        cls.show("Unexpected number of uv layers in " +
                                 obj.name)
                    texco = uv_lyrs[0].data[li].uv
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

    @staticmethod
    def model_has_dynamic_parent(obj):
        o = obj.parent
        while o is not None:
            if cls.STRING_DYNAMIC_PART in o:
                return True
            o = o.parent
        return False

    @classmethod
    def write_model(cls, name, inv_mat_par=mathutils.Matrix()):
        obj = bpy.data.objects[name]
        dyn = cls.STRING_DYNAMIC_PART in obj
        origin = cls.assert_copied_model(name)
        is_copy = origin is not None
        cls.write_bool(is_copy)
        if is_copy:
            cls.write_matrix(obj.matrix_world)
            cls.out.write(cls.TYPE_TYPE_ID(cls.models[origin.name][1]))
            return
        cls.write_bool(dyn)
        mesh_matrix = mathutils.Matrix()
        child_inv = inv_mat_par
        if dyn:
            cls.write_matrix(obj.matrix_world)
            child_inv = obj.matrix_world.inverted()
        else:
            mesh_matrix = inv_mat_par * obj.matrix_world
        shd = cls.get_shader_id(obj)
        if obj.parent is None or dyn:
            if len(obj.children) == 0:
                cls.show("Object " + obj.name + " should not have zero " +
                         "children count")
        cls.write_mesh(obj, shd, child_inv)
        cls.out.write(cls.TYPE_COUNT(len(obj.children)))
        for c in obj.children:
            cls.write_model(c.name, child_inv)

    @classmethod
    def write_models(cls):
        items = [i for i in range(len(cls.models))]
        for name, (offset, iid) in cls.models.items():
            items[iid] = name
        for name in items:
            cls.assert_model_name(name)
            cls.models[name][0] = cls.out.tell()
            cls.log("model with name:", name,
                    " and offset:", cls.models[name][0])
            cls.write_model(name)

    @classmethod
    def write_scenes(cls):
        items = [i for i in range(len(cls.scenes))]
        for name, offset_id in cls.scenes.items():
            offset, iid = offset_id
            items[iid] = name
        for name in items:
            cls.scenes[name][0] = cls.out.tell()
            cls.log("offset of scene with name",
                    name, ":", cls.scenes[name][0])
            scene = bpy.data.scenes[name]
            models = []
            cameras = []
            speakers = []
            lights = []
            for o in scene.objects:
                if o.parent is not None:
                    continue
                if o.type == "MESH":
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
            cls.out.write(cls.TYPE_COUNT(int(
                scene[cls.STRING_VERTICES_BUFFER_SIZE])))
            cls.out.write(cls.TYPE_COUNT(int(
                scene[cls.STRING_INDICES_BUFFER_SIZE])))
            cls.out.write(cls.TYPE_COUNT(int(
                scene[cls.STRING_UNIFORM_BUFFER_SIZE])))
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

    @classmethod
    def model_has_dynamic_part(cls, m):
        has_dynamic_child = cls.STRING_DYNAMIC_PART in m and \
            m[cls.STRING_DYNAMIC_PART] == 1.0
        for c in m.children:
            has_dynamic_child = \
                has_dynamic_child or cls.model_has_dynamic_part(c)
        return has_dynamic_child

    @classmethod
    def assert_model_dynamism(cls, m):
        for c in m.children:
            cls.assert_model_dynamism(c)
        d = cls.model_has_dynamic_part(m)
        if cls.STRING_DYNAMIC_PARTED in m and \
                m[cls.STRING_DYNAMIC_PARTED] == 1.0:
            if d:
                return
            else:
                cls.show("Model: " + m.name + " has " + cls.
                         STRING_DYNAMIC_PARTED + " property but does not have "
                         + " a correct " + cls.STRING_DYNAMIC_PART + " child.")
        else:
            if d:
                cls.show("Model: " + m.name + " does not have a correct " +
                         cls.STRING_DYNAMIC_PARTED +
                         " property but has a correct " +
                         cls.STRING_DYNAMIC_PART + " child.")
            else:
                return

    @classmethod
    def assert_texture_2d(cls, t):
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
        if filepath in cls.textures:
            if cls.textures[filepath][2] != cls.TEXTURE_TYPE_2D:
                cls.show("You have used a same image in two defferent " +
                         "texture type in " + t.name)
            else:
                return
        else:
            cls.textures[filepath] = \
                [0, cls.last_texture_id, cls.TEXTURE_TYPE_2D]
            cls.last_texture_id += 1

    @classmethod
    def read_material(cls, m, environment=0):
        light_mode = 0
        if m.use_shadeless:
            light_mode = 1
        else:
            light_mode = 2
        texture_count = len(m.texture_slots.keys())
        texturing = 0
        if texture_count == 0:
            texturing = 1
        elif texture_count == 1:
            texturing = 2
            cls.assert_texture_2d(m.texture_slots[0].texture)
        else:
            cls.show("Unsupported number of textures in material: " + m.name)
        speculation = 0
        if m.specular_intensity > 0.001:
            speculation = 1
        else:
            speculation = 2
        shadowing = 0
        if m.use_cast_shadows:
            if m.use_shadows:
                shadowing = 1
            else:
                shadowing = 3
        else:
            if m.use_shadows:
                shadowing = 2
            else:
                shadowing = 0
        transparency = 0
        if "cutoff" in m:
            transparency = 3
        elif "transparent" in m:
            transparency = 2
        k = (light_mode, texturing, speculation, environment, shadowing,
             transparency)
        if k not in cls.shaders:
            cls.shaders[k] = 0
        return k

    @classmethod
    def assert_texture_cube(cls, up_txt_file):
        if up_txt_file in cls.textures:
            if cls.textures[up_txt_file][2] != cls.TEXTURE_TYPE_CUBE:
                cls.show("You have used a same image in two defferent " +
                         "texture type in " + up_txt_file)
            else:
                return
        else:
            cls.textures[up_txt_file] = \
                [0, cls.last_texture_id, cls.TEXTURE_TYPE_CUBE]
            cls.last_texture_id += 1

    @classmethod
    def assert_material_face(cls, face, m):
        if len(m.texture_slots.keys()) == 1:
            error = "Texture in material " + m.name + " is not set correctly"
            txt = m.texture_slots[0]
            if txt is None:
                cls.show(error)
            txt = txt.texture
            if txt is None:
                cls.show(error)
            img = txt.image
            if img is None:
                cls.show(error)
            img = bpy.path.abspath(img.filepath_raw).split()
            if img is None or len(img):
                cls.show(error)
            if not img.endswith(".png"):
                cls.show("Only PNG file is supported right now! change " + img)
            if not img.endswith("-" + face + ".png"):
                cls.show("File name must end with -" + face + ".png in " + img)
            if face == "up":
                cls.assert_texture_cube(img)
            return 1
        elif len(m.texture_slots.keys()) > 1:
            cls.show("Material " + m.name +
                     " has more than expected textures.")
        elif not m.raytrace_mirror.use or \
                m.raytrace_mirror.reflect_factor < 0.001:
            cls.show("Material " + m.name + " does not set reflective.")
        return 2

    @classmethod
    def read_material_slot(cls, s):
        environment = None
        for f in cls.STRING_CUBE_TEXTURE_FACES:
            found = 0
            face_mat = None
            for m in s.keys():
                mat = s[m].material
                if mat.name.endswith("-" + f):
                    face_mat = mat
                    found += 1
            if found > 1:
                cls.show("More than 1 material found with property " + f)
            if found < 1:
                cls.show("No material found with name " + f)
            face_env = cls.assert_material_face(f, face_mat)
            if environment is None:
                environment = face_env
            elif environment != face_env:
                cls.show("Material " + face_mat + " is different than others.")
        for m in s.keys():
            mat = s[m].material
            found = True
            for f in cls.STRING_CUBE_TEXTURE_FACES:
                if mat.name.endswith("-" + f):
                    found = False
                    break
            if found:
                return cls.read_material(mat, environment=environment)

    @classmethod
    def assert_model_materials(cls, m):
        if m.type != 'MESH':
            return
        for c in m.children:
            cls.assert_model_materials(c)
        if cls.STRING_DYNAMIC_PART in m:
            material_count = len(m.material_slots.keys())
            if material_count != 0:
                cls.show("Dynamic model must have occlusion mesh at its " +
                         "root that does not have any material, your '" +
                         m.name + "' model has to not have any material " +
                         "but it has " + str(material_count) + " material(s).")
            else:
                return
        if len(m.material_slots.keys()) == 1:
            cls.read_material(m.material_slots[0].material)
        elif len(m.material_slots.keys()) == 7:
            cls.read_material_slot(m.material_slots)
        else:
            cls.show("Unexpected number of materials in model " + m.name)

    @classmethod
    def get_shader_id(cls, obj):
        material_count = len(obj.material_slots.keys())
        if material_count == 0:
            return tuple([0 for _ in range(cls.SHADER_PARTS_COUNT)])
        elif material_count == 1:
            return cls.read_material(obj.material_slots[0].material)
        elif material_count == 7:
            return cls.read_material_slot(obj.material_slots)
        else:
            cls.show("Unexpected number of materials in model " + obj.name)

    @classmethod
    def read_model(cls, m):
        if m.parent is not None:
            return
        if m.name in cls.models:
            return
        cls.assert_model_dynamism(m)
        cls.assert_model_materials(m)
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
    def read_object(cls, o):
        if o.type == 'MESH':
            return cls.read_model(o)
        if o.type == 'CAMERA':
            return cls.read_camera(o)
        if o.type == 'LAMP':
            return cls.read_light(o)
        if o.type == 'SPEAKER':
            return cls.read_speaker(o)

    @classmethod
    def read_scenes(cls):
        for s in bpy.data.scenes:
            if s.name in cls.scenes:
                continue
            for o in s.objects:
                cls.read_object(o)
            cls.scenes[s.name] = [0, cls.last_scene_id]
            cls.last_scene_id += 1

    @classmethod
    def write_tables(cls):
        cls.write_shaders_table()
        cls.gather_cameras_offsets()
        cls.gather_speakers_offsets()
        cls.gather_lights_offsets()
        cls.gather_textures_offsets()
        cls.gather_models_offsets()
        cls.gather_scenes_offsets()
        cls.write_offset_array(cls.cameras_offsets)
        cls.write_offset_array(cls.speakers_offsets)
        cls.write_offset_array(cls.lights_offsets)
        cls.write_offset_array(cls.textures_offsets)
        cls.write_offset_array(cls.models_offsets)
        cls.write_offset_array(cls.scenes_offsets)

    @classmethod
    def write_file(cls):
        cls.shaders = {  # id: offset
            # special shaders will be added manually in here
            (0, 0, 0, 0, 0, 0): 0,  # white shader for occlussion culling
        }
        cls.textures = dict()  # filepath: [offest, id<con>, type]
        cls.last_texture_id = 0
        cls.scenes = dict()  # name: [offset, id<con>]
        cls.last_scene_id = 0
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
        cls.write_models()
        cls.write_scenes()
        cls.out.flush()
        cls.out.seek(tables_offset)
        cls.write_tables()
        cls.out.flush()
        cls.out.close()
        cls.rust_code.flush()
        cls.rust_code.close()

    class Exporter(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
        """This is a plug in for Gearoenix 3D file format"""
        bl_idname = "gearoenix_exporter.data_structure"
        bl_label = "Export Gearoenix 3D"
        filename_ext = ".gx3d"
        filter_glob = bpy.props.StringProperty(
            default="*.gx3d",
            options={'HIDDEN'}, )

        def execute(self, context):
            if not (Gearoenix.check_env()):
                return {'CANCELLED'}
            try:
                Gearoenix.out = open(self.filepath, mode='wb')
                Gearoenix.rust_code = open(self.filepath + ".rs", mode='w')
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
