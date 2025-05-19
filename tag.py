import trimesh
from solid import text, linear_extrude, scad_render_to_file
from solid.utils import translate
import os
import subprocess

# === Parameters ===
text_string = "Part123"
text_size = 5  # mm
text_depth = 1  # mm
text_position = [20, 10, 3]  # mm, relative position

base_model_path = "model.stl"
text_mesh_path = "text_tmp.stl"
output_path = "model_with_tag.stl"

# === 1. Create 3D Text Using OpenSCAD-compatible SolidPython ===
scad_code = translate(text_position)(
    linear_extrude(height=text_depth)(
        text(text_string, size=text_size)
    )
)

scad_render_to_file(scad_code, 'text.scad')

# === 2. Generate STL from SCAD ===
# You need OpenSCAD installed (CLI only, no GUI)
subprocess.run(["openscad", "-o", text_mesh_path, "text.scad"], check=True)

# === 3. Load Both Meshes ===
base = trimesh.load_mesh(base_model_path)
text_mesh = trimesh.load_mesh(text_mesh_path)

# === 4. Combine Meshes ===
combined = base + text_mesh

# === 5. Export Final STL ===
combined.export(output_path)

print(f"Saved tagged STL to {output_path}")
