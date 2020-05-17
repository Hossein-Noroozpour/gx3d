"""
GX3D file exporter main module
"""

import mathutils
import bpy_extras
import bpy
import tempfile
import sys
import subprocess
import os
import math
import io
import gc
import enum
import ctypes
import collections

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


class Gearoenix:
    """Main class and a pseudo-namespace of the GX3D exporter"""

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
    EXPORT_FILE_PATH = ''

    GX3D_FILE = None
    CPP_FILE = None
    RUST_FILE = None

    BAKED_SKYBOX_CUBE_RES = '1024'
    IRRADIANCE_RES = '128'
    RADIANCE_RES = '512'

    IBL_BAKER_ENVIRONMENT_NAME = 'GEAROENIX_IBL_BAKER'

    last_id = None

    @staticmethod
    def terminate(*msgs):
        """Terminates the plugin process"""
        final_msg = ''
        for msg in msgs:
            final_msg += str(msg) + ' '
        print('Fatal error: ' + final_msg)
        raise Exception(final_msg)

    @staticmethod
    def initialize():
        """Initializes the class propeties that will be used in other functions"""
        Gearoenix.last_id = 1024
        Gearoenix.GX3D_FILE = open(Gearoenix.EXPORT_FILE_PATH, mode='wb')
        dirstr = os.path.dirname(Gearoenix.EXPORT_FILE_PATH)
        filename = Gearoenix.EXPORT_FILE_PATH[len(dirstr) + 1:]
        p_dir_str = os.path.dirname(dirstr)
        if Gearoenix.EXPORT_VULKUST:
            rs_file = filename.replace('.', '_') + '.rs'
            Gearoenix.RUST_FILE = open(p_dir_str + '/src/' + rs_file, mode='w')
        elif Gearoenix.EXPORT_GEAROENIX:
            Gearoenix.CPP_FILE = open(
                Gearoenix.EXPORT_FILE_PATH + '.hpp', mode='w')
        else:
            Gearoenix.terminate('Unexpected engine selection')

    @staticmethod
    def log_info(*msgs):
        """Logs in debug mode"""
        if Gearoenix.DEBUG_MODE:
            print('Info:', *msgs)

    @staticmethod
    def write_float(f):
        Gearoenix.GX3D_FILE.write(Gearoenix.TYPE_FLOAT(f))

    @staticmethod
    def write_u64(n):
        Gearoenix.GX3D_FILE.write(Gearoenix.TYPE_U64(n))

    @staticmethod
    def write_u32(n):
        Gearoenix.GX3D_FILE.write(Gearoenix.TYPE_U32(n))

    @staticmethod
    def write_u16(n):
        Gearoenix.GX3D_FILE.write(Gearoenix.TYPE_U16(n))

    @staticmethod
    def write_u8(n):
        Gearoenix.GX3D_FILE.write(Gearoenix.TYPE_U8(n))

    @staticmethod
    def write_type_id(n):
        Gearoenix.write_u8(n)

    @staticmethod
    def write_instances_ids(instances):
        Gearoenix.write_u64(len(instances))
        for ins in instances:
            Gearoenix.write_id(ins.instance_id)

    @staticmethod
    def write_id(obj_id):
        Gearoenix.write_u64(obj_id)

    @staticmethod
    def write_vector(v, element_count=3):
        for i in range(element_count):
            Gearoenix.write_float(v[i])

    @staticmethod
    def write_matrix(matrix):
        for i in range(0, 4):
            for j in range(0, 4):
                Gearoenix.write_float(matrix[j][i])

    @staticmethod
    def write_u32_array(arr):
        Gearoenix.write_u64(len(arr))
        for i in arr:
            Gearoenix.write_u32(i)

    @staticmethod
    def write_u64_array(arr):
        Gearoenix.write_u64(len(arr))
        for i in arr:
            Gearoenix.write_u64(i)

    @staticmethod
    def write_bool(b):
        data = 0
        if b:
            data = 1
        Gearoenix.GX3D_FILE.write(Gearoenix.TYPE_BOOLEAN(data))

    @staticmethod
    def write_file_content(name):
        Gearoenix.GX3D_FILE.write(open(name, 'rb').read())

    @staticmethod
    def file_tell():
        return Gearoenix.GX3D_FILE.tell()

    @staticmethod
    def limit_check(val, maxval=1.0, minval=0.0, obj=None):
        if val > maxval or val < minval:
            msg = 'Out of range value'
            if obj is not None:
                msg += ', in object: ' + obj.name
            Gearoenix.terminate(msg)

    @staticmethod
    def uint_check(s):
        try:
            if int(s) >= 0:
                return True
        except ValueError:
            Gearoenix.terminate('Type error')
        Gearoenix.terminate('Type error')

    @staticmethod
    def get_origin_name(blender_object):
        origin_name = blender_object.name.strip().split('.')
        num_dot = len(origin_name)
        if num_dot > 2 or num_dot < 1:
            Gearoenix.terminate('Wrong name in:', blender_object.name)
        elif num_dot == 1:
            return None
        try:
            int(origin_name[1])
        except ValueError:
            Gearoenix.terminate('Wrong name in:', blender_object.name)
        return origin_name[0]

    @staticmethod
    def is_zero(f):
        return -Gearoenix.EPSILON < f < Gearoenix.EPSILON

    @staticmethod
    def has_transformation(blender_object):
        m = blender_object.matrix_world
        if blender_object.parent is not None:
            m = blender_object.parent.matrix_world.inverted() @ m
        for i in range(4):
            for j in range(4):
                if i == j:
                    if not Gearoenix.is_zero(m[i][j] - 1.0):
                        return True
                elif not Gearoenix.is_zero(m[i][j]):
                    return True
        return False

    @staticmethod
    def write_string(s):
        bs = bytes(s, 'utf-8')
        Gearoenix.write_u64(len(bs))
        for b in bs:
            Gearoenix.write_u8(b)

    @staticmethod
    def const_string(s):
        ss = s.replace('-', '_')
        ss = ss.replace('/', '_')
        ss = ss.replace('.', '_')
        ss = ss.replace('C:\\', '_')
        ss = ss.replace('c:\\', '_')
        ss = ss.replace('\\', '_')
        ss = ss.upper()
        return ss

    @staticmethod
    def read_file(f):
        return open(f, 'rb').read()

    @staticmethod
    def write_file(f):
        Gearoenix.write_u64(len(f))
        Gearoenix.GX3D_FILE.write(f)

    @staticmethod
    def enum_max_check(e):
        if e == e.MAX:
            Gearoenix.terminate('UNEXPECTED')

    @staticmethod
    def write_start_module(c):
        mod_name = c.__name__
        if Gearoenix.EXPORT_VULKUST:
            Gearoenix.RUST_FILE.write('#[allow(dead_code)]\n')
            Gearoenix.RUST_FILE.write(
                '#[cfg_attr(debug_assertions, derive(Debug))]\n')
            Gearoenix.RUST_FILE.write('#[repr(u64)]\n')
            Gearoenix.RUST_FILE.write('pub enum ' + mod_name + ' {\n')
            Gearoenix.RUST_FILE.write('    Unexpected = 0,\n')
        elif Gearoenix.EXPORT_GEAROENIX:
            Gearoenix.CPP_FILE.write('namespace ' + mod_name + '\n{\n')

    @staticmethod
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

    @staticmethod
    def write_name_id(name, item_id):
        if Gearoenix.EXPORT_VULKUST:
            Gearoenix.RUST_FILE.write(
                '    ' + Gearoenix.make_camel_underlined(name) + ' = ' + str(int(item_id)) + ',\n')
        elif Gearoenix.EXPORT_GEAROENIX:
            Gearoenix.CPP_FILE.write(
                '    const gearoenix::core::Id ' + name + ' = ' + str(item_id) + ';\n')

    @staticmethod
    def write_end_module():
        if Gearoenix.EXPORT_VULKUST:
            Gearoenix.RUST_FILE.write('}\n\n')
        elif Gearoenix.EXPORT_GEAROENIX:
            Gearoenix.CPP_FILE.write('}\n')

    @staticmethod
    def find_common_starting(s1, s2):
        s = ''
        l = min(len(s1), len(s2))
        for i in range(l):
            if s1[i] == s2[i]:
                s += s1[i]
            else:
                break
        return s

    @staticmethod
    def find_tools():
        Gearoenix.IBL_BAKER_PATH = os.environ[Gearoenix.IBL_BAKER_ENVIRONMENT_NAME]

    class GxTmpFile:
        """A better temporary file"""

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

    @staticmethod
    def create_sky_resources(file: str):
        baked_cube = Gearoenix.GxTmpFile()
        irradiance = Gearoenix.GxTmpFile()
        radiance = Gearoenix.GxTmpFile()
        subprocess.run(args=[
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
        ], check=True)
        return (baked_cube, irradiance, radiance)

    @staticmethod
    def menu_func_export(obj, _):
        obj.layout.operator(
            Gearoenix.Exporter.bl_idname, text='Gearoenix 3D Exporter (.gx3d)')

    @staticmethod
    def register_plugin():
        bpy.utils.register_class(Gearoenix.Exporter)
        try:
            bpy.types.TOPBAR_MT_file_export.append(Gearoenix.menu_func_export)
        except AttributeError:
            return

    @staticmethod
    def write_tables():
        Gearoenix.Camera.write_table()
        Gearoenix.Audio.write_table()
        Gearoenix.Light.write_table()
        Gearoenix.Texture.write_table()
        Gearoenix.Font.write_table()
        Gearoenix.Mesh.write_table()
        Gearoenix.Model.write_table()
        Gearoenix.Reflection.write_table()
        Gearoenix.Skybox.write_table()
        Gearoenix.Constraint.write_table()
        Gearoenix.Scene.write_table()

    @staticmethod
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
        Gearoenix.Reflection.init()
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
        Gearoenix.Reflection.write_all()
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


