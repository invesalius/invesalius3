import trimesh
import argparse
import sys

def merge_and_color_stl(stl_paths, output_path):
    rgb_colors = [
        [255, 0, 0],   # Red
        [0, 255, 0],   # Green
        [0, 0, 255]    # Blue
    ]
    meshes = []
    for path, rgb in zip(stl_paths, rgb_colors):
        mesh = trimesh.load_mesh(path)
        color = rgb + [255]  # RGBA
        mesh.visual.vertex_colors = [color] * len(mesh.vertices)
        meshes.append(mesh)
    merged = trimesh.util.concatenate(meshes)
    merged.export(output_path, file_type='ply')
    print(f"Merged mesh saved to {output_path} (PLY format with vertex colors)")

def parse_args():
    parser = argparse.ArgumentParser(description="Merge exactly three STL files as red, green, blue, export as PLY (with vertex colors).")
    parser.add_argument('stl_files', nargs=3, help='Input STL file paths (order: red green blue)')
    parser.add_argument('--output', required=True, help='Output PLY file path')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    merge_and_color_stl(args.stl_files, args.output)

