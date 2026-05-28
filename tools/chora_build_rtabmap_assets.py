#!/usr/bin/env python3
"""
Build long-lived Chora assets from an exported RTAB-Map point cloud.

This is an offline tool. It turns a fused RTAB-Map PLY export into lighter
artifacts that Logos can load as phantasmata without doing heavy Open3D work
during cognition.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import open3d as o3d
except ImportError as exc:
    raise SystemExit("Open3D is required: {}".format(exc))


DEFAULT_SOURCE = "/home/robot/maps/cloud.ply"
DEFAULT_OUT = "/home/robot/maps/chora_assets/rtabmap_world"
DEFAULT_CLOUD_VOXELS = "0.05,0.08,0.10,0.15"


def _parse_voxel_csv(text: str) -> List[float]:
    values = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        value = float(part)
        if value <= 0:
            raise argparse.ArgumentTypeError("voxel sizes must be positive")
        values.append(value)
    if not values:
        raise argparse.ArgumentTypeError("at least one voxel size is required")
    return values


def _format_voxel(value: float) -> str:
    value = float(value)
    if abs(value - round(value, 2)) < 1e-9:
        return "{:.2f}".format(value)
    return "{:.3f}".format(value).rstrip("0").rstrip(".")


def _bounds_dict(geometry: Any) -> Dict[str, List[float]]:
    min_bound = np.asarray(geometry.get_min_bound(), dtype=np.float64)
    max_bound = np.asarray(geometry.get_max_bound(), dtype=np.float64)
    return {
        "min": [float(x) for x in min_bound.tolist()],
        "max": [float(x) for x in max_bound.tolist()],
        "extent": [float(x) for x in (max_bound - min_bound).tolist()],
    }


def _normals_valid(pcd: Any) -> bool:
    if not pcd.has_normals():
        return False
    points = np.asarray(pcd.points)
    normals = np.asarray(pcd.normals)
    if len(points) == 0 or len(normals) != len(points):
        return False
    if not np.all(np.isfinite(normals)):
        return False
    lengths = np.linalg.norm(normals, axis=1)
    return bool(np.any(lengths > 1e-6))


def _ensure_normals(pcd: Any, radius: float, max_nn: int) -> str:
    if _normals_valid(pcd):
        pcd.normalize_normals()
        return "source"

    print("[chora-assets] estimating normals")
    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(
            radius=float(radius),
            max_nn=int(max_nn),
        )
    )
    pcd.normalize_normals()
    return "estimated"


def _write_point_cloud(path: str, pcd: Any) -> None:
    ok = o3d.io.write_point_cloud(path, pcd, write_ascii=False, compressed=False)
    if not ok:
        raise RuntimeError("failed to write point cloud: {}".format(path))


def _write_mesh(path: str, mesh: Any) -> None:
    ok = o3d.io.write_triangle_mesh(path, mesh, write_ascii=False, compressed=False)
    if not ok:
        raise RuntimeError("failed to write mesh: {}".format(path))


def _clean_mesh(mesh: Any) -> Any:
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_non_manifold_edges()
    mesh.compute_vertex_normals()
    return mesh


def _remove_low_density_vertices(mesh: Any, densities: Any, quantile: float) -> int:
    values = np.asarray(densities, dtype=np.float64)
    if values.size == 0:
        return 0
    threshold = float(np.quantile(values, float(quantile)))
    mask = values < threshold
    removed = int(np.count_nonzero(mask))
    if removed > 0:
        mesh.remove_vertices_by_mask(mask)
    return removed


def _build_mesh(
    pcd: Any,
    source_bounds: Dict[str, List[float]],
    out_path: str,
    source_voxel_m: float,
    depth: int,
    density_quantile: float,
    target_triangles: int,
) -> Dict[str, Any]:
    normal_source = _ensure_normals(pcd, radius=0.20, max_nn=30)

    print("[chora-assets] running Poisson reconstruction depth={}".format(depth))
    start = time.time()
    with o3d.utility.VerbosityContextManager(o3d.utility.VerbosityLevel.Info):
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd,
            depth=int(depth),
        )
    poisson_seconds = time.time() - start

    removed = _remove_low_density_vertices(
        mesh,
        densities,
        quantile=float(density_quantile),
    )

    min_bound = np.asarray(source_bounds["min"], dtype=np.float64)
    max_bound = np.asarray(source_bounds["max"], dtype=np.float64)
    padding = 0.02
    aabb = o3d.geometry.AxisAlignedBoundingBox(
        min_bound=min_bound - padding,
        max_bound=max_bound + padding,
    )
    mesh = mesh.crop(aabb)
    mesh = _clean_mesh(mesh)

    before_decimation = len(mesh.triangles)
    if target_triangles > 0 and before_decimation > target_triangles:
        print(
            "[chora-assets] decimating mesh {} -> {} triangles".format(
                before_decimation,
                target_triangles,
            )
        )
        mesh = mesh.simplify_quadric_decimation(
            target_number_of_triangles=int(target_triangles)
        )
        mesh = _clean_mesh(mesh)

    _write_mesh(out_path, mesh)

    return {
        "path": out_path,
        "kind": "mesh",
        "method": "poisson",
        "source_voxel_m": float(source_voxel_m),
        "poisson_depth": int(depth),
        "normal_source": normal_source,
        "density_quantile_removed": float(density_quantile),
        "density_vertices_removed": removed,
        "target_triangles": int(target_triangles),
        "triangles_before_decimation": int(before_decimation),
        "triangles": int(len(mesh.triangles)),
        "vertices": int(len(mesh.vertices)),
        "bounds": _bounds_dict(mesh),
        "seconds": float(poisson_seconds),
        "note": (
            "Experimental visual layer. Poisson reconstruction can create "
            "unsupported surfaces in sparse regions; do not treat this as "
            "navigation truth."
        ),
    }


def _build_assets(args: argparse.Namespace) -> Dict[str, Any]:
    source = os.path.abspath(os.path.expanduser(args.source))
    out_dir = os.path.abspath(os.path.expanduser(args.out))

    if args.mode == "tsdf":
        raise SystemExit(
            "TSDF mode is intentionally not implemented from a fused PLY. "
            "Future TSDF input must include synchronized RGB-D frames, camera "
            "intrinsics, and per-frame camera extrinsics/poses from RTAB-Map."
        )

    os.makedirs(out_dir, exist_ok=True)

    print("[chora-assets] reading {}".format(source))
    start = time.time()
    source_pcd = o3d.io.read_point_cloud(source)
    read_seconds = time.time() - start
    if source_pcd.is_empty():
        raise RuntimeError("source point cloud is empty: {}".format(source))

    source_stat = os.stat(source)
    source_bounds = _bounds_dict(source_pcd)
    source_points = int(len(source_pcd.points))
    print("[chora-assets] source points: {:,}".format(source_points))

    cloud_assets = []
    downsampled_by_voxel = {}
    for voxel in args.cloud_voxels:
        label = _format_voxel(voxel)
        filename = "cloud_voxel_{}.ply".format(label)
        path = os.path.join(out_dir, filename)

        print("[chora-assets] voxel downsample {} m".format(label))
        start = time.time()
        downsampled = source_pcd.voxel_down_sample(float(voxel))
        seconds = time.time() - start
        _write_point_cloud(path, downsampled)

        asset = {
            "path": path,
            "kind": "pointcloud",
            "voxel_m": float(voxel),
            "points": int(len(downsampled.points)),
            "has_colors": bool(downsampled.has_colors()),
            "has_normals": bool(downsampled.has_normals()),
            "bounds": _bounds_dict(downsampled),
            "seconds": float(seconds),
        }
        cloud_assets.append(asset)
        downsampled_by_voxel[round(float(voxel), 6)] = downsampled
        print(
            "[chora-assets] wrote {} ({:,} points)".format(
                path,
                asset["points"],
            )
        )

    mesh_asset = None
    if args.mesh:
        mesh_voxel_key = round(float(args.mesh_source_voxel), 6)
        mesh_source = downsampled_by_voxel.get(mesh_voxel_key)
        if mesh_source is None:
            print(
                "[chora-assets] building mesh source voxel {} m".format(
                    args.mesh_source_voxel
                )
            )
            mesh_source = source_pcd.voxel_down_sample(float(args.mesh_source_voxel))

        mesh_path = os.path.join(
            out_dir,
            "mesh_poisson_depth{}_voxel{}_decimated.ply".format(
                int(args.poisson_depth),
                _format_voxel(float(args.mesh_source_voxel)),
            ),
        )
        mesh_asset = _build_mesh(
            pcd=mesh_source,
            source_bounds=source_bounds,
            out_path=mesh_path,
            source_voxel_m=float(args.mesh_source_voxel),
            depth=int(args.poisson_depth),
            density_quantile=float(args.density_quantile),
            target_triangles=int(args.target_triangles),
        )
        print("[chora-assets] wrote {}".format(mesh_path))

    manifest = {
        "schema_version": 1,
        "created_at_unix": float(time.time()),
        "open3d_version": getattr(o3d, "__version__", "unknown"),
        "source": {
            "path": source,
            "mtime": float(source_stat.st_mtime),
            "size_bytes": int(source_stat.st_size),
            "points": source_points,
            "has_colors": bool(source_pcd.has_colors()),
            "has_normals": bool(source_pcd.has_normals()),
            "bounds": source_bounds,
            "read_seconds": float(read_seconds),
        },
        "cloud_assets": cloud_assets,
        "mesh_asset": mesh_asset,
        "tsdf_future": {
            "implemented": False,
            "reason": "A fused PLY lacks RGB-D frames, intrinsics, and camera poses.",
            "required_inputs": [
                "synchronized RGB images",
                "synchronized depth images",
                "camera intrinsics",
                "per-frame camera extrinsics or poses from RTAB-Map",
            ],
            "intended_output": "triangle mesh loadable by rtabmap_world phantasma",
        },
    }

    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("[chora-assets] wrote {}".format(manifest_path))
    return manifest


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Chora RTAB-Map world assets from an exported PLY."
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument(
        "--cloud-voxels",
        type=_parse_voxel_csv,
        default=_parse_voxel_csv(DEFAULT_CLOUD_VOXELS),
        help="Comma-separated voxel sizes in meters.",
    )
    parser.add_argument(
        "--mode",
        choices=["pointcloud", "tsdf"],
        default="pointcloud",
        help="TSDF is documented as a future backend and currently exits.",
    )
    parser.add_argument("--mesh", action="store_true")
    parser.add_argument("--mesh-source-voxel", type=float, default=0.08)
    parser.add_argument("--poisson-depth", type=int, default=8)
    parser.add_argument("--density-quantile", type=float, default=0.02)
    parser.add_argument("--target-triangles", type=int, default=200000)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    _build_assets(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