class Asset:
    """
    Parent class for all assets.
    ...
    Attributes
    ----------
    instances : dict
        instances of that subclass all together
    name : str
        name of the instance
    instance_id : int
        id of instance
    offset : int
        offset of object in the gx3d file
    blender_object: bpy_types.Objec
        corresponding blender object
    instance_type : int
        each instance of subclass of this class must define and initialize it."""

    def __init__(self, blender_object):
        self.instance_type = None
        self.offset = 0
        self.blender_object = blender_object
        self.instance_id = Gearoenix.last_id
        Gearoenix.last_id += 1
        self.name = self.__class__.get_name_from_blender_object(
            blender_object)
        if not blender_object.name.startswith(self.__class__.get_prefix()):
            Gearoenix.terminate(
                'Unexpected name in ',
                self.__class__.__name__)
        if self.name in self.__class__.instances:
            Gearoenix.terminate(self.name, 'is already in instances.')
        self.__class__.instances[self.name] = self

    @classmethod
    def get_prefix(cls):
        return cls.__name__.lower() + '-'

    def write(self):
        Gearoenix.write_type_id(self.instance_type)

    @classmethod
    def write_all(cls):
        instances = sorted(
            cls.instances.items(),
            key=lambda kv: kv[1].instance_id)
        for (_, item) in instances:
            item.offset = Gearoenix.file_tell()
            item.write()

    def get_reference_name(self):
        """The name that will be used in table as a reference."""
        name = self.name[len(self.__class__.get_prefix()):]
        return name[name.find('-') + 1:]

    @classmethod
    def find_common_starting(cls) -> str:
        common_starting = ''
        if len(cls.instances) < 2:
            return common_starting
        for k in cls.instances:
            common_starting = Gearoenix.const_string(k)
            break
        for k in cls.instances:
            common_starting = Gearoenix.find_common_starting(
                common_starting, Gearoenix.const_string(k))
        return common_starting

    @classmethod
    def check_names(cls):
        """Checks the names that required and their uniqueness"""
        if not Gearoenix.DEBUG_MODE:
            return
        names = set()
        const_names = set()
        for k, item in cls.instances.items():
            const_name = Gearoenix.const_string(k)
            name = item.get_reference_name()
            if const_name in const_names or name in names:
                Gearoenix.terminate(
                    "Duplicated name in module", item.__class__.name,
                    "name:", item.blender_object.name)
            names.add(name)
            const_names.add(const_name)

    @classmethod
    def write_table(cls):
        cls.check_names()
        Gearoenix.write_start_module(cls)
        instances = sorted(
            cls.instances.items(),
            key=lambda kv: kv[1].instance_id)
        common_starting = cls.find_common_starting()
        Gearoenix.write_u64(len(instances))
        Gearoenix.log_info('Number of', cls.__name__, len(instances))
        for _, item in instances:
            Gearoenix.write_id(item.instance_id)
            Gearoenix.write_u64(item.offset)
            Gearoenix.write_string(item.get_reference_name())
            Gearoenix.log_info(
                'instance_id:', item.instance_id,
                'offset:', item.offset,
                'name:', item.get_reference_name())
            name = Gearoenix.const_string(item.name)[len(common_starting):]
            Gearoenix.write_name_id(name, item.instance_id)
        Gearoenix.write_end_module()

    @staticmethod
    def get_name_from_blender_object(blender_object):
        return blender_object.name

    @classmethod
    def read(cls, blender_object):
        name = cls.get_name_from_blender_object(blender_object)
        if not blender_object.name.startswith(cls.get_prefix()):
            return None
        if name in cls.instances:
            return None
        return cls(blender_object)

    @classmethod
    def init(cls):
        cls.instances = dict()

    def get_offset(self):
        return self.offset


