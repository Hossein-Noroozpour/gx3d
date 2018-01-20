import enum

import bpy
import bpy_extras
import mathutils


class ColoringType(enum.Enum):
    COLORED = 0
    TEXTURED = 1


class DiffuseType(enum.Enum):
    SHADELESS = 0
    DIFFUSE = 1


class SpecularType(enum.Enum):
    SHADELESS = 0
    DIFFUSE = 1


class TrancparencyType(enum.Enum):
    OPAQUE = 0
    TRANSPARENT = 1
    CUTOFF = 2


class MirrorType(enum.Enum)
    MATTE = 0
    REALTIME = 1
    BAKED = 2


for m in bpy.data.materials:
