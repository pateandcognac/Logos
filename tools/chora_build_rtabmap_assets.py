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
import re
import shutil
import subprocess
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
DEFAULT_TSDF_DB = "/home/robot/.ros/logos_rtabmap.db"
DEFAULT_TSDF_OUT = "/home/robot/maps/chora_assets/rtabmap_tsdf"
DEFAULT_CLOUD_VOXELS = "0.05,0.08,0.10,0.15"
RTABMAP_LIBRARY_PATH = "/opt/ros/noetic/lib/x86_64-linux-gnu:/opt/ros/noetic/lib"


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


def _update_current_asset_link(asset_path: str, link_name: str) -> str:
    """Point a stable asset name at the newest generated quality profile."""
    link_path = os.path.join(os.path.dirname(asset_path), link_name)
    temp_path = "{}.tmp".format(link_path)
    if os.path.lexists(temp_path):
        os.unlink(temp_path)
    os.symlink(os.path.basename(asset_path), temp_path)
    os.replace(temp_path, link_path)
    return link_path


def _clean_mesh(mesh: Any) -> Any:
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_non_manifold_edges()
    mesh.compute_vertex_normals()
    return mesh


def _clamp_geometry_colors(geometry: Any) -> None:
    if hasattr(geometry, "has_colors") and geometry.has_colors():
        colors = np.asarray(geometry.colors)
        if colors.size > 0:
            geometry.colors = o3d.utility.Vector3dVector(np.clip(colors, 0.0, 1.0))
    if hasattr(geometry, "has_vertex_colors") and geometry.has_vertex_colors():
        colors = np.asarray(geometry.vertex_colors)
        if colors.size > 0:
            geometry.vertex_colors = o3d.utility.Vector3dVector(np.clip(colors, 0.0, 1.0))


def _clean_point_cloud(pcd: Any, voxel_size: float) -> Any:
    if voxel_size > 0:
        pcd = pcd.voxel_down_sample(float(voxel_size))
    _clamp_geometry_colors(pcd)
    return pcd


def _run_rtabmap_export(cmd_args: List[str]) -> None:
    env = os.environ.copy()
    current = env.get("LD_LIBRARY_PATH", "")
    parts = [RTABMAP_LIBRARY_PATH]
    if current:
        parts.append(current)
    env["LD_LIBRARY_PATH"] = ":".join(parts)

    cmd = ["rtabmap-export"] + cmd_args
    print("[chora-assets] {}".format(" ".join(cmd)))
    subprocess.check_call(cmd, env=env)


def _export_rtabmap_rgbd(db_path: str, export_dir: str, reuse_export: bool) -> Dict[str, str]:
    os.makedirs(export_dir, exist_ok=True)
    frame_prefix = "frames"
    pose_prefix = "poses"

    rgb_dir = os.path.join(export_dir, "{}_rgb".format(frame_prefix))
    depth_dir = os.path.join(export_dir, "{}_depth".format(frame_prefix))
    calib_dir = os.path.join(export_dir, "{}_calib".format(frame_prefix))
    poses_path = os.path.join(export_dir, "{}_camera_poses.txt".format(pose_prefix))

    if not reuse_export or not (
        os.path.isdir(rgb_dir)
        and os.path.isdir(depth_dir)
        and os.path.isdir(calib_dir)
        and os.path.exists(poses_path)
    ):
        _run_rtabmap_export([
            "--images_id",
            "--output_dir",
            export_dir,
            "--output",
            frame_prefix,
            db_path,
        ])
        _run_rtabmap_export([
            "--poses_camera",
            "--poses_format",
            "11",
            "--output_dir",
            export_dir,
            "--output",
            pose_prefix,
            db_path,
        ])
    else:
        print("[chora-assets] reusing exported RGB-D frames in {}".format(export_dir))

    return {
        "rgb_dir": rgb_dir,
        "depth_dir": depth_dir,
        "calib_dir": calib_dir,
        "poses_path": poses_path,
    }


def _quat_xyzw_to_rotation(qx: float, qy: float, qz: float, qw: float) -> np.ndarray:
    q = np.array([qx, qy, qz, qw], dtype=np.float64)
    norm = np.linalg.norm(q)
    if norm < 1e-12:
        return np.eye(3, dtype=np.float64)
    q = q / norm
    x, y, z, w = q

    return np.array([
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
    ], dtype=np.float64)