Gearoenix.Asset = Asset


class UniqueAsset(Gearoenix.Asset):
    """
    This class is parent of those classes having instances with
    an origin that shares most of the data (e.g. Mesh) is and
    must be kept unique in all other instances to prevent data redundancy
    ...
    Attributes
    ----------
    origin_instance: Object
    """

    def __init__(self, blender_object):
        self.origin_instance = None
        origin_name = Gearoenix.get_origin_name(blender_object)
        if origin_name is None:
            super().__init__(blender_object)
        else:
            self.origin_instance = self.__class__.instances[origin_name]
            self.name = blender_object.name
            self.instance_id = self.origin_instance.instance_id
            self.instance_type = self.origin_instance.instance_type
            self.blender_object = blender_object

    def write(self):
        if self.origin_instance is not None:
            Gearoenix.terminate(
                'This object must not written like this. in', self.name)
        super().write()

    @classmethod
    def read(cls, blender_object):
        if not blender_object.name.startswith(cls.get_prefix()):
            return None
        origin_name = Gearoenix.get_origin_name(blender_object)
        if origin_name is None:
            return super().read(blender_object)
        super().read(bpy.data.objects[origin_name])
        return cls(blender_object)


Gearoenix.UniqueAsset = UniqueAsset


class ReferencingAsset(Gearoenix.Asset):
    """
    This class is parent of those classes having instances that
    reference same data (e.g. Texture)
    ...
    Attributes
    ----------
    origin_instance: Object
    """

    def __init__(self, blender_object):
        self.origin_instance = None
        self.name = self.__class__.get_name_from_blender_object(blender_object)
        if self.name not in self.__class__.instances:
            super().__init__(blender_object)
        else:
            self.origin_instance = self.__class__.instances[self.name]
            self.instance_id = self.origin_instance.instance_id
            self.instance_type = self.origin_instance.instance_type
            self.blender_object = blender_object

    @classmethod
    def read(cls, blender_object):
        if not blender_object.name.startswith(cls.get_prefix()):
            return None
        name = cls.get_name_from_blender_object(blender_object)
        if name not in cls.instances:
            return super().read(blender_object)
        return cls(blender_object)

    def write(self):
        if self.origin_instance is not None:
            Gearoenix.terminate(
                'This object must not written like this. in', self.name)
        super().write()

    def get_offset(self):
        if self.origin_instance is None:
            return self.offset
        return self.origin_instance.offset


Gearoenix.ReferencingAsset = ReferencingAsset


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


Gearoenix.Aabb = Aabb


class Audio(Gearoenix.ReferencingAsset):
    TYPE_MUSIC = 1
    TYPE_OBJECT = 2

    @classmethod
    def init(cls):
        super().init()
        cls.MUSIC_PREFIX = cls.get_prefix() + 'music-'
        cls.OBJECT_PREFIX = cls.get_prefix() + 'object-'

    def __init__(self, blender_object):
        super().__init__(blender_object)
        if blender_object.startswith(self.MUSIC_PREFIX):
            self.instance_type = self.TYPE_MUSIC
        elif blender_object.startswith(self.OBJECT_PREFIX):
            self.instance_type = self.TYPE_OBJECT
        else:
            Gearoenix.terminate('Unspecified type in:', blender_object.name)
        self.file = Gearoenix.read_file(self.name)

    def write(self):
        super().write()
        Gearoenix.write_file(self.file)

    @staticmethod
    def get_name_from_blender_object(blender_object):
        if blender_object.type != 'SPEAKER':
            Gearoenix.terminate('Audio must be speaker: ', blender_object.name)
        aud = blender_object.data
        if aud is None:
            Gearoenix.terminate(
                'Audio is not set in speaker: ', blender_object.name)
        aud = aud.sound
        if aud is None:
            Gearoenix.terminate(
                'Sound is not set in speaker: ', blender_object.name)
        filepath = aud.filepath.strip()
        if filepath is None or len(filepath) == 0:
            Gearoenix.terminate(
                'Audio is not specified yet in speaker: ', blender_object.name)
        if not filepath.endswith('.ogg'):
            Gearoenix.terminate('Use OGG instead of ', filepath)
        return filepath


Gearoenix.Audio = Audio


class Light(Gearoenix.Asset):
    TYPE_CONE = 1
    TYPE_DIRECTIONAL = 2
    TYPE_POINT = 3

    @classmethod
    def init(cls):
        super().init()
        cls.DIRECTIONAL_PREFIX = cls.get_prefix() + 'directional-'
        cls.POINT_PREFIX = cls.get_prefix() + 'point-'
        cls.CONE_PREFIX = cls.get_prefix() + 'cone-'

    def __init__(self, blender_object):
        super().__init__(blender_object)
        if self.blender_object.type != 'LIGHT':
            Gearoenix.terminate('Light type is incorrect:',
                                blender_object.name)
        if blender_object.name.startswith(self.DIRECTIONAL_PREFIX):
            if blender_object.data.type != 'SUN':
                Gearoenix.terminate(blender_object.name,
                                    "should be a sun light")
            self.instance_type = self.TYPE_DIRECTIONAL
        elif blender_object.name.startswith(self.POINT_PREFIX):
            if blender_object.data.type != 'POINT':
                Gearoenix.terminate(blender_object.name,
                                    "should be a point light")
            self.instance_type = self.TYPE_POINT
        else:
            Gearoenix.terminate('Unspecified type in:', blender_object.name)

    def write(self):
        super().write()
        color = self.blender_object.data.color
        strength = self.blender_object.data.energy
        Gearoenix.write_float(color[0] * strength)
        Gearoenix.write_float(color[1] * strength)
        Gearoenix.write_float(color[2] * strength)
        Gearoenix.write_bool(self.blender_object.data.use_shadow)
        if self.instance_type == self.TYPE_POINT:
            Gearoenix.write_vector(self.blender_object.location)
        elif self.instance_type == self.TYPE_DIRECTIONAL:
            v = self.blender_object.matrix_world @ mathutils.Vector(
                (0.0, 0.0, -1.0, 0.0))
            v.normalize()
            Gearoenix.write_vector(v)


