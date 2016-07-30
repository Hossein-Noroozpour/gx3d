bl_info = {
    "name": "Gearoenix Blender",
    "author": "Hossein Noroozpour",
    "version": (1, 0),
    "blender": (2, 7, 5),
    "api": 1,
    "location": "File > Export",
    "description": "Export several scene into a Gearoenix 3D file format.",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export",
}

import bpy
import sys
import ctypes
import io
import mathutils
import math
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator


class Gearoenix:
    class OkOperator(bpy.types.Operator):
        bl_idname = "error.ok"
        bl_label = "OK"

        def execute(self, context):
            return {'FINISHED'}

    class MessageOperator(Operator):
        bl_idname = "error.message"
        bl_label = "Message"
        type = StringProperty()
        message = StringProperty()

        def execute(self, context):
            self.report({'INFO'}, self.message)
            print(self.message)
            return {'FINISHED'}

        def invoke(self, context, event):
            wm = context.window_manager
            return wm.invoke_popup(self, width=400, height=200)

        def draw(self, context):
            self.layout.label("A message has arrived")
            row = self.layout.split(0.25)
            row.prop(self, "type")
            row.prop(self, "message")
            row = self.layout.split(0.80)
            row.label("")
            row.operator("error.ok")

    def show_error(s: str):
        print(s)
        bpy.ops.error.message('INVOKE_DEFAULT', type="Error", message=s)
        raise Exception(s)


# TODO: Encoding in string
# TODO: New Terrain Importing
# TODO: Geometry copy
# Types
Gearoenix.TYPE_BOOLEAN = ctypes.c_uint8
Gearoenix.TYPE_OBJECT_TYPE_ID = ctypes.c_uint8
Gearoenix.TYPE_INSTRUCTION = ctypes.c_uint16
Gearoenix.TYPE_VERTEX_ELEMENT = ctypes.c_float
Gearoenix.TYPE_INDEX_ELEMENT = ctypes.c_uint32
Gearoenix.TYPE_VERTEX_ELEMENT_COUNT = ctypes.c_uint32
Gearoenix.TYPE_INDICES_COUNT = ctypes.c_uint32
Gearoenix.TYPE_STRING_LENGTH = ctypes.c_uint16
Gearoenix.TYPE_CHARACTER = ctypes.c_char
Gearoenix.TYPE_MATRIX_ELEMENTS = ctypes.c_float
Gearoenix.MATRIX_SIZE = ctypes.sizeof(Gearoenix.TYPE_MATRIX_ELEMENTS) * 16
# Constants
Gearoenix.BOOLEAN_TRUE = Gearoenix.TYPE_BOOLEAN(1)
Gearoenix.BOOLEAN_FALSE = Gearoenix.TYPE_BOOLEAN(0)
# Debuging symboles
Gearoenix.terrain_debug = True

Gearoenix.render_mode = 'path tracing'

Gearoenix.imported_objects = set()


def assigner():
    def save_string(save_file, string):
        save_file.write(Gearoenix.TYPE_STRING_LENGTH(len(string)))
        for c in string:
            save_file.write(Gearoenix.TYPE_CHARACTER(ord(c)))

    return save_string


Gearoenix.save_string = assigner()


def assigner():
    def get_string_size(s: str):
        return ctypes.sizeof(Gearoenix.TYPE_STRING_LENGTH) + ctypes.sizeof(Gearoenix.TYPE_CHARACTER) * len(s)

    return get_string_size


Gearoenix.get_string_size = assigner()


def assigner():
    def save_matrix(save_file, matrix):
        for i in range(0, 4):
            for j in range(0, 4):
                save_file.write(Gearoenix.TYPE_MATRIX_ELEMENTS(matrix[j][i]))

    return save_matrix


Gearoenix.save_matrix = assigner()


def assigner():
    def save_vector(save_file, vector):
        for i in range(3):
            save_file.write(ctypes.c_float(vector[i]))

    return save_vector


Gearoenix.save_vector = assigner()


def assigner():
    def prefix_check(name, prefix):
        return name[0:len(prefix)] == prefix

    return prefix_check


Gearoenix.prefix_check = assigner()


def assigner():
    def postfix_check(name, postfix):
        return name[len(name) - len(postfix):] == postfix

    return postfix_check


Gearoenix.postfix_check = assigner()


def assigner():
    class Vertex:

        class UnKnownVertexTypeError(Exception):
            def __init__(self, value):
                self.value = value

            def __str__(self):
                return repr(self.value)

        class WrappedVertexTypeError(Exception):
            def __init__(self, value):
                self.value = value

            def __str__(self):
                return repr(self.value)

        class VertexGroupOutOfRangeTypeError(Exception):
            def __init__(self, value):
                self.value = value

            def __str__(self):
                return repr(self.value)

        def __init__(self, vertex_index, loop_index, vertex_obj, world_matrix, mesh_type, mesh):
            self.mesh = mesh
            if Gearoenix.Mesh.MESH_TYPE_OCCLUSION == mesh_type:
                self.position = world_matrix * vertex_obj.data.vertices[vertex_index].co
                self.data = (self.position[0], self.position[1], self.position[2])
            elif Gearoenix.Mesh.MESH_TYPE_SKIN == mesh_type:
                self.position = vertex_obj.data.vertices[vertex_index].co
                self.normal = vertex_obj.data.vertices[vertex_index].normal
                if vertex_obj.data.uv_layers.active is not None:
                    self.uv = vertex_obj.data.uv_layers.active.data[loop_index].uv
                else:
                    raise self.WrappedVertexTypeError("Your mesh does not unwrapped yet.")
                self.weight = [0.0] * len(vertex_obj.vertex_groups)
                number_of_affect_bones = 0
                for g in vertex_obj.data.vertices[vertex_index].groups:
                    index = g.group
                    if index < len(vertex_obj.vertex_groups):
                        if g.weight > 0.0:
                            self.weight[index] = g.weight
                            number_of_affect_bones += 1
                    else:
                        raise self.VertexGroupOutOfRangeTypeError("Out of range vertex group index.")
                if number_of_affect_bones > mesh.max_number_of_affecting_bone_on_a_vertex:
                    mesh.max_number_of_affecting_bone_on_a_vertex = number_of_affect_bones
                self.data = [self.position[0], self.position[1], self.position[2],
                             self.normal[0], self.normal[1], self.normal[2],
                             self.uv[0], self.uv[1]]
            elif mesh_type.startswith("static"):
                data_list = []
                if "position" in mesh_type:
                    position = world_matrix * vertex_obj.data.vertices[vertex_index].co
                    data_list.append(position[0])
                    data_list.append(position[1])
                    data_list.append(position[2])
                if "normal" in mesh_type:
                    normal = vertex_obj.data.vertices[vertex_index].normal.xyzz
                    normal[3] = 0.0
                    normal = world_matrix * normal
                    normal = normal.xyz.normalized()
                    data_list.append(normal[0])
                    data_list.append(normal[1])
                    data_list.append(normal[2])
                if "uv" in mesh_type:
                    if vertex_obj.data.uv_layers.active is not None:
                        uv = vertex_obj.data.uv_layers.active.data[loop_index].uv
                        data_list.append(uv[0])
                        data_list.append(uv[1])
                    else:
                        Gearoenix.show_error("Your mesh does not unwrapped yet.")
                self.data = tuple(data_list)
            else:
                raise self.UnKnownVertexTypeError("Unknown vertex type")

        def create_data(self):
            bone_index_index = len(self.data)
            self.data += [0.0] * 2 * self.mesh.max_number_of_affecting_bone_on_a_vertex
            bone_weight_index = bone_index_index + self.mesh.max_number_of_affecting_bone_on_a_vertex
            for i, w in enumerate(self.weight):
                if w > 0.0:
                    self.data[bone_index_index] = float(i)
                    self.data[bone_weight_index] = w
            self.data = tuple(self.data)

        def __str__(self):
            return str(self.data)

    return Vertex