def _pose_matrix_from_row(row: Dict[str, Any]) -> np.ndarray:
    mat = np.eye(4, dtype=np.float64)
    mat[:3, :3] = _quat_xyzw_to_rotation(
        float(row["qx"]),
        float(row["qy"]),
        float(row["qz"]),
        float(row["qw"]),
    )
    mat[:3, 3] = [
        float(row["x"]),
        float(row["y"]),
        float(row["z"]),
    ]
    return mat


def _read_pose_rows(path: str) -> List[Dict[str, Any]]:
    rows = []
    with open(path, "r") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 9:
                continue
            rows.append({
                "stamp": float(parts[0]),
                "x": float(parts[1]),
                "y": float(parts[2]),
                "z": float(parts[3]),
                "qx": float(parts[4]),
                "qy": float(parts[5]),
                "qz": float(parts[6]),
                "qw": float(parts[7]),
                "id": int(parts[8]),
            })
    return rows


def _yaml_scalar_int(text: str, key: str) -> int:
    match = re.search(r"{}\s*:\s*([0-9]+)".format(re.escape(key)), text)
    if not match:
        raise RuntimeError("missing '{}' in calibration YAML".format(key))
    return int(match.group(1))


def _yaml_matrix_data(text: str, key: str) -> List[float]:
    match = re.search(
        r"{}\s*:\s*.*?data\s*:\s*\[(.*?)\]".format(re.escape(key)),
        text,
        flags=re.S,
    )
    if not match:
        raise RuntimeError("missing '{}' data in calibration YAML".format(key))
    raw_values = match.group(1).replace("\n", " ").split(",")
    values = []
    for raw in raw_values:
        raw = raw.strip()
        if raw:
            values.append(float(raw))
    return values


def _read_open3d_intrinsic(calib_path: str) -> Tuple[Any, Dict[str, Any]]:
    with open(calib_path, "r") as handle:
        text = handle.read()

    width = _yaml_scalar_int(text, "image_width")
    height = _yaml_scalar_int(text, "image_height")

    matrix_name = "projection_matrix"
    values = _yaml_matrix_data(text, matrix_name)
    if len(values) < 12:
        matrix_name = "camera_matrix"
        values = _yaml_matrix_data(text, matrix_name)

    if matrix_name == "projection_matrix":
        fx, fy, cx, cy = values[0], values[5], values[2], values[6]
    else:
        fx, fy, cx, cy = values[0], values[4], values[2], values[5]

    intrinsic = o3d.camera.PinholeCameraIntrinsic(
        int(width),
        int(height),
        float(fx),
        float(fy),
        float(cx),
        float(cy),
    )
    meta = {
        "calibration_path": calib_path,
        "matrix_used": matrix_name,
        "width": int(width),
        "height": int(height),
        "fx": float(fx),
        "fy": float(fy),
        "cx": float(cx),
        "cy": float(cy),
    }
    return intrinsic, meta


def _select_pose_rows(
    pose_rows: List[Dict[str, Any]],
    frame_step: int,
    max_frames: int,
) -> List[Dict[str, Any]]:
    stepped = pose_rows[::max(1, int(frame_step))]
    if max_frames <= 0 or len(stepped) <= max_frames:
        return stepped

    indices = np.linspace(0, len(stepped) - 1, int(max_frames), dtype=np.int64)
    return [stepped[int(i)] for i in indices]