Gearoenix.Light = Light


class Camera(Gearoenix.Asset):
    TYPE_PERSPECTIVE = 1
    TYPE_ORTHOGRAPHIC = 2

    @classmethod
    def init(cls):
        super().init()
        cls.PERSPECTIVE_PREFIX = cls.get_prefix() + 'perspective-'
        cls.ORTHOGRAPHIC_PREFIX = cls.get_prefix() + 'orthographic-'

    def __init__(self, blender_object):
        super().__init__(blender_object)
        if self.blender_object.type != 'CAMERA':
            Gearoenix.terminate('Camera type is incorrect:',
                                blender_object.name)
        if blender_object.name.startswith(self.PERSPECTIVE_PREFIX):
            self.instance_type = self.TYPE_PERSPECTIVE
            if blender_object.data.type != 'PERSP':
                Gearoenix.terminate(
                    'Camera type is incorrect:', blender_object.name)
        elif blender_object.name.startswith(self.ORTHOGRAPHIC_PREFIX):
            self.instance_type = self.TYPE_ORTHOGRAPHIC
            if blender_object.data.type != 'ORTHO':
                Gearoenix.terminate(
                    'Camera type is incorrect:', blender_object.name)
        else:
            Gearoenix.terminate('Unspecified type in:', blender_object.name)

    def write(self):
        super().write()
        cam = self.blender_object.data
        Gearoenix.write_vector(self.blender_object.location)
        Gearoenix.log_info(
            "Camera location is:",
            str(self.blender_object.location))
        Gearoenix.write_vector(
            self.blender_object.matrix_world.to_quaternion(), 4)
        Gearoenix.log_info("Camera quaternion is:",
                           str(self.blender_object.matrix_world.to_quaternion()))
        Gearoenix.write_float(cam.clip_start)
        Gearoenix.write_float(cam.clip_end)
        if self.instance_type == self.TYPE_PERSPECTIVE:
            Gearoenix.write_float(cam.angle_x)
        elif self.instance_type == self.TYPE_ORTHOGRAPHIC:
            Gearoenix.write_float(cam.ortho_scale)
        else:
            Gearoenix.terminate('Unspecified type in:',
                                self.blender_object.name)


Gearoenix.Camera = Camera


class Constraint(Gearoenix.Asset):
    TYPE_PLACER = 1
    TYPE_TRACKER = 2
    TYPE_SPRING = 3
    TYPE_SPRING_JOINT = 4

    @classmethod
    def init(cls):
        super().init()
        cls.PLACER_PREFIX = cls.get_prefix() + 'placer-'

    def __init__(self, blender_object):
        super().__init__(blender_object)
        if blender_object.name.startswith(self.PLACER_PREFIX):
            self.instance_type = self.TYPE_PLACER
            self.init_placer()
        else:
            Gearoenix.terminate('Unspecified type in:', blender_object.name)

    def write(self):
        super().write()
        if self.instance_type == self.TYPE_PLACER:
            self.write_placer()
        else:
            Gearoenix.terminate('Unspecified type in:',
                                self.blender_object.name)

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
        if self.blender_object.type != B_TYPE:
            Gearoenix.terminate(DESC, 'type must be', B_TYPE,
                                'in object:', self.blender_object.name)
        if len(self.blender_object.children) < 1:
            Gearoenix.terminate(
                DESC, 'must have more than 0 children, in object:', self.blender_object.name)
        self.model_children = []
        for c in self.blender_object.children:
            ins = Gearoenix.Model.read(c)
            if ins is None:
                Gearoenix.terminate(
                    DESC, 'can only have model as its child, in object:', self.blender_object.name)
            self.model_children.append(ins)
        self.attrs = [None for i in range(6)]
        if ATT_X_MIDDLE in self.blender_object:
            self.check_trans()
            self.attrs[0] = self.blender_object[ATT_X_MIDDLE]
        if ATT_Y_MIDDLE in self.blender_object:
            self.check_trans()
            self.attrs[1] = self.blender_object[ATT_Y_MIDDLE]
        if ATT_X_LEFT in self.blender_object:
            self.attrs[2] = self.blender_object[ATT_X_LEFT]
        if ATT_X_RIGHT in self.blender_object:
            self.attrs[3] = self.blender_object[ATT_X_RIGHT]
        if ATT_Y_UP in self.blender_object:
            self.attrs[4] = self.blender_object[ATT_Y_UP]
        if ATT_Y_DOWN in self.blender_object:
            self.attrs[5] = self.blender_object[ATT_Y_DOWN]
        if ATT_RATIO in self.blender_object:
            self.ratio = self.blender_object[ATT_RATIO]
        else:
            self.ratio = None
        self.placer_type = 0
        for i in range(len(self.attrs)):
            if self.attrs[i] is not None:
                self.placer_type |= (1 << i)
        if self.placer_type not in {4, 8, 33}:
            Gearoenix.terminate(
                DESC, 'must have meaningful combination, in object:', self.blender_object.name)

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
            Gearoenix.terminate(
                'It is not implemented, in object:', self.blender_object.name)
        childrenids = []
        for c in self.model_children:
            childrenids.append(c.instance_id)
        childrenids.sort()
        Gearoenix.write_u64_array(childrenids)

    def check_trans(self):
        if Gearoenix.has_transformation(self.blender_object):
            Gearoenix.terminate(
                'This object should not have any transformation, in:', self.blender_object.name)


