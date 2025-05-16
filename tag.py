import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)

# Ensure there is a scene and a view layer
if not bpy.data.scenes:
    bpy.data.scenes.new("Scene")
if not bpy.context.view_layer:
    bpy.context.window.view_layer = bpy.context.scene.view_layers[0]

# Check if the STL import operator is available
if hasattr(bpy.ops.import_mesh, "stl"):
    bpy.ops.import_mesh.stl(filepath=r"C:\Users\chris\Downloads\isolated.stl")
else:
    print("STL import operator not found. Make sure the STL add-on is enabled.")

bpy.ops.object.text_add(location=(10, 5, 3))
text_obj = bpy.context.object
text_obj.data.body = "Tag123"

bpy.ops.object.convert(target='MESH')

bpy.ops.export_mesh.stl(filepath=r"C:\Users\chris\Downloads\new_isolated.stl")
