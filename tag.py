import trimesh
from solid import text, linear_extrude, scad_render_to_file, color as scad_color
from solid.utils import translate
import os
import subprocess
import argparse
import tempfile
import ast
import sys

def parse_tags(inline_tags):
    """
    Parse inline tags argument.
    Example: "Text1,[10,10,2];Text2,[20,15,2]"
    Returns: list of dicts
    """
    tags = []
    for tag_str in inline_tags.split(";"):
        if not tag_str.strip():
            continue
        parts = tag_str.split(",", 1)
        if len(parts) < 2:
            print(f"Invalid tag format: {tag_str}")
            sys.exit(1)
        tag_text = parts[0]
        tag_position = ast.literal_eval(parts[1])
        tag_size = 5.0      # Default size
        tag_depth = 1.0     # Default depth
        tag_color = [1, 0, 0]  # Default color: red
        tags.append({
            "text": tag_text,
            "size": tag_size,
            "depth": tag_depth,
            "position": tag_position,
            "color": tag_color
        })
    return tags

def main():
    parser = argparse.ArgumentParser(
        description="Add multiple 3D text tags to a model (inline tags, default red color, outputs OBJ)."
    )
    parser.add_argument(
        "base_model_path",
        help="Path to the base STL/OBJ/PLY model."
    )
    parser.add_argument(
        "output_path",
        help="Path to save the output OBJ model."
    )
    parser.add_argument(
        "--tags",
        required=True,
        help='Inline tags, e.g. "Text1,5,1,[10,10,2];Text2,4,1,[20,15,2]" (all tags default to red)'
    )
    args = parser.parse_args()

    tags = parse_tags(args.tags)

    temp_dir = tempfile.mkdtemp()
    text_meshes = []
    colors = []
    for i, tag in enumerate(tags):
        scad_obj = linear_extrude(height=tag["depth"])(
            text(tag["text"], size=tag["size"])
        )
        if tag["color"]:
            scad_obj = scad_color(tag["color"])(scad_obj)
        scad_code = translate(tag["position"])(scad_obj)
        scad_path = os.path.join(temp_dir, f"text_{i}.scad")
        stl_path = os.path.join(temp_dir, f"text_{i}.stl")
        scad_render_to_file(scad_code, scad_path)
        subprocess.run(["openscad", "-o", stl_path, scad_path], check=True)
        text_mesh = trimesh.load_mesh(stl_path)
        text_meshes.append(text_mesh)
        colors.append(tag["color"])  # always red

    base = trimesh.load_mesh(args.base_model_path)
    # If base mesh has no color, assign default
    if not hasattr(base.visual, "vertex_colors") or base.visual.vertex_colors is None:
        base.visual.vertex_colors = [200, 200, 200, 255]  # light gray

    # Assign colors to tag meshes
    for mesh, color in zip(text_meshes, colors):
        rgb = [int(255 * c) for c in color]
        if mesh.visual.kind == 'face':
            mesh.visual.face_colors = [rgb + [255]] * len(mesh.faces)
        else:
            mesh.visual.vertex_colors = [rgb + [255]] * len(mesh.vertices)

    # Combine all meshes
    combined = trimesh.util.concatenate([base] + text_meshes)

    # Export as OBJ (with colors)
    combined.export(args.output_path)
    print(f"Saved tagged OBJ to {args.output_path}")

if __name__ == "__main__":
    main()