Gearoenix.Vertex = assigner()


def assigner():
    class Triangle:

        class UntriangulatedMeshError(Exception):
            def __init__(self, value):
                self.value = value

            def __str__(self):
                return repr(self.value)

        def __init__(self, polygon, world_matrix, triangle_obj, mesh_type, mesh):
            super(Gearoenix.Triangle, self).__init__()
            self.vertices = []
            if len(polygon.vertices) > 3:
                Gearoenix.show_error("Your mesh(" + str(triangle_obj.name) + ") must be triangulated before exporting.")
            for vertex_index, loop_index in zip(polygon.vertices, polygon.loop_indices):
                vertex = Gearoenix.Vertex(vertex_index, loop_index, triangle_obj, world_matrix, mesh_type, mesh)
                self.vertices.append(vertex)
                # mid_normal = self.vertices[0].normal + self.vertices[1].normal + self.vertices[2].normal
                # v1 = self.vertices[1].position - self.vertices[0].position
                # v2 = self.vertices[2].position - self.vertices[0].position
                # cross_v1_v2 = v1.cross(v2)
                # cull = cross_v1_v2.dot(mid_normal)
                # if cull > 0:
                # v = self.vertices[2]
                # self.vertices[2] = self.vertices[1]
                # self.vertices[1] = v

        def __str__(self):
            s = ''
            for v in self.vertices:
                s += str(v)
                s += '\n'
            return s

    return Triangle


Gearoenix.Triangle = assigner()


def assigner():
    class Mesh:
        MESH_TYPE_OCCLUSION = 'occlusion'
        MESH_TYPE_SKIN = 'skin'

        def __init__(self, mesh_obj, mesh_type, inverse_matrix):
            self.max_number_of_affecting_bone_on_a_vertex = 0
            # print("Mesh ", mesh_obj.name, " is initializing")
            triangles = []
            if mesh_type == Gearoenix.Mesh.MESH_TYPE_OCCLUSION:
                world_matrix = mathutils.Matrix()
            else:
                world_matrix = inverse_matrix * mesh_obj.matrix_world
            for polygon in mesh_obj.data.polygons:
                triangle = Gearoenix.Triangle(polygon, world_matrix, mesh_obj, mesh_type, self)
                triangles.append(triangle)
            vert_ind = dict()
            vertices_count = 0
            for triangle in triangles:
                for vertex in triangle.vertices:
                    if mesh_type == self.MESH_TYPE_SKIN:
                        vertex.create_data()
                    key = vertex.data
                    if key in vert_ind:
                        vert_ind[key].append(vertices_count)
                    else:
                        vert_ind[key] = [vertices_count]
                    vertices_count += 1
            self.ibo = vertices_count * [0]
            self.vbo = []
            vertices_count = 0
            for vertex, indices in vert_ind.items():
                for v in vertex:
                    self.vbo.append(v)
                for i in indices:
                    self.ibo[i] = vertices_count
                vertices_count += 1
            if mesh_type == self.MESH_TYPE_SKIN:
                print("Maximum number of affecting bone on a vertex is: ",
                      self.max_number_of_affecting_bone_on_a_vertex)

        def save(self, save_file):
            save_file.write(Gearoenix.TYPE_VERTEX_ELEMENT_COUNT(len(self.vbo)))
            for f in self.vbo:
                save_file.write(Gearoenix.TYPE_VERTEX_ELEMENT(f))
            save_file.write(Gearoenix.TYPE_INDICES_COUNT(len(self.ibo)))
            for i in self.ibo:
                save_file.write(Gearoenix.TYPE_INDEX_ELEMENT(i))

    return Mesh


Gearoenix.Mesh = assigner()


def assigner():
    class Bone:
        BONE_TYPE_FLOAT = ctypes.c_float
        BONE_TYPE_BONE_INDEX = ctypes.c_uint16
        BONE_TYPE_CHILDREN_COUNT = ctypes.c_uint8

        class OutOfRangeChildrenNumberError(Exception):
            def __init__(self, value):
                self.value = value

            def __str__(self):
                return repr(self.value)

        def __init__(self, bone):
            self.name = bone.name
            if len(bone.children) > 255:
                raise self.OutOfRangeChildrenNumberError(
                    "Your bone structure has out of range children at bone[" + self.name + "]")
            self.children = [Gearoenix.Bone(child) for child in bone.children]
            self.head = bone.head
            self.tail = bone.tail
            self.index = None

        def indexify(self, vertex_groups):
            self.index = vertex_groups[self.name]
            for c in self.children:
                c.indexify(vertex_groups)

        def save(self, save_file):
            Gearoenix.save_string(save_file, self.name)
            for i in range(3):
                save_file.write(self.BONE_TYPE_FLOAT(self.head[i]))
            for i in range(3):
                save_file.write(self.BONE_TYPE_FLOAT(self.tail[i]))
            save_file.write(self.BONE_TYPE_BONE_INDEX(self.index))
            print(len(self.children))
            save_file.write(self.BONE_TYPE_CHILDREN_COUNT(len(self.children)))
            for c in self.children:
                c.save(save_file)

        def get_size(self):
            children_size = 0
            for c in self.children:
                children_size += c.get_size()
            return Gearoenix.get_string_size(self.name) + ctypes.sizeof(self.BONE_TYPE_FLOAT) * 6 + ctypes.sizeof(
                self.BONE_TYPE_BONE_INDEX) + ctypes.sizeof(self.BONE_TYPE_CHILDREN_COUNT) + children_size


