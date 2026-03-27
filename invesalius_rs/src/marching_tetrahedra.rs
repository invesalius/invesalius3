//! Marching Tetrahedra Isosurface Extractor
//!
//! Splits each voxel into 6 tetrahedra and produces manifold topology with
//! consistent edge-sharing across adjacent cubes. Each shared edge in the
//! grid is interpolated exactly once and reused by all faces that reference it.

use ndarray::ArrayView3;
use rustc_hash::FxHashMap;

// The isosurface threshold. Voxels >= THR are considered "inside".
const THR: u8 = 127;

type GridPoint = (usize, usize, usize);
type EdgeKey   = (GridPoint, GridPoint);

#[derive(Debug, Default)]
pub struct TetraMesh {
    pub vertices: Vec<[f32; 3]>,
    pub faces:    Vec<[i32; 3]>,
}

// ─── Cube topology ────────────────────────────────────────────────────────────

// Corner offsets in (dz, dy, dx) order, indexed 0–7.
const CORNERS: [(usize, usize, usize); 8] = [
    (0, 0, 0), // 0
    (0, 0, 1), // 1
    (0, 1, 0), // 2
    (0, 1, 1), // 3
    (1, 0, 0), // 4
    (1, 0, 1), // 5
    (1, 1, 0), // 6
    (1, 1, 1), // 7
];

// Six tetrahedra that partition the cube, all sharing the 0→7 main diagonal.
// This decomposition guarantees a consistent, crack-free interface between
// neighbouring cubes because adjacent cubes share the same diagonal.
const TETS: [[usize; 4]; 6] = [
    [0, 1, 3, 7],
    [0, 5, 1, 7],
    [0, 4, 5, 7],
    [0, 6, 4, 7],
    [0, 2, 6, 7],
    [0, 3, 2, 7],
];

// The 6 edges of a single tetrahedron, as pairs of local vertex indices.
const TET_EDGES: [(usize, usize); 6] = [
    (0, 1), // edge 0
    (0, 2), // edge 1
    (0, 3), // edge 2
    (1, 2), // edge 3
    (1, 3), // edge 4
    (2, 3), // edge 5
];

// ─── Triangulation table ──────────────────────────────────────────────────────
//
// 16 cases (one per subset of the 4 tetrahedron vertices being "inside").
// Each entry lists edge indices whose intersection points form triangles.
// Winding order is chosen so outward normals face the "outside" region.
// Complementary cases (e.g. 1↔14, 7↔8) have reversed winding to match.
const MT_TABLE: &[&[usize]] = &[
    &[],                 // 0000 — fully outside
    &[0, 1, 2],          // 0001
    &[3, 0, 4],          // 0010
    &[1, 3, 4, 1, 4, 2], // 0011
    &[1, 3, 5],          // 0100
    &[0, 3, 5, 0, 5, 2], // 0101
    &[0, 1, 5, 0, 5, 4], // 0110
    &[5, 2, 4],          // 0111
    &[5, 4, 2],          // 1000
    &[0, 4, 5, 0, 5, 1], // 1001
    &[0, 2, 5, 0, 5, 3], // 1010
    &[1, 5, 3],          // 1011
    &[1, 2, 4, 1, 4, 3], // 1100
    &[3, 4, 0],          // 1101
    &[0, 2, 1],          // 1110
    &[],                 // 1111 — fully inside
];

// ─── Core algorithm ───────────────────────────────────────────────────────────

pub fn marching_tetrahedra_mask(mask: ArrayView3<u8>, spacing: [f64; 3]) -> TetraMesh {
    let nz = mask.shape()[0];
    let ny = mask.shape()[1];
    let nx = mask.shape()[2];

    if nz < 2 || ny < 2 || nx < 2 {
        return TetraMesh::default();
    }

    let voxel_count = (nz - 1) * (ny - 1) * (nx - 1);

    let mut vertices: Vec<[f32; 3]> = Vec::with_capacity(voxel_count / 4);
    let mut faces:    Vec<[i32; 3]> = Vec::with_capacity(voxel_count / 2);

    // FxHashMap uses a fast integer hash (no DoS protection needed here).
    // Seeded with a capacity estimate to avoid mid-run reallocation.
    let mut edge_to_vertex: FxHashMap<EdgeKey, u32> =
        FxHashMap::with_capacity_and_hasher(voxel_count / 3, Default::default());

    for z in 0..nz - 1 {
        for y in 0..ny - 1 {
            for x in 0..nx - 1 {
                process_cube(
                    &mask,
                    z, y, x,
                    spacing,
                    &mut vertices,
                    &mut faces,
                    &mut edge_to_vertex,
                );
            }
        }
    }

    TetraMesh { vertices, faces }
}