Gearoenix.Constraint = Constraint


class Collider:
    GHOST = 1
    MESH = 2
    PREFIX = 'collider-'
    CHILDREN = []

    def __init__(self, blender_object=None):
        if blender_object is None:
            if self.MY_TYPE == self.GHOST:
                return
            else:
                Gearoenix.terminate('Unexpected blender_object is None')
        if not blender_object.name.startswith(self.PREFIX):
            Gearoenix.terminate(
                'Collider object name is wrong. In:', blender_object.name)
        self.blender_object = blender_object

    def write(self):
        Gearoenix.write_type_id(self.MY_TYPE)

    @classmethod
    def read(cls, pb_obj):
        collider_object = None
        for blender_object in pb_obj.children:
            for c in cls.CHILDREN:
                if blender_object.name.startswith(c.PREFIX):
                    if collider_object is not None:
                        Gearoenix.terminate(
                            'Only one collider is acceptable. In model:', pb_obj.name)
                    collider_object = c(blender_object)
        if collider_object is None:
            return Gearoenix.GhostCollider()
        return collider_object


Gearoenix.Collider = Collider


class GhostCollider(Gearoenix.Collider):
    MY_TYPE = Gearoenix.Collider.GHOST
    PREFIX = Gearoenix.Collider.PREFIX + 'ghost-'


Gearoenix.GhostCollider = GhostCollider
Gearoenix.Collider.CHILDREN.append(Gearoenix.GhostCollider)


class MeshCollider(Gearoenix.Collider):
    MY_TYPE = Gearoenix.Collider.MESH
    PREFIX = Gearoenix.Collider.PREFIX + 'mesh-'

    def __init__(self, blender_object):
        super().__init__(blender_object)
        self.blender_object = blender_object
        if blender_object.type != 'MESH':
            Gearoenix.terminate(
                'Mesh collider must have mesh object type, In model:', blender_object.name)
        if has_transformation(blender_object):
            Gearoenix.terminate(
                'Mesh collider can not have any transformation, in:', blender_object.name)
        msh = blender_object.data
        self.indices = []
        self.vertices = msh.vertices
        for p in msh.polygons:
            if len(p.vertices) > 3:
                Gearoenix.terminate('Object', blender_object.name,
                                    'is not triangulated!')
            for i in p.vertices:
                self.indices.append(i)

    def write(self):
        super().write()
        Gearoenix.write_u64(len(self.vertices))
        for v in self.vertices:
            Gearoenix.write_vector(v.co)
        Gearoenix.write_u32_array(self.indices)


Gearoenix.MeshCollider = MeshCollider
Gearoenix.Collider.CHILDREN.append(Gearoenix.MeshCollider)


class Texture(Gearoenix.ReferencingAsset):
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
                self.blender_object.name,
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

    def __init__(self, blender_object):
        super().__init__(blender_object)
        if blender_object.name.startswith(self.D2_PREFIX):
            self.file = Gearoenix.read_file(self.name)
            self.instance_type = self.TYPE_2D
        elif blender_object.name.startswith(self.D3_PREFIX):
            self.file = Gearoenix.read_file(self.name)
            self.instance_type = self.TYPE_D3
        elif blender_object.name.startswith(self.CUBE_PREFIX):
            self.init_6_face()
            self.instance_type = self.TYPE_CUBE
        else:
            Gearoenix.terminate(
                'Unspecified texture type, in:', blender_object.name)

    def write(self):
        super().write()
        Gearoenix.write_u8(13)  # texture_format TextureFormat::RgbaUint8
        Gearoenix.write_u8(7)   # min_filter     Filter::LinearMipmapLinear;
        Gearoenix.write_u8(5)   # mag_filter     Filter::Linear;
        Gearoenix.write_u8(3)   # wrap_s         Wrap::Repeat;
        Gearoenix.write_u8(3)   # wrap_t         Wrap::Repeat;
        Gearoenix.write_u8(3)   # wrap_r         Wrap::Repeat;
        if self.instance_type == self.TYPE_2D:
            Gearoenix.write_u16(self.blender_object.size[0])
            Gearoenix.write_u16(self.blender_object.size[1])
            Gearoenix.write_file(self.file)
        elif self.instance_type == self.TYPE_CUBE:
            self.write_6_face()
        else:
            Gearoenix.terminate(
                'Unspecified texture type, in:', self.blender_object.name)

    @staticmethod
    def get_name_from_blender_object(blender_object):
        if blender_object.type != 'IMAGE':
            Gearoenix.terminate('Unrecognized type for texture')
        filepath = bpy.path.abspath(blender_object.filepath_raw).strip()
        if filepath is None or len(filepath) == 0:
            Gearoenix.terminate('Filepass is empty:', blender_object.name)
        return filepath

    def is_cube(self):
        return self.instance_type == self.TYPE_CUBE

    def get_reference_name(self):
        """Overrided methode of Asset."""
        name = self.blender_object.name[len(self.__class__.get_prefix()):]
        return name[name.find('-') + 1:]


Gearoenix.Texture = Texture


class Font(Gearoenix.ReferencingAsset):
    TYPE_2D = 1
    TYPE_3D = 2

    @classmethod
    def init(cls):
        super().init()
        cls.D2_PREFIX = cls.get_prefix() + '2d-'
        cls.D3_PREFIX = cls.get_prefix() + '3d-'

    def __init__(self, blender_object):
        super().__init__(blender_object)
        if blender_object.name.startswith(self.D2_PREFIX):
            self.instance_type = self.TYPE_2D
        elif blender_object.name.startswith(self.D3_PREFIX):
            self.instance_type = self.TYPE_3D
        else:
            Gearoenix.terminate(
                'Unspecified font type, in:', blender_object.name)
        self.file = Gearoenix.read_file(self.name)

    def write(self):
        super().write()
        Gearoenix.write_file(self.file)

    @staticmethod
    def get_name_from_blender_object(blender_object):
        filepath = None
        if str(type(blender_object)) == "<class 'bpy.types.VectorFont'>":
            filepath = bpy.path.abspath(blender_object.filepath).strip()
        else:
            Gearoenix.terminate('Unrecognized type for font')
        if filepath is None or len(filepath) == 0:
            Gearoenix.terminate('Filepass is empty:', blender_object.name)
        if not filepath.endswith('.ttf'):
            Gearoenix.terminate('Use TTF for font, in:', filepath)
        return filepath