def assigner():
    class ChannelKeyFrame:
        CHANNEL_KEYFRAME_TYPE_ELEMENT = ctypes.c_float

        def __init__(self, keyframe):
            if keyframe.interpolation != 'BEZIER':
                print("Error: Only bezier interpolation is supported.")
                exit(1)
            self.position_t = keyframe.co[0]
            self.position_v = keyframe.co[1]
            self.left_handle_t = keyframe.handle_left[0]
            self.left_handle_v = keyframe.handle_left[1]
            self.right_handle_t = keyframe.handle_right[0]
            self.right_handle_v = keyframe.handle_right[1]

        def save(self, save_file):
            save_file.write(self.CHANNEL_KEYFRAME_TYPE_ELEMENT(self.position_t))
            save_file.write(self.CHANNEL_KEYFRAME_TYPE_ELEMENT(self.position_v))
            save_file.write(self.CHANNEL_KEYFRAME_TYPE_ELEMENT(self.left_handle_t))
            save_file.write(self.CHANNEL_KEYFRAME_TYPE_ELEMENT(self.left_handle_v))
            save_file.write(self.CHANNEL_KEYFRAME_TYPE_ELEMENT(self.right_handle_t))
            save_file.write(self.CHANNEL_KEYFRAME_TYPE_ELEMENT(self.right_handle_v))

        def get_size(self):
            return 6 * ctypes.sizeof(self.CHANNEL_KEYFRAME_TYPE_ELEMENT)
    return ChannelKeyFrame

Gearoenix.ChannelKeyFrame = assigner()


def assigner():
    class AnimationChannel:
        X_LOCATION = ctypes.c_uint8(1)
        Y_LOCATION = ctypes.c_uint8(2)
        Z_LOCATION = ctypes.c_uint8(3)
        W_QUATERNION_ROTATION = ctypes.c_uint8(4)
        X_QUATERNION_ROTATION = ctypes.c_uint8(5)
        Y_QUATERNION_ROTATION = ctypes.c_uint8(6)
        Z_QUATERNION_ROTATION = ctypes.c_uint8(7)
        X_SCALE = ctypes.c_uint8(8)
        Y_SCALE = ctypes.c_uint8(9)
        Z_SCALE = ctypes.c_uint8(10)

        CHANNEL_TYPE_KEYFRAME_COUNT = ctypes.c_uint16

        def __init__(self, channel):
            self.bone_index = None
            self.keyframes = []
            data_path = channel.data_path
            array_index = channel.array_index
            if Gearoenix.postfix_check(data_path, 'location'):
                self.bone = data_path[len('pose.bones[\"'):len(data_path) - len('\"].location')]
                if array_index == 0:
                    self.channel_type = self.X_LOCATION
                elif array_index == 1:
                    self.channel_type = self.Y_LOCATION
                elif array_index == 2:
                    self.channel_type = self.Z_LOCATION
                else:
                    print("Error: Unknown location channel.")
                    exit(1)
            elif Gearoenix.postfix_check(data_path, 'rotation_quaternion'):
                self.bone = data_path[len('pose.bones[\"'):len(data_path) - len('\"].rotation_quaternion')]
                if array_index == 0:
                    self.channel_type = self.W_QUATERNION_ROTATION
                elif array_index == 1:
                    self.channel_type = self.X_QUATERNION_ROTATION
                elif array_index == 2:
                    self.channel_type = self.Y_QUATERNION_ROTATION
                elif array_index == 3:
                    self.channel_type = self.Z_QUATERNION_ROTATION
                else:
                    print("Error: Unknown rotation quaternion channel.")
                    exit(1)
            elif Gearoenix.postfix_check(data_path, 'scale'):
                self.bone = data_path[len('pose.bones[\"'):len(data_path) - len('\"].scale')]
                if array_index == 0:
                    self.channel_type = self.X_SCALE
                elif array_index == 1:
                    self.channel_type = self.Y_SCALE
                elif array_index == 2:
                    self.channel_type = self.Z_SCALE
                else:
                    print("Error: Unknown scale channel.")
                    exit(1)
            else:
                print("Error: Unknown channel.")
                exit(1)
            for keyframe in channel.keyframe_points:
                self.keyframes.append(Gearoenix.ChannelKeyFrame(keyframe))

        def indexify(self, vertex_groups):
            self.bone_index = vertex_groups[self.bone]

        def save(self, save_file):
            save_file.write(self.channel_type)
            save_file.write(Gearoenix.Bone.BONE_TYPE_BONE_INDEX(self.bone_index))
            Gearoenix.save_string(save_file, self.bone)
            save_file.write(self.CHANNEL_TYPE_KEYFRAME_COUNT(len(self.keyframes)))
            for k in self.keyframes:
                k.save(save_file)

        def get_size(self):
            keyframes_size = 0
            for k in self.keyframes:
                keyframes_size += k.get_size()
            return ctypes.sizeof(self.channel_type) + ctypes.sizeof(
                Gearoenix.Bone.BONE_TYPE_BONE_INDEX) + Gearoenix.get_string_size(self.bone) + ctypes.sizeof(
                self.CHANNEL_TYPE_KEYFRAME_COUNT) + keyframes_size
    return AnimationChannel

Gearoenix.AnimationChannel = assigner()


def assigner():
    class Action:
        ACTION_TYPE_FRAME_RANGE = ctypes.c_float
        ACTION_TYPE_CHANNEL_COUNT = ctypes.c_int16

        def __init__(self, arm_obj):
            action = arm_obj.animation_data.action
            self.key_frames_range = action.frame_range
            self.channels = []
            for fcurve in action.fcurves:
                self.channels.append(Gearoenix.AnimationChannel(fcurve))

        def indexify_channels_bones(self, vertex_groups):
            for c in self.channels:
                c.indexify(vertex_groups)

        def save(self, save_file):
            save_file.write(self.ACTION_TYPE_FRAME_RANGE(self.key_frames_range[0]))
            save_file.write(self.ACTION_TYPE_FRAME_RANGE(self.key_frames_range[1]))
            save_file.write(self.ACTION_TYPE_CHANNEL_COUNT(len(self.channels)))
            for c in self.channels:
                c.save(save_file)

        def get_size(self):
            channels_size = 0
            for c in self.channels:
                channels_size += c.get_size()
            return (ctypes.sizeof(self.ACTION_TYPE_FRAME_RANGE) * 2) + ctypes.sizeof(
                self.ACTION_TYPE_CHANNEL_COUNT) + channels_size
    return Action

Gearoenix.Action = assigner()


def assigner():
    class Animation:
        def __init__(self, arm_obj):
            self.action = Gearoenix.Action(arm_obj)

        def save(self, save_file):
            self.action.save(save_file)

        def indexify_channels_bones(self, vertex_groups):
            self.action.indexify_channels_bones(vertex_groups)

        def get_size(self):
            return self.action.get_size()
    return Animation

Gearoenix.Animation = assigner()