// Processes all 6 tetrahedra in one cube cell, emitting vertices and faces.
#[inline]
fn process_cube(
    mask:            &ArrayView3<u8>,
    z: usize, y: usize, x: usize,
    spacing:         [f64; 3],
    vertices:        &mut Vec<[f32; 3]>,
    faces:           &mut Vec<[i32; 3]>,
    edge_to_vertex:  &mut FxHashMap<EdgeKey, u32>,
) {
    for tet in TETS {
        // Collect the 4 grid coordinates and scalar values for this tetrahedron.
        let mut tet_coords = [(0usize, 0usize, 0usize); 4];
        let mut tet_vals   = [0u8; 4];
        let mut case_idx   = 0u8;

        for (i, &corner) in tet.iter().enumerate() {
            let (dz, dy, dx) = CORNERS[corner];
            let (gz, gy, gx) = (z + dz, y + dy, x + dx);
            let val = mask[[gz, gy, gx]];

            tet_coords[i] = (gz, gy, gx);
            tet_vals[i]   = val;

            if val >= THR {
                case_idx |= 1 << i;
            }
        }

        // Skip if fully inside or fully outside — no surface to emit.
        if case_idx == 0 || case_idx == 15 {
            continue;
        }

        for tri in MT_TABLE[case_idx as usize].chunks_exact(3) {
            let mut face_vids = [0i32; 3];

            for (slot, &edge_idx) in tri.iter().enumerate() {
                let v1 = TET_EDGES[edge_idx].0;
                let v2 = TET_EDGES[edge_idx].1;

                let vid = get_or_create_vertex(
                    tet_coords, tet_vals,
                    v1, v2,
                    spacing,
                    vertices,
                    edge_to_vertex,
                );

                face_vids[slot] = vid as i32;
            }

            // Skip degenerate triangles (two or more identical vertex indices).
            if face_vids[0] != face_vids[1]
                && face_vids[1] != face_vids[2]
                && face_vids[0] != face_vids[2]
            {
                faces.push(face_vids);
            }
        }
    }
}

// Returns the vertex index for the isosurface point on the edge between
// tet vertices `v1` and `v2`, creating it if it hasn't been seen before.
//
// Endpoints are sorted before hashing so the same edge encountered from
// either direction maps to the same key — this is what makes the mesh manifold.
#[inline]
fn get_or_create_vertex(
    tet_coords:     [(usize, usize, usize); 4],
    tet_vals:       [u8; 4],
    v1: usize, v2: usize,
    spacing:        [f64; 3],
    vertices:       &mut Vec<[f32; 3]>,
    edge_to_vertex: &mut FxHashMap<EdgeKey, u32>,
) -> u32 {
    let mut p1 = tet_coords[v1];
    let mut p2 = tet_coords[v2];

    // Canonical ordering: smaller grid point always comes first.
    // This ensures two tets traversing the same edge in opposite directions
    // produce the same key and therefore reuse the same vertex.
    if p1 > p2 {
        std::mem::swap(&mut p1, &mut p2);
    }

    *edge_to_vertex.entry((p1, p2)).or_insert_with(|| {
        // Linear interpolation parameter: where along the edge does the
        // isosurface (value == THR) fall?
        let a = tet_vals[v1] as f64;
        let b = tet_vals[v2] as f64;
        let t = if a != b { (THR as f64 - a) / (b - a) } else { 0.5 };

        // tet_coords layout: (z_idx, y_idx, x_idx)
        //   .0 → z,  .1 → y,  .2 → x
        // spacing layout: [x_spacing, y_spacing, z_spacing]
        let interp = |a: usize, b: usize| a as f64 + t * (b as f64 - a as f64);

        let vx = interp(tet_coords[v1].2, tet_coords[v2].2) * spacing[0];
        let vy = interp(tet_coords[v1].1, tet_coords[v2].1) * spacing[1];
        let vz = interp(tet_coords[v1].0, tet_coords[v2].0) * spacing[2];

        let new_vid = vertices.len() as u32;
        debug_assert!(
            new_vid <= i32::MAX as u32,
            "vertex count exceeds i32::MAX — mesh is too large"
        );

        vertices.push([vx as f32, vy as f32, vz as f32]);
        new_vid
    })
}