# Gearoenix Blender plugin

Blender plug-in for Gearoenix 3D file format.

## License

- Do not use it! :D
- Do not even look at/in it! :|-
- Unless your a recruiter or you want to assess me for a job.

## Rules:

- Scene:

  - Its name starts with `scene-`.
  - It has following fields:

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
      - Its difference with game scene is game scene does not propagate any user event on its models, but ui scene do that.

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

- Model:

  - It is an object.
  - Its name must start with `model-`.
  - Its blender mesh data will be ignored.
  - It must have at least 1 mesh or 1 model as its child.
  - It must have an occlusion bounding sphere in its child with name `occlusion`.
  - Its mesh child specifies with `mesh-[type]-[name].xxx` pattern.
  - Its mesh child can not have different material that require different vertex attributes with its origin mesh.
  - It can not have a several children from one mesh, It can only have one mesh from one origin.
  - Each model can have one collider at max.
  - If it is a solid model with no physical attributes, it does not need to have collider as its child.
  - If a model has a collider it must have a symmetric scale.
  - It has following type:

    - Basic:

      - It name starts with `model-basic-`.

    - Widget:

      - It name starts with `model-widget-`.
      - Its difference with basic model is, it can receive events and do some action.

- Material

  - Only one material must be in material slots.

- Texture

  - Its name starts with `txt-` in texture slots.
  - Texture must have a image with format of `PNG`.
  - It has following types:

    - 2D:

      - Its name starts with `txt-2d-`.

    - 3D:

      - Its name starts with `txt-3d-`.

    - Cube:

      - Its name starts with `txt-cube-`.
      - Its image file name must end with `-up.png`.
      - All of its faces image files must be in the same location.
      - So, its faces image files names are like `[texture-name]-(up/down/front/back/right/left).png`.

    - Specular:

      - Is name starts with `txt-spec-`.

    - Normal map:

      - Is name starts with `txt-nrm-`.

    - Backed Environment:

      - Is name starts with `txt-bkenv-`.
      - It is like cube.

  - Note: 3D, Specular and Normal map texture is not supported right now.

- Collider

  - Its name start with `collider-`.
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