Gearoenix.Font = Font


class Material:
    TYPE_PBR = 1
    TYPE_UNLIT = 2

    PBR_PREFIX = 'pbr-'
    UNLIT_PREFIX = 'unlit-'

    FIELD_IS_FLOAT = 1
    FIELD_IS_TEXTURE = 2
    FIELD_IS_VECTOR = 3

    def read_links(self, name):
        if name not in self.inputs or self.inputs[name] is None:
            Gearoenix.terminate('Node input', name,
                                'is not correct in', blender_object.name)
        i = self.inputs[name]
        if len(i.links) < 1:
            return i.default_value
        elif len(i.links) == 1:
            if i.links[0] is None or i.links[0].from_node is None or i.links[0].from_node.image is None:
                Gearoenix.terminate(
                    'A link can be only a default or a texture link, wrong link in:', blender_object.name, 'link:', i.name)
            img = i.links[0].from_node.image
            txt = Gearoenix.Texture.read(img)
            if txt is None:
                Gearoenix.terminate(
                    'Your texture name is wrong in:', self.blender_object.name,
                    'link:', i.name, 'texture:', img.name)
            return txt
        else:
            Gearoenix.terminate(
                'Unexpected number of links in:', blender_object.name, 'link:', i.name)

    def init_pbr(self):
        self.init_unlit()
        self.emission = self.read_links('Emission')
        self.metallic = self.read_links('Metallic')
        self.normal_map = self.read_links('Normal')
        self.roughness = self.read_links('Roughness')
        if isinstance(self.metallic, Gearoenix.Texture) != isinstance(self.roughness, Gearoenix.Texture):
            Gearoenix.terminate(
                '"Metallic" and "Roughness" must be both scalar or texture:', self.blender_object.name)
        if isinstance(self.metallic, Gearoenix.Texture) and self.metallic.instance_id != self.roughness.instance_id:
            Gearoenix.terminate(
                '"Metallic" and "Roughness" must be both pointing to the same texture:', self.blender_object.name)

    def init_unlit(self):
        self.alpha = self.read_links('Alpha')
        self.base_color = self.read_links('Base Color')
        if isinstance(self.alpha, Gearoenix.Texture) and (not isinstance(self.base_color, Gearoenix.Texture) or self.alpha.instance_id != self.base_color.instance_id):
            Gearoenix.terminate(
                'If "Alpha" is texture then it must point to the texture that "Base Color" is pointing:', self.blender_object.name)
        if not self.mat.use_backface_culling:
            Gearoenix.terminate(
                'Matrial must be only back-face culling enabled in:', self.blender_object.name)
        if self.mat.blend_method not in {'CLIP', 'BLEND'}:
            Gearoenix.terminate(
                '"Blend Mode" in material must be set to "Alpha Clip" or "Alpha Blend" in:', self.blender_object.name)
        self.is_tansparent = self.mat.blend_method == 'BLEND'
        if self.mat.shadow_method not in {'CLIP', 'NONE'}:
            Gearoenix.terminate(
                '"Shadow Mode" in material must be set to "Alpha Clip" or "None" in:', self.blender_object.name)
        self.is_shadow_caster = self.mat.shadow_method != 'NONE'
        self.alpha_cutoff = self.mat.alpha_threshold

    def __init__(self, blender_object):
        self.blender_object = blender_object
        if len(blender_object.material_slots) < 1:
            Gearoenix.terminate('There is no material:', blender_object.name)
        if len(blender_object.material_slots) > 1:
            Gearoenix.terminate(
                'There must be only one material slot:', blender_object.name)
        mat = blender_object.material_slots[0]
        if mat.material is None:
            Gearoenix.terminate(
                'Material does not exist in:', blender_object.name)
        self.mat = mat.material
        if self.mat.node_tree is None:
            Gearoenix.terminate(
                'Material node tree does not exist in:', blender_object.name)
        node = self.mat.node_tree
        NODE_NAME = 'Principled BSDF'
        if NODE_NAME not in node.nodes:
            Gearoenix.terminate('Material', NODE_NAME,
                                'node does not exist in:', blender_object.name)
        node = node.nodes[NODE_NAME]
        if node is None:
            Gearoenix.terminate('Node is not correct in', blender_object.name)
        self.inputs = node.inputs
        if self.inputs is None:
            Gearoenix.terminate(
                'Node inputs are not correct in', blender_object.name)
        if self.mat.name.startswith(self.PBR_PREFIX):
            self.instance_type = self.TYPE_PBR
            self.init_pbr()
        elif self.mat.name.startswith(self.UNLIT_PREFIX):
            self.instance_type = self.TYPE_UNLIT
            self.init_unlit()
        else:
            Gearoenix.terminate(
                'Unexpected material type in:', self.blender_object.name)

    def write_link(self, l, s=4):
        if isinstance(l, Gearoenix.Texture):
            Gearoenix.write_bool(True)
            Gearoenix.write_id(l.instance_id)
            return
        Gearoenix.write_bool(False)
        if isinstance(l, float):
            Gearoenix.write_float(l)
        elif isinstance(l, bpy.types.bpy_prop_array):
            Gearoenix.write_vector(l, s)
        elif isinstance(l, mathutils.Vector):
            Gearoenix.write_vector(l, s)
        else:
            Gearoenix.terminate(
                'Unexpected type for material input in:', self.blender_object.name)

    def write_pbr(self):
        self.write_unlit()
        self.write_link(self.emission, 3)
        if isinstance(self.metallic, Gearoenix.Texture):
            Gearoenix.write_bool(True)
            Gearoenix.write_id(self.metallic.instance_id)
        else:
            Gearoenix.write_bool(False)
            Gearoenix.write_float(self.metallic)
            Gearoenix.write_float(self.roughness)
        if isinstance(self.normal_map, Gearoenix.Texture):
            Gearoenix.write_bool(True)
            Gearoenix.write_id(self.normal.instance_id)
        else:
            Gearoenix.write_bool(False)

    def write_unlit(self):
        if isinstance(self.alpha, Gearoenix.Texture):
            Gearoenix.write_bool(True)
        else:
            Gearoenix.write_bool(False)
            Gearoenix.write_float(self.alpha)
        self.write_link(self.base_color)
        Gearoenix.write_bool(self.is_tansparent)
        Gearoenix.write_bool(self.is_shadow_caster)
        Gearoenix.write_float(self.alpha_cutoff)

    def write(self):
        Gearoenix.write_type_id(self.instance_type)
        if self.instance_type == self.TYPE_PBR:
            self.write_pbr()
        elif self.instance_type == self.TYPE_UNLIT:
            self.write_unlit()
        else:
            Gearoenix.terminate(
                "Unexpected internal error in material of:", self.blender_object.name)


