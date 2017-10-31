# Blender Gearoenix 3D file exporter

Blender plug-in for Gearoenix 3D file format.

## Rules for objects:

#### Material

- Only one material must be in material slots
-

#### Texture

- If material has a 2D texture, it must have one texture in its texture slots
with name pattern [texture-name]-2d.
- For 3D texture, [texture-name]-3d.
- For cube, it must have 6 textures in its texture slots
with name pattern [texture-name]-cube-(up/down/front/back/right/left).
- For speculating texture, [texture-name]-spectxt.
- If a material has a backed environment-mapping cube texture, it must have 6
textures in its texture slots with name pattern
[texture-name]-backed-(up/down/front/back/right/left).

(Note: 3D texture is not supported now.)

## License

- Do not use it!
- Do not even look at/in it!