def assigner():
    class Armature:
        ARMATURE_TYPE_BONE_COUNT = ctypes.c_uint16
        ARMATURE_TYPE_MAX_NUMBER_OF_AFFECTING_BONE_ON_A_VERTEX_TYPE = ctypes.c_int8

        def __init__(self, arm_obj):
            self.type = Gearoenix.Scene.OBJECT_TYPE_ID_ARMATURE
            self.name = arm_obj.name
            self.bones = []
            for bone in arm_obj.pose.bones:
                if bone.parent is None:
                    self.bones.append(Gearoenix.Bone(bone))
            if len(self.bones) > 1:
                print("Warning: Number of root bone in ", self.name, " is ", len(self.bones))
            self.animation_data = Gearoenix.Animation(arm_obj)
            self.skin = Gearoenix.Mesh(arm_obj.children[0], Gearoenix.Mesh.MESH_TYPE_SKIN, None)
            vertex_groups = arm_obj.children[0].vertex_groups
            vertex_groups = {g.name: i for i, g in enumerate(vertex_groups)}
            self.animation_data.indexify_channels_bones(vertex_groups)
            for b in self.bones:
                b.indexify(vertex_groups)

        def save(self, save_file):
            save_file.write(self.ARMATURE_TYPE_BONE_COUNT(len(self.bones)))
            for b in self.bones:
                b.save(save_file)
            self.animation_data.save(save_file)
            save_file.write(self.ARMATURE_TYPE_MAX_NUMBER_OF_AFFECTING_BONE_ON_A_VERTEX_TYPE(
                self.skin.max_number_of_affecting_bone_on_a_vertex))
            self.skin.save(save_file)
    return Armature

Gearoenix.Armature = assigner()


def assigner():
    class Geometry:
        TYPE_MESH_COUNT = ctypes.c_uint8

        def __init__(self, geo_obj):
            print("Geometry: ", geo_obj.name)
            self.type = Gearoenix.Scene.OBJECT_TYPE_ID_GEOMETRY
            self.name = geo_obj.name
            self.meshes = []
            self.matrix = geo_obj.matrix_world
            self.location = geo_obj.location
            inverse_matrix = geo_obj.matrix_world.copy()
            inverse_matrix.invert()
            for c in geo_obj.children:
                if c.type == 'MESH':
                    mesh_type = "static"
                    name_commands = c.name.split(":")
                    mesh_name = name_commands[0]
                    if len(name_commands) < 2:
                        Gearoenix.show_error(
                            "Mesh (" + mesh_name + ") child of (" + self.name + ") does not contain commands list.")
                    commands = name_commands[1]
                    mesh_attributes = commands
                    for attribute in mesh_attributes.split("-"):
                        if attribute == "normal":
                            mesh_type += "-normal"
                        elif attribute == "uv":
                            mesh_type += "-uv"
                        elif attribute == "position":
                            mesh_type += "-position"
                        else:
                            raise Exception(
                                "Unknown attribute in mesh (" + mesh_name + ") child of (" + self.name + ")")
                    mesh = Gearoenix.Mesh(c, mesh_type, inverse_matrix)
                    mesh.name = mesh_name
                    # TODO: In future this condition must be in the command list, not having UV!
                    if "uv" in mesh_type:
                        mesh.has_texture = True
                        # TODO: I only support one material and one texture for a object right now.
                        texture_name = c.data.materials[0].texture_slots[0].name
                        mesh.texture_index = Gearoenix.TextureManager.get_index(texture_name)
                    else:
                        mesh.has_texture = False
                    self.meshes.append(mesh)
            self.occ_mesh = Gearoenix.Mesh(geo_obj, Gearoenix.Mesh.MESH_TYPE_OCCLUSION, None)
            self.radius = 0.0
            for i in range(int(len(self.occ_mesh.vbo) / 3)):
                vl = self.matrix * mathutils.Vector((
                    self.occ_mesh.vbo[i * 3],
                    self.occ_mesh.vbo[i * 3 + 1],
                    self.occ_mesh.vbo[i * 3 + 2]))
                vd = mathutils.Vector((
                    self.location[0],
                    self.location[1],
                    self.location[2]
                )) - vl
                d = vd.length
                if d > self.radius:
                    self.radius = d
            print(self.radius)

        def save(self, save_file: io.BufferedWriter):
            save_file.write(Gearoenix.Geometry.TYPE_MESH_COUNT(len(self.meshes)))
            for mesh in self.meshes:
                Gearoenix.save_string(save_file, mesh.name)
                if mesh.has_texture:
                    save_file.write(Gearoenix.BOOLEAN_TRUE)
                    save_file.write(Gearoenix.TextureManager.TYPE_TEXTURE_INDEX(mesh.texture_index))
                else:
                    save_file.write(Gearoenix.BOOLEAN_FALSE)
                mesh.save(save_file)
            Gearoenix.save_matrix(save_file, self.matrix)
            Gearoenix.save_vector(save_file, self.location)
            save_file.write(ctypes.c_float(self.radius))
            self.occ_mesh.save(save_file)

    return Geometry


Gearoenix.Geometry = assigner()


def assigner():
    class CopyGeometry:

        def __init__(self, geo):
            super(Gearoenix.CopyGeometry, self).__init__()
            self.matrix = geo.matrix_world
            self.location = geo.location

        def save(self, save_file: io.BufferedWriter):
            Gearoenix.save_matrix(save_file, self.matrix)
            Gearoenix.save_vector(save_file, self.location)

        def __hash__(self):
            l = []
            for v in self.matrix:
                for e in v:
                    l.append(e)
            for e in self.location:
                l.append(e)
            return hash(tuple(l))

    return CopyGeometry


Gearoenix.CopyGeometry = assigner()


def assigner():
    class Camera:
        TYPE_CAMERA_ELEMENTS = ctypes.c_float
        TYPE_CAMERA_TYPE = ctypes.c_uint8
        ORTHO_CAMERA = TYPE_CAMERA_TYPE(1)
        PERSPECTIVE_CAMERA = TYPE_CAMERA_TYPE(2)

        def __init__(self, camera_obj):
            self.name = camera_obj.name
            self.type = Gearoenix.Scene.OBJECT_TYPE_ID_CAMERA
            if camera_obj.data.type == 'PERSP':
                self.camera_type = Gearoenix.Camera.PERSPECTIVE_CAMERA
                self.field_of_view = Gearoenix.Camera.TYPE_CAMERA_ELEMENTS(camera_obj.data.angle / 2.0)
            elif camera_obj.data.type == 'ORTHO':
                self.camera_type = Gearoenix.Camera.ORTHO_CAMERA
            self.near = Gearoenix.Camera.TYPE_CAMERA_ELEMENTS(camera_obj.data.clip_start)
            self.far = Gearoenix.Camera.TYPE_CAMERA_ELEMENTS(camera_obj.data.clip_end)
            self.location = camera_obj.location
            self.rotation = camera_obj.rotation_euler

        def save(self, save_file):
            save_file.write(self.camera_type)
            save_file.write(self.TYPE_CAMERA_ELEMENTS(self.location[0]))
            save_file.write(self.TYPE_CAMERA_ELEMENTS(self.location[1]))
            save_file.write(self.TYPE_CAMERA_ELEMENTS(self.location[2]))
            save_file.write(self.TYPE_CAMERA_ELEMENTS(self.rotation[0]))
            save_file.write(self.TYPE_CAMERA_ELEMENTS(self.rotation[1]))
            save_file.write(self.TYPE_CAMERA_ELEMENTS(self.rotation[2]))
            save_file.write(self.near)
            save_file.write(self.far)
            if self.camera_type == Gearoenix.Camera.PERSPECTIVE_CAMERA:
                save_file.write(self.field_of_view)

    return Camera


Gearoenix.Camera = assigner()


def assigner():
    class Sun:
        def __init__(self, sun_obj):
            self.location = sun_obj.location
            self.rotation = sun_obj.rotation_euler

        def save(self, save_file):
            save_file.write(ctypes.c_float(self.location[0]))
            save_file.write(ctypes.c_float(self.location[1]))
            save_file.write(ctypes.c_float(self.location[2]))
            save_file.write(ctypes.c_float(self.rotation[0]))
            save_file.write(ctypes.c_float(self.rotation[1]))
            save_file.write(ctypes.c_float(self.rotation[2]))

    return Sun


Gearoenix.Sun = assigner()


def assigner():
    class Sky:
        SKY_PREFIX = 'sky-'

        def __init__(self, geo_obj):
            self.type = Gearoenix.Scene.OBJECT_TYPE_ID_SKY_BOX
            self.name = geo_obj.name
            matrix = geo_obj.matrix_world
            self.mesh = Gearoenix.Mesh(geo_obj, 'static-position', matrix)
            texture_name = geo_obj.data.materials[0].texture_slots[0].name
            texture_name = Gearoenix.CubeTexture.prepare_name(texture_name)
            self.texture_index = Gearoenix.TextureManager.get_index(texture_name)

        def save(self, save_file: io.BufferedWriter):
            save_file.write(Gearoenix.TextureManager.TYPE_TEXTURE_INDEX(self.texture_index))
            self.mesh.save(save_file)

    return Sky


Gearoenix.Sky = assigner()


def assigner():
    class Terrain:
        TERRAIN_PREFIX = 'terrain-'
        TYPE_AREA_COUNT = ctypes.c_uint8
        TYPE_TEXTURE_COUNT = ctypes.c_uint8
        TYPE_TRIANGLE_COUNT = ctypes.c_uint16

        def __init__(self, obj):
            super(Gearoenix.Terrain, self).__init__()
            self.areas = dict()
            for c in obj.children:
                if c.type != 'EMPTY':
                    continue
                if not c.name.startswith('area'):
                    continue
                x = c.location.x
                y = c.location.y
                self.areas[(x, y)] = {'triangles': [], 'radius': 0.0}
            for polygon in obj.data.polygons:
                if len(polygon.vertices) > 3:
                    raise Exception('Untriangulated polygon in ' + obj.name)
                vertices = []
                for vertex_index, loop_index in zip(polygon.vertices, polygon.loop_indices):
                    position = obj.matrix_world * obj.data.vertices[vertex_index].co
                    normal = obj.data.vertices[vertex_index].normal.xyzz
                    normal[3] = 0.0
                    normal = obj.matrix_world * normal
                    normal = normal.xyz.normalized()
                    uv = obj.data.uv_layers.active.data[loop_index].uv
                    vertices.append({'position': position, 'normal': normal, 'uv': uv})
                mind = 10.0 ** 100
                area = None
                for a in self.areas.keys():
                    x = a[0] - vertices[0]['position'][0]
                    x *= x
                    y = a[1] - vertices[0]['position'][1]
                    y *= y
                    d = math.sqrt(x + y)
                    if d < mind:
                        area = a
                        mind = d
                max_d = -1
                for v in vertices:
                    x = area[0] - v['position'][0]
                    y = area[1] - v['position'][1]
                    d = math.sqrt((x * x) + (y * y))
                    if max_d < d:
                        max_d = d
                self.areas[area]['triangles'].append(vertices)
                if self.areas[area]['radius'] < max_d:
                    self.areas[area]['radius'] = max_d
            self.textures = []
            for t in obj.data.materials[0].texture_slots:
                if t is not None:
                    self.textures.append(Gearoenix.TextureManager.get_index(t.name))
            if Gearoenix.terrain_debug:
                print('Terrain debugging')
                for center, area in self.areas.items():
                    print('Center x: ', center[0], '  y: ', center[1], '   Radius: ', area['radius'],
                          '  Triangles count: ', len(area['triangles']))

        def save(self, save_file: io.BufferedWriter):
            save_file.write(Gearoenix.Terrain.TYPE_AREA_COUNT(len(self.areas)))
            for center, area in self.areas.items():
                save_file.write(ctypes.c_float(center[0]))
                save_file.write(ctypes.c_float(center[1]))
                save_file.write(ctypes.c_float(area['radius']))
                vert_ind = dict()
                vertices_count = 0
                for triangle in area['triangles']:
                    for vertex in triangle:
                        key = (vertex['position'][0], vertex['position'][1], vertex['position'][2], vertex['normal'][0],
                               vertex['normal'][1], vertex['normal'][2], vertex['uv'][0], vertex['uv'][1])
                        if key in vert_ind:
                            vert_ind[key].append(vertices_count)
                        else:
                            vert_ind[key] = [vertices_count]
                        vertices_count += 1
                ibo = vertices_count * [0]
                vbo = []
                vertices_count = 0
                for vertex, indices in vert_ind.items():
                    for v in vertex:
                        vbo.append(v)
                    for i in indices:
                        ibo[i] = vertices_count
                    vertices_count += 1
                save_file.write(Gearoenix.TYPE_VERTEX_ELEMENT_COUNT(len(vbo)))
                for f in vbo:
                    save_file.write(Gearoenix.TYPE_VERTEX_ELEMENT(f))
                save_file.write(Gearoenix.TYPE_INDICES_COUNT(len(ibo)))
                for i in ibo:
                    save_file.write(Gearoenix.TYPE_INDEX_ELEMENT(i))
            save_file.write(Gearoenix.Terrain.TYPE_TEXTURE_COUNT(len(self.textures)))
            for t in self.textures:
                save_file.write(Gearoenix.TextureManager.TYPE_TEXTURE_INDEX(t))

    return Terrain


Gearoenix.Terrain = assigner()