Gearoenix.Material = Material


class Mesh(Gearoenix.UniqueAsset):
    TYPE_BASIC = 1

    @classmethod
    def init(cls):
        super().init()
        cls.BASIC_PREFIX = cls.get_prefix() + 'basic-'

    def __init__(self, blender_object):
        super().__init__(blender_object)
        self.box = Gearoenix.Aabb()
        if blender_object.name.startswith(self.BASIC_PREFIX):
            self.instance_type = self.TYPE_BASIC
        else:
            Gearoenix.terminate(
                'Unspecified mesh type, in:', blender_object.name)
        if blender_object.type != 'MESH':
            Gearoenix.terminate(
                'Mesh must be of type MESH:', blender_object.name)
        if Gearoenix.has_transformation(blender_object):
            Gearoenix.terminate(
                'Mesh must not have any transformation. in:', blender_object.name)
        if len(blender_object.children) != 0:
            Gearoenix.terminate(
                'Mesh can not have children:', blender_object.name)
        self.mat = Gearoenix.Material(blender_object)
        if self.origin_instance is not None:
            return
        if blender_object.parent is not None:
            Gearoenix.terminate(
                'Origin mesh can not have parent:', blender_object.name)
        msh = blender_object.data
        msh.calc_normals_split()
        msh.calc_tangents()
        vertices = dict()
        last_index = 0
        for p in msh.polygons:
            if len(p.vertices) > 3:
                Gearoenix.terminate('Object', blender_object.name,
                                    'is not triangulated!')
            for i, li in zip(p.vertices, p.loop_indices):
                vertex = []
                v = msh.vertices[i].co
                self.box.put(v)
                vertex.append(v[0])
                vertex.append(v[1])
                vertex.append(v[2])

                normal = msh.loops[li].normal.normalized()
                # Gearoenix.log_info(str(normal))
                vertex.append(normal[0])
                vertex.append(normal[1])
                vertex.append(normal[2])

                tangent = msh.loops[li].tangent.normalized()
                # Gearoenix.log_info(str(tangent))
                vertex.append(tangent[0])
                vertex.append(tangent[1])
                vertex.append(tangent[2])
                vertex.append(msh.loops[li].bitangent_sign)

                uv_leyers = msh.uv_layers
                if len(uv_leyers) > 1 or len(uv_leyers) < 1:
                    Gearoenix.terminate(
                        'Unexpected number of uv layers in', blender_object.name)
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


Gearoenix.Mesh = Mesh


class Model(Gearoenix.Asset):
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
        if self.blender_object.name.startswith(self.BUTTON_PREFIX):
            self.widget_type = self.TYPE_BUTTON
        elif self.blender_object.name.startswith(self.TEXT_PREFIX):
            self.widget_type = self.TYPE_TEXT
        elif self.blender_object.name.startswith(self.EDIT_PREFIX):
            self.widget_type = self.TYPE_EDIT
        else:
            Gearoenix.terminate('Unrecognized widget type:',
                                self.blender_object.name)
        if self.widget_type == self.TYPE_EDIT or \
                self.widget_type == self.TYPE_TEXT:
            self.text = self.blender_object.data.body.strip()
            b_font = self.blender_object.data.font
            if b_font is None:
                Gearoenix.terminate('Font is none in:',
                                    self.blender_object.name)
            self.font = Gearoenix.Font.read(b_font)
            if self.font is None:
                Gearoenix.terminate('Font is incorrect in:',
                                    self.blender_object.name, 'font:', b_font.name)
            align_x = self.blender_object.data.align_x
            align_y = self.blender_object.data.align_y
            self.align = 0
            if align_x == 'LEFT':
                self.align += 3
            elif align_x == 'CENTER':
                self.align += 0
            elif align_x == 'RIGHT':
                self.align += 6
            else:
                Gearoenix.terminate(
                    'Unrecognized text horizontal alignment, in:', self.blender_object.name)
            if align_y == 'TOP':
                self.align += 3
            elif align_y == 'CENTER':
                self.align += 2
            elif align_y == 'BOTTOM':
                self.align += 1
            else:
                Gearoenix.terminate(
                    'Unrecognized text vertical alignment, in:', self.blender_object.name)
            self.font_mat = Gearoenix.Material(self.blender_object)
            self.font_space_character = self.blender_object.data.space_character - 1.0
            self.font_space_word = self.blender_object.data.space_word - 1.0
            self.font_space_line = self.blender_object.data.space_line

    def __init__(self, blender_object):
        super().__init__(blender_object)
        self.matrix = blender_object.matrix_world
        self.meshes = []
        self.model_children = []
        self.collider = Gearoenix.Collider.read(blender_object)
        for c in blender_object.children:
            ins = Gearoenix.Mesh.read(c)
            if ins is not None:
                self.meshes.append(ins)
                continue
            ins = Gearoenix.Model.read(c)
            if ins is not None:
                self.model_children.append(ins)
                continue
        if len(self.model_children) + len(self.meshes) < 1 and not blender_object.name.startswith(self.TEXT_PREFIX):
            Gearoenix.terminate('Waste model', blender_object.name)
        if blender_object.name.startswith(self.DYNAMIC_PREFIX):
            self.instance_type = self.TYPE_DYNAMIC
        elif blender_object.name.startswith(self.STATIC_PREFIX):
            self.instance_type = self.TYPE_STATIC
        elif blender_object.name.startswith(self.WIDGET_PREFIX):
            self.instance_type = self.TYPE_WIDGET
            self.init_widget()
        else:
            Gearoenix.terminate(
                'Unspecified model type, in:', blender_object.name)

    def write_widget(self):
        if self.widget_type == self.TYPE_TEXT or\
                self.widget_type == self.TYPE_EDIT:
            Gearoenix.write_string(self.text)
            Gearoenix.write_u8(self.align)
            Gearoenix.write_id(self.font.instance_id)
            self.font_mat.write()

    def write(self):
        super().write()
        if self.instance_type == self.TYPE_WIDGET:
            Gearoenix.write_u64(self.widget_type)
        Gearoenix.write_matrix(self.blender_object.matrix_world)
        # self.collider.write()
        Gearoenix.write_u64(len(self.meshes))
        for m in self.meshes:
            Gearoenix.write_id(m.instance_id)
            m.mat.write()
        if self.instance_type == self.TYPE_WIDGET:
            self.write_widget()
        Gearoenix.write_instances_ids(self.model_children)


