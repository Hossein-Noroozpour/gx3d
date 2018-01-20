# Gearoenix Blender plugin

Blender plug-in for Gearoenix 3D file format.

## Rules:

- Scene:

  - Its name starts with `scene-`.
  - It have following fields:

    - Models
    - Cameras
    - Lights
    - Audios
    - Constraints

  - It has following types:

    - Game:

      - Its name starts with `scene-game-`.

    - UI:

      - Its name starts with `scene-gui-`.
      - It have following fields more than ordinary scene:

        - Widgets

- Mesh:

  - It is an object.
  - Its name starts with `mesh-` and it should not have tailing number at its name.
  - Its mesh name must be same.
  - Its name can not contain `.`.
  - It should not have any transformation.
  - it must be located in zero.
  - It should not have not applied modifier.
  - All of its face must be triangle.
  - It should not have neither parent nor child.
  - It has following types:

    - Basic:

      - It name starts with `mesh-basic-`.

- Model

  - It is an object.
  - Its name must start with `model-`.
  - Its blender mesh data will be ignored.
  - It must have at least 1 mesh or 1 model as its child.
  - It must have an occlusion bounding sphere in its child with name `occlusion`.
  - Its mesh child specifies with `mesh-[name].xxx` pattern.
  - Its mesh child can not have different material that require different vertex attributes with its origin mesh.
  - It can not have a several children from one mesh, It can only have one mesh from one origin.
  - Each model can have one collider at max.
  - If it is a solid model with no physical attributes, it does not need to have collider as its child.
  - If a model has a collider it must have a symmetric scale.

- Material

  - Only one material must be in material slots.

- Texture

  - If material has a 2D texture, it must have one texture in its texture slots with name pattern `[texture-name]-2d`.
  - For 3D texture, `[texture-name]-3d`.
  - For cube, it must have 6 textures in its texture slots with name pattern `[texture-name]-cube-(up/down/front/back/right/left)`.
  - For speculating texture, `[texture-name]-spectxt`.
  - For normal-map texture, `[texture-name]-normal`.
  - If a material has a baked environment-mapping cube texture, it must have 6 textures in its texture slots with name pattern `[texture-name]-baked-(up/down/front/back/right/left)`.
  - Note: 3D texture is not supported right now.

- Collider

  - Its name start with `collider-[collider-type]-[name]`.
  - Currently only one collider can exist in one object.
  - There are these types of collider:

    - Ghost

      - It should not have any collider object.

    - Sphere

      - Collider name becomes like this `collider-sphere-[name]`.
      - It is an empty object of type sphere.
      - It must not have local transformation except translation.

    - Cylinder

      - Collider name becomes like this `collider-cylinder-[name]`.
      - It is an empty object of type sphere.
      - It must not have local transformation except translation.
      - It must have a child with name `collider-cylinder-child-[name]`.
      - Child is an empty object of type plain axes.

    - Capsule

      - Collider name becomes like this `collider-capsule-[name]`.
      - It is an empty object of type sphere.
      - It must not have local transformation except translation.
      - It must have a child with name `collider-cylinder-child-[name]`.
      - Child is an empty object of type plain axes.

    - Mesh

      - Collider name becomes like this `collider-mesh-[name]`.
      - It is an object.
      - Triangulated.
      - Not local transformation.
      - Mostly like a mesh.
      - Its normal must be flat, not smooth.

- Constraints:

  - Placer:

    - Its name is `placer-[name]`.
    - It is an empty object.
    - It should not have any transformation.
    - It can have only model in its children.
    - In every size event it will compute the space and the position of the object and if the remained space was smaller than the current size of the object, object will be fitted by scaling down and on the other hand if object was smaller than the allowed space that it can fill, it will be fill the space by scaling up.
    - It has following attributes (misusing may cause undefined behavior):

      - x-middle: Place the object in x: 0.0 and with the specified distance from right and left borders.
      - y-middle: (todo: will be added, whenever needed)
      - x-left: (todo: will be added, whenever needed)
      - x-right: (todo: will be added, whenever needed)
      - y-down: place the object with a specified distance from bottom border.
      - y-up: (todo: will be added, whenever needed)
      - ratio: Its value is (width / height), it is a mandatory attribute.

## License

- Do not use it!
- Do not even look at/in it!