def assigner():
    class Scene:
        TYPE_OBJECT_COUNT = ctypes.c_uint16
        OBJECT_TYPE_ID_GEOMETRY = Gearoenix.TYPE_OBJECT_TYPE_ID(1)
        OBJECT_TYPE_ID_SKY_BOX = Gearoenix.TYPE_OBJECT_TYPE_ID(2)
        OBJECT_TYPE_ID_ARMATURE = Gearoenix.TYPE_OBJECT_TYPE_ID(3)
        OBJECT_TYPE_ID_CAMERA = Gearoenix.TYPE_OBJECT_TYPE_ID(4)
        OBJECT_TYPE_ID_SUN = Gearoenix.TYPE_OBJECT_TYPE_ID(5)
        OBJECT_TYPE_ID_TERRAIN = Gearoenix.TYPE_OBJECT_TYPE_ID(6)
        OBJECT_TYPE_STRING_ARMATURE = 'ARMATURE'
        OBJECT_TYPE_STRING_MESH = 'MESH'
        OBJECT_TYPE_STRING_CAMERA = 'CAMERA'
        OBJECT_TYPE_STRING_LAMP = 'LAMP'
        OBJECT_TYPE_STRING_SUN = 'SUN'
        COPY_GEOMETRY_PREFIX = 'copy-geo-'
        TYPE_OFFSET = ctypes.c_uint32

        def __init__(self, scn):
            super(Gearoenix.Scene, self).__init__()
            self.objects = []
            self.name = scn.name
            self.geo_copies = dict()
            for obj in bpy.data.scenes[self.name].objects:
                if obj.type == Gearoenix.Scene.OBJECT_TYPE_STRING_MESH:
                    if obj.parent is not None:
                        continue
                    if obj.name.startswith(Gearoenix.Scene.COPY_GEOMETRY_PREFIX):
                        continue
                    if obj.name.startswith(Gearoenix.Sky.SKY_PREFIX):
                        self.add_object(Gearoenix.Sky(obj))
                    elif obj.name.startswith(Gearoenix.Terrain.TERRAIN_PREFIX):
                        terrain = Gearoenix.Terrain(obj)
                        terrain.name = obj.name[len(Gearoenix.Terrain.TERRAIN_PREFIX):]
                        terrain.type = Gearoenix.Scene.OBJECT_TYPE_ID_TERRAIN
                        self.add_object(terrain)
                    else:
                        geo = Gearoenix.Geometry(obj)
                        self.add_object(geo)
                elif obj.type == Gearoenix.Scene.OBJECT_TYPE_STRING_ARMATURE:
                    self.add_object(Gearoenix.Armature(obj))
                elif obj.type == Gearoenix.Scene.OBJECT_TYPE_STRING_CAMERA:
                    self.add_object(Gearoenix.Camera(obj))
                elif obj.type == Gearoenix.Scene.OBJECT_TYPE_STRING_LAMP:
                    if obj.data.type != Gearoenix.Scene.OBJECT_TYPE_STRING_SUN:
                        Gearoenix.show_error("Only SUN is supported right now.")
                    sun = Gearoenix.Sun(obj)
                    sun.type = Gearoenix.Scene.OBJECT_TYPE_ID_SUN
                    sun.name = obj.name
                    self.add_object(sun)
            for obj in bpy.data.scenes[self.name].objects:
                if obj.type == Gearoenix.Scene.OBJECT_TYPE_STRING_MESH:
                    if obj.parent is not None:
                        continue
                    if obj.name.startswith(Gearoenix.Scene.COPY_GEOMETRY_PREFIX):
                        geo_name = obj.name[len(Gearoenix.Scene.COPY_GEOMETRY_PREFIX): len(obj.name) - 4]
                        geo_copy = Gearoenix.CopyGeometry(obj)
                        geo_copy.copy_number = int(obj.name[len(obj.name) - 3:])
                        if geo_name in self.geo_copies:
                            self.geo_copies[geo_name].add(geo_copy)
                        else:
                            self.geo_copies[geo_name] = {geo_copy}

        def add_object(self, o):
            self.objects.append(o)

        def save(self, save_file: io.BufferedReader):
            save_file.write(self.TYPE_OBJECT_COUNT(len(self.objects)))
            table_offset = save_file.tell()
            offsets = []
            for i in range(len(self.objects)):
                save_file.write(self.objects[i].type)
                Gearoenix.save_string(save_file, self.objects[i].name)
                save_file.write(Gearoenix.Scene.TYPE_OFFSET(0))
                offsets.append(0)
            for i in range(len(self.objects)):
                offsets[i] = save_file.tell()
                save_file.write(self.objects[i].type)
                Gearoenix.save_string(save_file, self.objects[i].name)
                self.objects[i].save(save_file)
            save_file.write(self.TYPE_OBJECT_COUNT(len(self.geo_copies)))
            for geo_name in self.geo_copies:
                Gearoenix.save_string(save_file, geo_name)
                save_file.write(self.TYPE_OBJECT_COUNT(len(self.geo_copies[geo_name])))
                for geo in self.geo_copies[geo_name]:
                    save_file.write(self.TYPE_OBJECT_COUNT(geo.copy_number))
                    geo.save(save_file)
            cur_loc = save_file.tell()
            save_file.seek(table_offset, io.SEEK_SET)
            for i in range(len(self.objects)):
                save_file.write(self.objects[i].type)
                Gearoenix.save_string(save_file, self.objects[i].name)
                save_file.write(Gearoenix.Scene.TYPE_OFFSET(offsets[i]))
            save_file.seek(cur_loc, io.SEEK_SET)

    return Scene


Gearoenix.Scene = assigner()


def assigner():
    class Texture:
        def __init__(self, tex, index):
            super(Gearoenix.Texture, self).__init__()
            self.file_path = tex.image.filepath_from_user()
            self.name = tex.name
            self.index = index

        def save(self, save_file):
            tex_file = open(self.file_path, 'rb')
            save_file.write(tex_file.read())

    return Texture


Gearoenix.Texture = assigner()


def assigner():
    class CubeTexture:
        CUBE_TEXTURE_PREFIX = 'cube-'
        CUBE_TEXTURE_UP_POSTFIX = '-up'
        CUBE_TEXTURE_DOWN_POSTFIX = '-down'
        CUBE_TEXTURE_FRONT_POSTFIX = '-front'
        CUBE_TEXTURE_BACK_POSTFIX = '-back'
        CUBE_TEXTURE_LEFT_POSTFIX = '-left'
        CUBE_TEXTURE_RIGHT_POSTFIX = '-right'

        def __init__(self, name: str, index: int):
            file_path = []
            self.name = Gearoenix.CubeTexture.CUBE_TEXTURE_PREFIX + name
            self.index = index
            tex = bpy.data.textures[
                Gearoenix.CubeTexture.CUBE_TEXTURE_PREFIX + name + Gearoenix.CubeTexture.CUBE_TEXTURE_UP_POSTFIX]
            file_path.append(tex.image.filepath_from_user())
            tex = bpy.data.textures[
                Gearoenix.CubeTexture.CUBE_TEXTURE_PREFIX + name + Gearoenix.CubeTexture.CUBE_TEXTURE_DOWN_POSTFIX]
            file_path.append(tex.image.filepath_from_user())
            tex = bpy.data.textures[
                Gearoenix.CubeTexture.CUBE_TEXTURE_PREFIX + name + Gearoenix.CubeTexture.CUBE_TEXTURE_FRONT_POSTFIX]
            file_path.append(tex.image.filepath_from_user())
            tex = bpy.data.textures[
                Gearoenix.CubeTexture.CUBE_TEXTURE_PREFIX + name + Gearoenix.CubeTexture.CUBE_TEXTURE_BACK_POSTFIX]
            file_path.append(tex.image.filepath_from_user())
            tex = bpy.data.textures[
                Gearoenix.CubeTexture.CUBE_TEXTURE_PREFIX + name + Gearoenix.CubeTexture.CUBE_TEXTURE_RIGHT_POSTFIX]
            file_path.append(tex.image.filepath_from_user())
            tex = bpy.data.textures[
                Gearoenix.CubeTexture.CUBE_TEXTURE_PREFIX + name + Gearoenix.CubeTexture.CUBE_TEXTURE_LEFT_POSTFIX]
            file_path.append(tex.image.filepath_from_user())
            self.file_path = (
                file_path[0],
                file_path[1],
                file_path[2],
                file_path[3],
                file_path[4],
                file_path[5]
            )

        def save(self, save_file: io.BufferedWriter):
            offsets = [0] * 6
            offset = save_file.tell()
            for i in range(6):
                save_file.write(ctypes.c_uint32(offsets[i]))
            for i in range(6):
                offsets[i] = save_file.tell()
                tex_file = open(self.file_path[i], 'rb')
                save_file.write(tex_file.read())
            tmp_offset = save_file.tell()
            save_file.seek(offset, io.SEEK_SET)
            for i in range(6):
                save_file.write(ctypes.c_uint32(offsets[i]))
            save_file.seek(tmp_offset, io.SEEK_SET)

        @staticmethod
        def prepare_name(name: str) -> str:
            posts = [
                Gearoenix.CubeTexture.CUBE_TEXTURE_UP_POSTFIX,
                Gearoenix.CubeTexture.CUBE_TEXTURE_DOWN_POSTFIX,
                Gearoenix.CubeTexture.CUBE_TEXTURE_FRONT_POSTFIX,
                Gearoenix.CubeTexture.CUBE_TEXTURE_BACK_POSTFIX,
                Gearoenix.CubeTexture.CUBE_TEXTURE_LEFT_POSTFIX,
                Gearoenix.CubeTexture.CUBE_TEXTURE_RIGHT_POSTFIX
            ]
            for p in posts:
                if name.endswith(p):
                    return name[:len(name) - len(p)]

    return CubeTexture


Gearoenix.CubeTexture = assigner()


def assigner():
    class TextureManager:
        textures = dict()
        TEXTURE_TYPE_CUBE = ctypes.c_uint8(1)
        TEXTURE_TYPE_2D = ctypes.c_uint8(2)
        TYPE_TEXTURE_COUNT = ctypes.c_uint16
        TYPE_TEXTURE_INDEX = ctypes.c_uint16
        TYPE_TEXTURE_NAMES_COUNT = ctypes.c_uint8
        TYPE_TEXTURE_OFFSET = ctypes.c_uint32
        table_offset = 0

        @staticmethod
        def initialize():
            for t in bpy.data.textures:
                if t.name.startswith(Gearoenix.CubeTexture.CUBE_TEXTURE_PREFIX):
                    if t.name.endswith(Gearoenix.CubeTexture.CUBE_TEXTURE_UP_POSTFIX):
                        texture = Gearoenix.CubeTexture(
                            t.name[len(Gearoenix.CubeTexture.CUBE_TEXTURE_PREFIX): len(t.name) - len(
                                Gearoenix.CubeTexture.CUBE_TEXTURE_UP_POSTFIX)],
                            len(Gearoenix.TextureManager.textures))
                        texture.type = Gearoenix.TextureManager.TEXTURE_TYPE_CUBE
                    else:
                        continue
                else:
                    texture = Gearoenix.Texture(t, len(
                        Gearoenix.TextureManager.textures))  # Doubt !!!!!!!!!!!!!!!!!!!!!!!!!!!1
                    texture.type = Gearoenix.TextureManager.TEXTURE_TYPE_2D
                try:
                    t = Gearoenix.TextureManager.textures[texture.file_path]
                    t[0].add(texture.name)
                except KeyError:
                    Gearoenix.TextureManager.textures[texture.file_path] = [{texture.name}, texture, 0]

        @staticmethod
        def get_index(name):
            for v in Gearoenix.TextureManager.textures.values():
                if name in v[0]:
                    return v[1].index
            print('Error texture ' + name + ' not found.')
            raise Exception('Error texture ' + name + ' not found.')

        @staticmethod
        def write_table(save_file):
            Gearoenix.TextureManager.table_offset = save_file.tell()
            save_file.write(Gearoenix.TextureManager.TYPE_TEXTURE_COUNT(len(Gearoenix.TextureManager.textures)))
            for f in Gearoenix.TextureManager.textures.keys():
                save_file.write(
                    Gearoenix.TextureManager.TYPE_TEXTURE_NAMES_COUNT(len(Gearoenix.TextureManager.textures[f][0])))
                for s in Gearoenix.TextureManager.textures[f][0]:
                    Gearoenix.save_string(save_file, s)
                save_file.write(
                    Gearoenix.TextureManager.TYPE_TEXTURE_INDEX(Gearoenix.TextureManager.textures[f][1].index))
                save_file.write(Gearoenix.TextureManager.textures[f][1].type)
                save_file.write(Gearoenix.TextureManager.TYPE_TEXTURE_OFFSET(Gearoenix.TextureManager.textures[f][2]))

        @staticmethod
        def write_textures(save_file):
            for texture in Gearoenix.TextureManager.textures.values():
                print(texture)
                texture[2] = save_file.tell()
                texture[1].save(save_file)
            cur_loc = save_file.tell()
            save_file.seek(Gearoenix.TextureManager.table_offset, io.SEEK_SET)
            Gearoenix.TextureManager.write_table(save_file)
            save_file.seek(cur_loc, io.SEEK_SET)

    return TextureManager


Gearoenix.TextureManager = assigner()


def assigner():
    class SceneManager:
        scenes = []
        offsets = []
        table_offset = 0
        TYPE_SCENES_COUNT = ctypes.c_uint32
        TYPE_OFFSET = ctypes.c_uint32

        @staticmethod
        def initialize():
            for s in bpy.data.scenes:
                Gearoenix.SceneManager.offsets.append(0)
                Gearoenix.SceneManager.scenes.append(Gearoenix.Scene(s))

        @staticmethod
        def write_table(save_file):
            Gearoenix.SceneManager.table_offset = save_file.tell()
            save_file.write(Gearoenix.SceneManager.TYPE_SCENES_COUNT(len(Gearoenix.SceneManager.scenes)))
            for i in range(len(Gearoenix.SceneManager.scenes)):
                save_file.write(Gearoenix.SceneManager.TYPE_OFFSET(Gearoenix.SceneManager.offsets[i]))
                Gearoenix.save_string(save_file, Gearoenix.SceneManager.scenes[i].name)

        @staticmethod
        def write_scenes(save_file):
            for i in range(len(Gearoenix.SceneManager.scenes)):
                Gearoenix.SceneManager.offsets[i] = save_file.tell()
                Gearoenix.SceneManager.scenes[i].save(save_file)
            cur_loc = save_file.tell()
            save_file.seek(Gearoenix.SceneManager.table_offset, io.SEEK_SET)
            Gearoenix.SceneManager.write_table(save_file)
            save_file.seek(cur_loc, io.SEEK_SET)

    return SceneManager