def _integrate_tsdf(args: argparse.Namespace) -> Dict[str, Any]:
    db_path = os.path.abspath(os.path.expanduser(args.db))
    out_dir = os.path.abspath(os.path.expanduser(args.out or DEFAULT_TSDF_OUT))
    export_dir = os.path.abspath(os.path.expanduser(
        args.export_dir or os.path.join(out_dir, "exported_rgbd")
    ))
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.exists(db_path):
        raise RuntimeError("RTAB-Map database not found: {}".format(db_path))

    exported = _export_rtabmap_rgbd(
        db_path=db_path,
        export_dir=export_dir,
        reuse_export=bool(args.reuse_export),
    )
    pose_rows = _read_pose_rows(exported["poses_path"])
    selected_rows = _select_pose_rows(
        pose_rows,
        frame_step=int(args.frame_step),
        max_frames=int(args.max_frames),
    )
    print(
        "[chora-assets] integrating {} / {} camera poses".format(
            len(selected_rows),
            len(pose_rows),
        )
    )

    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=float(args.voxel_length),
        sdf_trunc=float(args.sdf_trunc),
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )

    intrinsic_cache: Dict[str, Tuple[Any, Dict[str, Any]]] = {}
    first_intrinsic_meta = None
    integrated_ids = []
    skipped = []
    start = time.time()

    for index, row in enumerate(selected_rows):
        node_id = int(row["id"])
        rgb_path = os.path.join(exported["rgb_dir"], "{}.jpg".format(node_id))
        depth_path = os.path.join(exported["depth_dir"], "{}.png".format(node_id))
        calib_path = os.path.join(exported["calib_dir"], "{}.yaml".format(node_id))
        if not (os.path.exists(rgb_path) and os.path.exists(depth_path) and os.path.exists(calib_path)):
            skipped.append(node_id)
            continue

        if calib_path not in intrinsic_cache:
            intrinsic_cache[calib_path] = _read_open3d_intrinsic(calib_path)
        intrinsic, intrinsic_meta = intrinsic_cache[calib_path]
        if first_intrinsic_meta is None:
            first_intrinsic_meta = intrinsic_meta

        color = o3d.io.read_image(rgb_path)
        depth = o3d.io.read_image(depth_path)
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            color,
            depth,
            depth_scale=float(args.depth_scale),
            depth_trunc=float(args.depth_trunc),
            convert_rgb_to_intensity=False,
        )

        world_from_camera = _pose_matrix_from_row(row)
        camera_from_world = np.linalg.inv(world_from_camera)
        volume.integrate(rgbd, intrinsic, camera_from_world)
        integrated_ids.append(node_id)

        if args.progress_every > 0 and (len(integrated_ids) % int(args.progress_every)) == 0:
            print(
                "[chora-assets] integrated {}/{} frames".format(
                    len(integrated_ids),
                    len(selected_rows),
                )
            )

    integrate_seconds = time.time() - start
    if not integrated_ids:
        raise RuntimeError("no RGB-D frames were integrated")

    label = _format_voxel(float(args.voxel_length))
    mesh_path = os.path.join(out_dir, "tsdf_mesh_voxel{}.ply".format(label))
    cloud_path = os.path.join(out_dir, "tsdf_cloud_voxel{}.ply".format(label))

    print("[chora-assets] extracting TSDF mesh")
    mesh = volume.extract_triangle_mesh()
    mesh = _clean_mesh(mesh)
    _clamp_geometry_colors(mesh)
    before_decimation = len(mesh.triangles)
    if args.tsdf_target_triangles > 0 and before_decimation > int(args.tsdf_target_triangles):
        print(
            "[chora-assets] decimating TSDF mesh {} -> {} triangles".format(
                before_decimation,
                int(args.tsdf_target_triangles),
            )
        )
        mesh = mesh.simplify_quadric_decimation(
            target_number_of_triangles=int(args.tsdf_target_triangles)
        )
        mesh = _clean_mesh(mesh)
        _clamp_geometry_colors(mesh)
    _write_mesh(mesh_path, mesh)
    current_mesh_path = os.path.join(out_dir, "tsdf_mesh_current.ply")

    cloud_asset = None
    current_cloud_path = None
    if not args.no_tsdf_cloud:
        print("[chora-assets] extracting TSDF cloud")
        pcd = volume.extract_point_cloud()
        pcd = _clean_point_cloud(pcd, float(args.tsdf_cloud_voxel))
        _write_point_cloud(cloud_path, pcd)
        current_cloud_path = os.path.join(out_dir, "tsdf_cloud_current.ply")
        cloud_asset = {
            "path": cloud_path,
            "current_path": current_cloud_path,
            "kind": "pointcloud",
            "points": int(len(pcd.points)),
            "voxel_m": float(args.tsdf_cloud_voxel),
            "bounds": _bounds_dict(pcd),
        }

    _update_current_asset_link(mesh_path, os.path.basename(current_mesh_path))
    if current_cloud_path is not None:
        _update_current_asset_link(cloud_path, os.path.basename(current_cloud_path))

    manifest = {
        "schema_version": 1,
        "created_at_unix": float(time.time()),
        "mode": "tsdf",
        "open3d_version": getattr(o3d, "__version__", "unknown"),
        "source": {
            "db_path": db_path,
            "db_mtime": float(os.stat(db_path).st_mtime),
            "db_size_bytes": int(os.stat(db_path).st_size),
        },
        "export": {
            "dir": export_dir,
            "rgb_dir": exported["rgb_dir"],
            "depth_dir": exported["depth_dir"],
            "calib_dir": exported["calib_dir"],
            "poses_path": exported["poses_path"],
            "pose_rows": int(len(pose_rows)),
            "selected_rows": int(len(selected_rows)),
            "integrated_frames": int(len(integrated_ids)),
            "skipped_frame_ids": skipped,
        },
        "tsdf": {
            "voxel_length": float(args.voxel_length),
            "sdf_trunc": float(args.sdf_trunc),
            "depth_scale": float(args.depth_scale),
            "depth_trunc": float(args.depth_trunc),
            "frame_step": int(args.frame_step),
            "max_frames": int(args.max_frames),
            "integrate_seconds": float(integrate_seconds),
            "camera_pose_convention": (
                "rtabmap-export --poses_camera gives optimized camera-to-map "
                "poses; Open3D integration receives their inverse."
            ),
            "intrinsic_sample": first_intrinsic_meta,
        },
        "mesh_asset": {
            "path": mesh_path,
            "current_path": current_mesh_path,
            "kind": "mesh",
            "vertices": int(len(mesh.vertices)),
            "triangles": int(len(mesh.triangles)),
            "triangles_before_decimation": int(before_decimation),
            "target_triangles": int(args.tsdf_target_triangles),
            "bounds": _bounds_dict(mesh),
        },
        "cloud_asset": cloud_asset,
    }

    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("[chora-assets] wrote {}".format(mesh_path))
    if cloud_asset is not None:
        print("[chora-assets] wrote {}".format(cloud_path))
    print("[chora-assets] wrote {}".format(manifest_path))

    if not args.keep_export:
        print("[chora-assets] removing temporary export {}".format(export_dir))
        shutil.rmtree(export_dir)

    return manifest


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
    out_dir = os.path.abspath(os.path.expanduser(args.out or DEFAULT_OUT))

    if args.mode == "tsdf":
        return _integrate_tsdf(args)

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
            "implemented": True,
            "mode": "Use --mode tsdf with --db to integrate RGB-D frames from RTAB-Map.",
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
    parser.add_argument("--db", default=DEFAULT_TSDF_DB)
    parser.add_argument("--out", default=None)
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
        help="Build from an exported PLY or integrate RGB-D frames from an RTAB-Map DB.",
    )
    """ 
    parser.add_argument("--mesh", action="store_true")
    parser.add_argument("--mesh-source-voxel", type=float, default=0.08)
    parser.add_argument("--poisson-depth", type=int, default=8)
    parser.add_argument("--density-quantile", type=float, default=0.02)
    parser.add_argument("--target-triangles", type=int, default=200000)
    parser.add_argument("--export-dir", default=None)
    parser.add_argument("--reuse-export", action="store_true")
    parser.add_argument("--keep-export", action="store_true")
    parser.add_argument("--voxel-length", type=float, default=0.035)
    parser.add_argument("--sdf-trunc", type=float, default=0.14)
    parser.add_argument("--depth-scale", type=float, default=1000.0)
    parser.add_argument("--depth-trunc", type=float, default=4.5)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--tsdf-target-triangles", type=int, default=300000)
    parser.add_argument("--tsdf-cloud-voxel", type=float, default=0.02)
    parser.add_argument("--no-tsdf-cloud", action="store_true")
    parser.add_argument("--progress-every", type=int, default=50)
    """
    parser.add_argument("--mesh", action="store_true")
    parser.add_argument("--mesh-source-voxel", type=float, default=0.08)
    parser.add_argument("--poisson-depth", type=int, default=8)
    parser.add_argument("--density-quantile", type=float, default=0.02)
    parser.add_argument("--target-triangles", type=int, default=200000)
    parser.add_argument("--export-dir", default=None)
    parser.add_argument("--reuse-export", action="store_true")
    parser.add_argument("--keep-export", action="store_true")
    parser.add_argument("--voxel-length", type=float, default=0.025)
    parser.add_argument("--sdf-trunc", type=float, default=0.14)
    parser.add_argument("--depth-scale", type=float, default=1000.0)
    parser.add_argument("--depth-trunc", type=float, default=4.5)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--tsdf-target-triangles", type=int, default=500000)
    parser.add_argument("--tsdf-cloud-voxel", type=float, default=0.02)
    parser.add_argument("--no-tsdf-cloud", action="store_true")
    parser.add_argument("--progress-every", type=int, default=50)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    _build_assets(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
