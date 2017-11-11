# Blender Gearoenix 3D file exporter
Blender plug-in for Gearoenix 3D file format.

## Rules for objects:
- ### Mesh
 - It is an object.
 - Its name starts with `mesh-` and it should not have tailing number at its
   name.
 - Its mesh name must be same.
 - It should not have any transformation.
 - it must be located in zero.
 - It should not have any not applied modifier.
 - All of its face must be triangle.
 - It should not have any parent or child.
- ### Model
 - It must have at least 1 mesh or 1 model as its child.
 - It name should not start with `mesh-`.
 - Its mesh child specify with `mesh-[name].xxx` pattern.
- ### Material
 - Only one material must be in material slots.
- ### Texture
 - If material has a 2D texture, it must have one texture in its texture slots
   with name pattern `[texture-name]-2d`.
 - For 3D texture, `[texture-name]-3d`.
 - For cube, it must have 6 textures in its texture slots
   with name pattern `[texture-name]-cube-(up/down/front/back/right/left)`.
 - For speculating texture, `[texture-name]-spectxt`.
 - For normal-map texture, `[texture-name]-normal`.
 - If a material has a baked environment-mapping cube texture, it must have 6
   textures in its texture slots with name pattern
   `[texture-name]-baked-(up/down/front/back/right/left)`.
 - Note: 3D texture is not supported right now.

## License
- Do not use it!
- Do not even look at/in it!