Gearoenix.SceneManager = assigner()


def assigner():
    class Effect:
        TYPE_FILE_SIZE = ctypes.c_uint32

        def __init__(self, s):
            self.file_path = bpy.path.abspath(s.sound.filepath)
            if not self.file_path.endswith('.ogg'):
                raise Exception('Error only ogg Vorbis is supported now.')

        def save(self, save_file: io.BufferedWriter):
            data = open(self.file_path, 'rb')
            data = data.read()
            save_file.write(Effect.TYPE_FILE_SIZE(len(data)))
            save_file.write(data)
    return Effect

Gearoenix.Effect = assigner()


def assigner():
    class BackgroundMusic:
        TYPE_FILE_SIZE = ctypes.c_uint32

        def __init__(self, s):
            self.file_path = bpy.path.abspath(s.sound.filepath)
            if not self.file_path.endswith('.ogg'):
                raise Exception('Error only ogg Vorbis is supported now.')

        def save(self, save_file: io.BufferedWriter):
            data = open(self.file_path, 'rb')
            data = data.read()
            save_file.write(BackgroundMusic.TYPE_FILE_SIZE(len(data)))
            save_file.write(data)
    return BackgroundMusic

Gearoenix.BackgroundMusic = assigner()


def assigner():
    class AudioManager:
        TYPE_OFFSET = ctypes.c_uint32
        TYPE_AUDIO_COUNT = ctypes.c_uint32
        TYPE_AUDIO_TYPE = ctypes.c_uint8
        AUDIO_TYPE_BG_MUSIC = TYPE_AUDIO_TYPE(1)
        AUDIO_TYPE_EFFECT = TYPE_AUDIO_TYPE(2)
        PREFIX_BG_MUSIC = "back-music-"
        PREFIX_EFFECT = "effect-"
        audios = []
        table_offset = TYPE_OFFSET(0)

        @staticmethod
        def initialize():
            for s in bpy.data.speakers:
                if s.name.startswith(AudioManager.PREFIX_BG_MUSIC):
                    audio = Gearoenix.BackgroundMusic(s)
                    audio.name = s.name[len(AudioManager.PREFIX_BG_MUSIC):]
                    audio.type = AudioManager.AUDIO_TYPE_BG_MUSIC
                elif s.name.startswith(AudioManager.PREFIX_EFFECT):
                    audio = Gearoenix.Effect(s)
                    audio.name = s.name[len(AudioManager.PREFIX_EFFECT):]
                    audio.type = AudioManager.AUDIO_TYPE_EFFECT
                else:
                    raise Exception("Audio prefix must be 'back-music-' or 'effect-'.")
                AudioManager.audios.append(audio)

        @staticmethod
        def write_table(save_file: io.BufferedWriter):
            AudioManager.table_offset = AudioManager.TYPE_OFFSET(save_file.tell())
            save_file.write(AudioManager.TYPE_AUDIO_COUNT(len(AudioManager.audios)))
            for a in AudioManager.audios:
                save_file.write(a.type)
                Gearoenix.save_string(save_file, a.name)
                save_file.write(AudioManager.TYPE_OFFSET(0))

        @staticmethod
        def write_audios(save_file: io.BufferedWriter):
            for a in AudioManager.audios:
                a.offset = AudioManager.TYPE_OFFSET(save_file.tell())
                save_file.write(a.type)
                Gearoenix.save_string(save_file, a.name)
                a.save(save_file)

    return AudioManager

Gearoenix.AudioManager = assigner()


def assigner():
    def write_some_data(context, filepath):
        f = open(filepath, 'wb')
        Gearoenix.TextureManager.initialize()
        Gearoenix.SceneManager.initialize()
        Gearoenix.AudioManager.initialize()
        if sys.byteorder == 'little':
            f.write(ctypes.c_char(1))
        else:
            f.write(ctypes.c_char(0))
        Gearoenix.TextureManager.write_table(f)
        Gearoenix.SceneManager.write_table(f)
        Gearoenix.AudioManager.write_table(f)
        Gearoenix.TextureManager.write_textures(f)
        Gearoenix.SceneManager.write_scenes(f)
        Gearoenix.AudioManager.write_audios(f)
        f.close()

        return {'FINISHED'}

    return write_some_data


Gearoenix.write_some_data = assigner()


def assigner():
    class Exporter(Operator, ExportHelper):
        """This is a plug in for Gearoenix 3D file format"""
        bl_idname = "dusty_exporter.data_structure"  # important since its how bpy.ops.import_test.some_data is constructed
        bl_label = "Export Gearoenix 3D"

        # ExportHelper mixin class uses this
        filename_ext = ".gx3d"

        filter_glob = StringProperty(
            default="*.gx3d",
            options={'HIDDEN'},
        )

        # List of operator properties, the attributes will be assigned
        # to the class instance from the operator settings before calling.
        # use_setting = BoolProperty(
        #         name="Example Boolean",
        #         description="Example Tooltip.",
        #         default=True,
        #         )
        #
        # type = EnumProperty(
        #         name="Example Enum",
        #         description="Choose between two items.",
        #         items=(('OPT_A', "First Option", "Description one"),
        #                ('OPT_B', "Second Option", "Description two")),
        #         default='OPT_A',
        #         )

        def execute(self, context):
            return Gearoenix.write_some_data(context, self.filepath)  # self.use_setting

    return Exporter


Gearoenix.Exporter = assigner()


def assigner():
    # Only needed if you want to add into a dynamic menu
    def menu_func_export(self, context):
        self.layout.operator(Gearoenix.Exporter.bl_idname, text="Gearoenix 3D Exporter (.gx3d)")

    return menu_func_export


Gearoenix.menu_func_export = assigner()


def unregister():
    bpy.utils.unregister_class(Gearoenix.Exporter)
    bpy.types.INFO_MT_file_export.remove(Gearoenix.menu_func_export)


def register():
    bpy.utils.register_class(Gearoenix.OkOperator)
    bpy.utils.register_class(Gearoenix.MessageOperator)
    bpy.utils.register_class(Gearoenix.Exporter)
    bpy.types.INFO_MT_file_export.append(Gearoenix.menu_func_export)


if __name__ == "__main__":
    register()

    # test call
    # bpy.ops.export_test.some_data('INVOKE_DEFAULT')