Gearoenix.Model = Model


class Skybox(Gearoenix.Asset):
    TYPE_CUBE = 1
    TYPE_EQUIRECTANGULAR = 2

    @classmethod
    def init(cls):
        super().init()
        cls.CUBE_PREFIX = cls.get_prefix() + 'cube-'
        cls.EQUIRECTANGULAR_PREFIX = cls.get_prefix() + 'equirectangular-'

    def __init__(self, blender_object):
        super().__init__(blender_object)
        if blender_object.name.startswith(self.CUBE_PREFIX):
            self.instance_type = self.TYPE_CUBE
        elif blender_object.name.startswith(self.EQUIRECTANGULAR_PREFIX):
            self.instance_type = self.TYPE_EQUIRECTANGULAR
        else:
            Gearoenix.terminate(
                'Unspecified skybox type, in:', blender_object.name)
        image = blender_object.material_slots[0].material.node_tree.nodes['Principled BSDF']
        image = image.inputs['Base Color'].links[0].from_node.image
        if self.TYPE_EQUIRECTANGULAR == self.instance_type:
            self.image_file = bpy.path.abspath(image.filepath).strip()
        elif self.TYPE_CUBE == self.instance_type:
            self.texture = Gearoenix.Texture.read(image)
            if self.texture is None:
                Gearoenix.terminate(
                    'texture not found for skybox:', blender_object.name)
            if not self.texture.is_cube():
                Gearoenix.terminate(
                    'texture must be cube for skybox:', blender_object.name)

    def write(self):
        super().write()
        if self.TYPE_EQUIRECTANGULAR == self.instance_type:
            (env, irr, rad) = Gearoenix.create_sky_resources(self.image_file)
            Gearoenix.write_file_content(env.filename)
            Gearoenix.write_file_content(irr.filename)
            Gearoenix.write_file_content(rad.filename)
        elif self.TYPE_CUBE == self.instance_type:
            Gearoenix.write_id(self.texture.instance_id)


Gearoenix.Skybox = Skybox


class Reflection(Gearoenix.Asset):
    TYPE_BAKED = 1
    TYPE_RUNTIME = 2

    @classmethod
    def init(cls):
        super().init()
        cls.BAKED_PREFIX = cls.get_prefix() + 'baked-'
        cls.RUNTIME_PREFIX = cls.get_prefix() + 'runtime-'

    def __init__(self, blender_object):
        super().__init__(blender_object)
        if blender_object.name.startswith(self.BAKED_PREFIX):
            self.instance_type = self.TYPE_BAKED
        elif blender_object.name.startswith(self.RUNTIME_PREFIX):
            self.instance_type = self.TYPE_RUNTIME
        else:
            Gearoenix.terminate(
                'Unspecified reflection probe type, in:', blender_object.name)
        Gearoenix.terminate("Unimplemented")

    def write(self):
        super().write()
        if self.TYPE_RUNTIME == self.instance_type:
            pass
        elif self.TYPE_BAKED == self.instance_type:
            pass
        Gearoenix.terminate("Unimplemented")


Gearoenix.Reflection = Reflection


class Scene(Gearoenix.Asset):
    TYPE_GAME = 1
    TYPE_UI = 2

    @classmethod
    def init(cls):
        super().init()
        cls.GAME_PREFIX = cls.get_prefix() + 'game-'
        cls.UI_PREFIX = cls.get_prefix() + 'ui-'

    def __init__(self, blender_object):
        super().__init__(blender_object)
        self.models = []
        self.skyboxes = []
        self.cameras = []
        self.lights = []
        self.audios = []
        self.constraints = []
        self.reflections = []
        for o in blender_object.objects:
            if o.parent is not None:
                continue
            ins = Gearoenix.Model.read(o)
            if ins is not None:
                self.models.append(ins)
                continue
            ins = Gearoenix.Skybox.read(o)
            if ins is not None:
                self.skyboxes.append(ins)
                continue
            ins = Gearoenix.Reflection.read(o)
            if ins is not None:
                self.reflections.append(ins)
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
        if blender_object.name.startswith(self.GAME_PREFIX):
            self.instance_type = self.TYPE_GAME
        elif blender_object.name.startswith(self.UI_PREFIX):
            self.instance_type = self.TYPE_UI
        else:
            Gearoenix.terminate(
                'Unspecified scene type, in:', blender_object.name)
        if len(self.cameras) < 1:
            Gearoenix.terminate(
                'Scene must have at least one camera, in:', blender_object.name)

    def write(self):
        super().write()
        Gearoenix.write_instances_ids(self.cameras)
        Gearoenix.write_instances_ids(self.audios)
        Gearoenix.write_instances_ids(self.lights)
        Gearoenix.write_instances_ids(self.models)
        Gearoenix.write_instances_ids(self.skyboxes)
        Gearoenix.write_instances_ids(self.reflections)
        Gearoenix.write_instances_ids(self.constraints)

    @classmethod
    def read_all(cls):
        for s in bpy.data.scenes:
            super().read(s)


Gearoenix.Scene = Scene


class Exporter(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    """
    This is a plug in for Gearoenix 3D file format
    """
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
            (str(Gearoenix.ENGINE_GEAROENIX), 'Gearoenix', ''),
            (str(Gearoenix.ENGINE_VULKUST), 'Vulkust', ''),
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
        try:
            Gearoenix.EXPORT_FILE_PATH = self.filepath
        except AttributeError:
            Gearoenix.terminate("Exporter.filepath not found")
        Gearoenix.find_tools()
        Gearoenix.export_files()
        return {'FINISHED'}


Gearoenix.Exporter = Exporter

if __name__ == '__main__':
    Gearoenix.register_plugin()
