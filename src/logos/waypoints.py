"""
My named, persistent navigation poses.

I keep waypoint knowledge separate from Chora so the same stable records can
drive rendering, navigation, and future semantic retrieval. The YAML file is
human-editable, while this module provides a small validated read/query API.
"""

from __future__ import annotations

import builtins
from copy import deepcopy
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Dict, List, Optional

from ruamel.yaml import YAML

from .core import Verbosity, api_call


__all__ = [
    "list",
    "get",
    "reload",
    "normalize_pose",
    "upsert",
    "upsert_here",
    "update",
    "remove",
    "go_to",
]


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_TOP_LEVEL_KEYS = {"schema_version", "frame", "waypoints"}
_WAYPOINT_KEYS = {
    "name",
    "description",
    "pose",
    "created_at",
    "navigable",
    "emoji",
    "tags",
    "enabled",
    "render",
    "metadata",
}
_POSE_KEYS = {"position", "rpy_deg"}
_RENDER_KEYS = {
    "mode",
    "scale_m",
    "icon_height_m",
    "marker",
    "show_heading",
    "emoji_file",
}
_RENDER_MODES = {"floor", "pose_billboard", "camera_billboard", "marker"}
_MARKER_MODES = {"none", "pin", "axes"}
_MISSING = object()
_MUTABLE_FIELDS = {
    "name",
    "description",
    "created_at",
    "navigable",
    "emoji",
    "tags",
    "enabled",
    "render",
    "metadata",
}
_POSE_OVERRIDE_FIELDS = {
    "x",
    "y",
    "z",
    "theta_deg",
    "yaw_deg",
    "roll_deg",
    "pitch_deg",
}


def _waypoints_config() -> Dict[str, Any]:
    """Read my live waypoint configuration without caching it separately."""
    try:
        import logos

        merged = logos.config.merged
        config = merged.get("waypoints", {})
        return dict(config) if isinstance(config, dict) else {}
    except Exception:
        return {}


def _configured_path() -> Path:
    configured = _waypoints_config().get(
        "file", "hypomnemata/chora/waypoints_00.yaml"
    )
    return Path(str(configured)).expanduser()


def _require_mapping(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("{} must be a mapping".format(label))
    return dict(value)


def _reject_unknown(
    value: Dict[str, Any],
    allowed: set,
    label: str,
) -> None:
    unknown = sorted(set(value.keys()) - allowed)
    if unknown:
        raise ValueError(
            "{} has unknown field(s): {}".format(label, ", ".join(unknown))
        )


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("{} must be a non-empty string".format(label))
    return value.strip()


def _require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError("{} must be true or false".format(label))
    return value


def _require_vector3(value: Any, label: str) -> List[float]:
    if not isinstance(value, (builtins.list, tuple)) or len(value) != 3:
        raise ValueError("{} must contain exactly three numbers".format(label))

    result: List[float] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(
                "{}[{}] must be a finite number".format(label, index)
            )
        number = float(item)
        if not math.isfinite(number):
            raise ValueError(
                "{}[{}] must be a finite number".format(label, index)
            )
        result.append(number)
    return result


def _member(value: Any, name: str, default: Any = _MISSING) -> Any:
    """Read one field from either a mapping or a ROS-style object."""
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{} must be a finite number".format(label))
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("{} must be a finite number".format(label))
    return number


def _pose_frame(value: Any) -> Optional[str]:
    """Find an optional frame on a ROS message or pose dictionary."""
    current = value
    for _ in range(4):
        frame = _member(current, "frame", _MISSING)
        if frame is _MISSING:
            frame = _member(current, "frame_id", _MISSING)
        if frame is not _MISSING and frame is not None:
            return str(frame)

        header = _member(current, "header", _MISSING)
        if header is not _MISSING and header is not None:
            frame_id = _member(header, "frame_id", _MISSING)
            if frame_id is not _MISSING and frame_id is not None:
                return str(frame_id)

        nested = _member(current, "pose", _MISSING)
        if nested is _MISSING or nested is None:
            break
        current = nested
    return None


def _unwrap_pose(value: Any) -> Any:
    """Peel PoseStamped, PoseWithCovariance, or TransformStamped shells."""
    current = value
    for _ in range(4):
        nested = _member(current, "pose", _MISSING)
        if nested is _MISSING:
            nested = _member(current, "transform", _MISSING)
        if nested is _MISSING or nested is None:
            break
        current = nested
    return current


def _xyz_from_value(value: Any, label: str) -> List[float]:
    if isinstance(value, (builtins.list, tuple)):
        return _require_vector3(value, label)
    return [
        _finite_number(_member(value, "x"), "{}.x".format(label)),
        _finite_number(_member(value, "y"), "{}.y".format(label)),
        _finite_number(_member(value, "z", 0.0), "{}.z".format(label)),
    ]


def _quaternion_to_rpy_deg(value: Any, label: str) -> List[float]:
    x = _finite_number(_member(value, "x"), "{}.x".format(label))
    y = _finite_number(_member(value, "y"), "{}.y".format(label))
    z = _finite_number(_member(value, "z"), "{}.z".format(label))
    w = _finite_number(_member(value, "w"), "{}.w".format(label))

    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm < 1e-12:
        raise ValueError("{} must not be a zero quaternion".format(label))
    x, y, z, w = x / norm, y / norm, z / norm, w / norm

    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    if abs(sinp) >= 1.0:
        pitch = math.copysign(math.pi / 2.0, sinp)
    else:
        pitch = math.asin(sinp)

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return [math.degrees(roll), math.degrees(pitch), math.degrees(yaw)]


def normalize_pose(
    pose: Any = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
    z: Optional[float] = None,
    theta_deg: Optional[float] = None,
    yaw_deg: Optional[float] = None,
    roll_deg: Optional[float] = None,
    pitch_deg: Optional[float] = None,
) -> Dict[str, List[float]]:
    """
    Normalize common robot pose shapes into my waypoint pose convention.

    I accept canonical Chora dictionaries, flat x/y/theta_deg dictionaries,
    ROS Pose/PoseStamped/Odometry-like objects or dictionaries, quaternion
    orientation dictionaries, [x, y, theta_deg], and [x, y, z, theta_deg].
    Explicit coordinate arguments override values extracted from `pose`.

    Args:
        pose: Any supported pose object, mapping, or coordinate sequence.
        x: Optional map X override in meters.
        y: Optional map Y override in meters.
        z: Optional map Z override in meters.
        theta_deg: Optional yaw override in degrees.
        yaw_deg: Alias for theta_deg.
        roll_deg: Optional roll override in degrees.
        pitch_deg: Optional pitch override in degrees.

    Returns:
        `{"position": [x, y, z], "rpy_deg": [roll, pitch, yaw]}`.

    Note to self:
        If an input declares a frame, I accept only `map`. I never silently
        reinterpret odom coordinates as persistent map coordinates.
    """
    frame = _pose_frame(pose) if pose is not None else None
    if frame is not None and frame.strip().lstrip("/") != "map":
        raise ValueError(
            "Waypoint poses must be in the map frame, not {!r}".format(frame)
        )

    position: List[Optional[float]] = [None, None, None]
    rpy: List[Optional[float]] = [0.0, 0.0, None]

    if pose is not None and isinstance(pose, (builtins.list, tuple)):
        if len(pose) == 3:
            position = [
                _finite_number(pose[0], "pose[0]"),
                _finite_number(pose[1], "pose[1]"),
                0.0,
            ]
            rpy[2] = _finite_number(pose[2], "pose[2]")
        elif len(pose) == 4:
            position = [
                _finite_number(pose[0], "pose[0]"),
                _finite_number(pose[1], "pose[1]"),
                _finite_number(pose[2], "pose[2]"),
            ]
            rpy[2] = _finite_number(pose[3], "pose[3]")
        else:
            raise ValueError(
                "pose sequences must be [x, y, theta_deg] or "
                "[x, y, z, theta_deg]"
            )
    elif pose is not None:
        core = _unwrap_pose(pose)
        position_value = _member(core, "position", _MISSING)
        if position_value is _MISSING:
            position_value = _member(core, "translation", _MISSING)
        if position_value is not _MISSING:
            position = _xyz_from_value(position_value, "pose.position")
        elif (
            _member(core, "x", _MISSING) is not _MISSING
            and _member(core, "y", _MISSING) is not _MISSING
        ):
            position = _xyz_from_value(core, "pose")

        rpy_value = _member(core, "rpy_deg", _MISSING)
        if rpy_value is not _MISSING:
            rpy = _require_vector3(rpy_value, "pose.rpy_deg")
        else:
            orientation = _member(core, "orientation", _MISSING)
            if orientation is _MISSING:
                orientation = _member(core, "rotation", _MISSING)
            if orientation is not _MISSING:
                rpy = _quaternion_to_rpy_deg(
                    orientation, "pose.orientation"
                )
            else:
                extracted_yaw = _member(core, "theta_deg", _MISSING)
                if extracted_yaw is _MISSING:
                    extracted_yaw = _member(core, "yaw_deg", _MISSING)
                if extracted_yaw is not _MISSING:
                    rpy[2] = _finite_number(
                        extracted_yaw, "pose.theta_deg"
                    )
                else:
                    theta_rad = _member(core, "theta", _MISSING)
                    if theta_rad is not _MISSING:
                        rpy[2] = math.degrees(
                            _finite_number(theta_rad, "pose.theta")
                        )

    overrides = [x, y, z]
    for index, override in enumerate(overrides):
        if override is not None:
            position[index] = _finite_number(
                override, ("x", "y", "z")[index]
            )

    if theta_deg is not None and yaw_deg is not None:
        theta_value = _finite_number(theta_deg, "theta_deg")
        yaw_value = _finite_number(yaw_deg, "yaw_deg")
        if abs(theta_value - yaw_value) > 1e-9:
            raise ValueError("theta_deg and yaw_deg disagree")
        rpy[2] = theta_value
    elif theta_deg is not None:
        rpy[2] = _finite_number(theta_deg, "theta_deg")
    elif yaw_deg is not None:
        rpy[2] = _finite_number(yaw_deg, "yaw_deg")

    if roll_deg is not None:
        rpy[0] = _finite_number(roll_deg, "roll_deg")
    if pitch_deg is not None:
        rpy[1] = _finite_number(pitch_deg, "pitch_deg")

    if position[2] is None:
        position[2] = 0.0
    if position[0] is None or position[1] is None or rpy[2] is None:
        raise ValueError(
            "A waypoint pose needs map x, y, and theta_deg/yaw orientation"
        )

    return {
        "position": [float(value) for value in position],
        "rpy_deg": [float(value) for value in rpy],
    }


def _require_utc_timestamp(value: Any, label: str) -> str:
    text = _require_text(value, label)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        raise ValueError("{} must be an ISO-8601 timestamp".format(label))

    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("{} must include a UTC timezone".format(label))
    return text


def _normalize_render(value: Any, label: str) -> Dict[str, Any]:
    render = _require_mapping(value, label)
    _reject_unknown(render, _RENDER_KEYS, label)
    normalized: Dict[str, Any] = {}

    if "mode" in render:
        mode = _require_text(render["mode"], "{}.mode".format(label))
        if mode not in _RENDER_MODES:
            raise ValueError(
                "{}.mode must be one of {}".format(
                    label, ", ".join(sorted(_RENDER_MODES))
                )
            )
        normalized["mode"] = mode

    for key in ("scale_m", "icon_height_m"):
        if key not in render:
            continue
        item = render[key]
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("{}.{} must be a number".format(label, key))
        number = float(item)
        if not math.isfinite(number) or number <= 0.0:
            raise ValueError("{}.{} must be positive".format(label, key))
        normalized[key] = number

    if "marker" in render:
        marker = _require_text(render["marker"], "{}.marker".format(label))
        if marker not in _MARKER_MODES:
            raise ValueError(
                "{}.marker must be one of {}".format(
                    label, ", ".join(sorted(_MARKER_MODES))
                )
            )
        normalized["marker"] = marker

    if "show_heading" in render:
        normalized["show_heading"] = _require_bool(
            render["show_heading"], "{}.show_heading".format(label)
        )

    if "emoji_file" in render:
        filename = _require_text(
            render["emoji_file"], "{}.emoji_file".format(label)
        )
        if Path(filename).name != filename:
            raise ValueError("{}.emoji_file must be a filename".format(label))
        if not filename.lower().endswith(".png"):
            raise ValueError("{}.emoji_file must name a PNG file".format(label))
        normalized["emoji_file"] = filename

    return normalized


def _normalize_waypoint(
    waypoint_id: Any,
    value: Any,
    frame: str,
) -> Dict[str, Any]:
    waypoint_id = _require_text(waypoint_id, "waypoint id")
    if not _ID_RE.match(waypoint_id):
        raise ValueError(
            "waypoint id {!r} may contain only letters, numbers, '.', '_', and '-'".format(
                waypoint_id
            )
        )

    label = "waypoints.{}".format(waypoint_id)
    record = _require_mapping(value, label)
    _reject_unknown(record, _WAYPOINT_KEYS, label)

    required = {
        "name",
        "description",
        "pose",
        "created_at",
        "navigable",
    }
    missing = sorted(required - set(record.keys()))
    if missing:
        raise ValueError(
            "{} is missing required field(s): {}".format(label, ", ".join(missing))
        )

    pose_label = "{}.pose".format(label)
    pose = _require_mapping(record["pose"], pose_label)
    _reject_unknown(pose, _POSE_KEYS, pose_label)
    missing_pose = sorted(_POSE_KEYS - set(pose.keys()))
    if missing_pose:
        raise ValueError(
            "{} is missing required field(s): {}".format(
                pose_label, ", ".join(missing_pose)
            )
        )

    normalized: Dict[str, Any] = {
        "id": waypoint_id,
        "frame": frame,
        "name": _require_text(record["name"], "{}.name".format(label)),
        "description": _require_text(
            record["description"], "{}.description".format(label)
        ),
        "pose": {
            "position": _require_vector3(
                pose["position"], "{}.position".format(pose_label)
            ),
            "rpy_deg": _require_vector3(
                pose["rpy_deg"], "{}.rpy_deg".format(pose_label)
            ),
        },
        "created_at": _require_utc_timestamp(
            record["created_at"], "{}.created_at".format(label)
        ),
        "navigable": _require_bool(
            record["navigable"], "{}.navigable".format(label)
        ),
        "enabled": _require_bool(
            record.get("enabled", True), "{}.enabled".format(label)
        ),
        "tags": [],
        "metadata": {},
    }

    if "emoji" in record:
        normalized["emoji"] = _require_text(
            record["emoji"], "{}.emoji".format(label)
        )

    tags = record.get("tags", [])
    if not isinstance(tags, builtins.list):
        raise ValueError("{}.tags must be a list of strings".format(label))
    seen_tags = set()
    for index, tag in enumerate(tags):
        tag_text = _require_text(tag, "{}.tags[{}]".format(label, index))
        folded = tag_text.casefold()
        if folded not in seen_tags:
            normalized["tags"].append(tag_text)
            seen_tags.add(folded)

    if "render" in record:
        normalized["render"] = _normalize_render(
            record["render"], "{}.render".format(label)
        )

    metadata = record.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("{}.metadata must be a mapping".format(label))
    normalized["metadata"] = deepcopy(dict(metadata))

    return normalized


def _load_validated(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError("Waypoint file not found: {}".format(path))

    yaml = YAML(typ="safe")
    with path.open("r", encoding="utf-8") as stream:
        raw = yaml.load(stream) or {}

    config = _require_mapping(raw, "waypoint file")
    _reject_unknown(config, _TOP_LEVEL_KEYS, "waypoint file")

    if config.get("schema_version") != 1:
        raise ValueError("waypoint file schema_version must be 1")
    frame = _require_text(config.get("frame"), "waypoint file frame")
    if frame != "map":
        raise ValueError("waypoint file frame must be 'map' for schema version 1")

    raw_waypoints = _require_mapping(
        config.get("waypoints"), "waypoint file waypoints"
    )
    validated: Dict[str, Dict[str, Any]] = {}
    for waypoint_id, record in raw_waypoints.items():
        normalized = _normalize_waypoint(waypoint_id, record, frame)
        validated[normalized["id"]] = normalized
    return validated


def _record_for_yaml(record: Dict[str, Any]) -> Dict[str, Any]:
    """Strip runtime-only keys and arrange one record for readable YAML."""
    stored: Dict[str, Any] = {
        "name": record["name"],
        "description": record["description"],
        "pose": deepcopy(record["pose"]),
        "created_at": record["created_at"],
        "navigable": record["navigable"],
    }
    if "emoji" in record:
        stored["emoji"] = record["emoji"]
    if record.get("tags"):
        stored["tags"] = deepcopy(record["tags"])
    if not record.get("enabled", True):
        stored["enabled"] = False
    if "render" in record:
        stored["render"] = deepcopy(record["render"])
    if record.get("metadata"):
        stored["metadata"] = deepcopy(record["metadata"])
    return stored


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


class _WaypointStore:
    """Hold my last-known-good waypoint registry behind a small lock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._loaded_path: Optional[Path] = None
        self._records: Dict[str, Dict[str, Any]] = {}

    def _ensure_loaded(self) -> None:
        path = _configured_path()
        with self._lock:
            needs_load = self._loaded_path != path
        if needs_load:
            self.reload()

    def reload(self) -> int:
        path = _configured_path()
        validated = _load_validated(path)
        with self._lock:
            self._records = validated
            self._loaded_path = path
            return len(self._records)

    def get_id(self, waypoint_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_loaded()
        with self._lock:
            record = self._records.get(waypoint_id)
            return deepcopy(record) if record is not None else None

    def _write_raw_locked(
        self,
        path: Path,
        raw: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """Atomically validate and replace my YAML while preserving comments."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=".{}.".format(path.name),
            suffix=".tmp",
            dir=str(path.parent),
        )
        os.close(fd)
        temporary_path = Path(temporary_name)

        try:
            yaml = YAML()
            yaml.default_flow_style = False
            yaml.preserve_quotes = True
            with temporary_path.open("w", encoding="utf-8") as stream:
                yaml.dump(raw, stream)

            validated = _load_validated(temporary_path)
            os.replace(str(temporary_path), str(path))
            self._records = validated
            self._loaded_path = path
            return validated
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def persist_upsert(
        self,
        waypoint_id: str,
        record: Dict[str, Any],
    ) -> Dict[str, Any]:
        path = _configured_path()
        with self._lock:
            # Refuse to overwrite an invalid hand edit, and incorporate any
            # valid edits made since my last API call.
            self._records = _load_validated(path)
            self._loaded_path = path

            yaml = YAML()
            yaml.preserve_quotes = True
            with path.open("r", encoding="utf-8") as stream:
                raw = yaml.load(stream) or {}
            waypoints = raw.get("waypoints")
            if not isinstance(waypoints, dict):
                raise ValueError("waypoint file waypoints must be a mapping")

            waypoints[waypoint_id] = _record_for_yaml(record)
            validated = self._write_raw_locked(path, raw)
            return deepcopy(validated[waypoint_id])

    def persist_remove(self, waypoint_id: str) -> Dict[str, Any]:
        path = _configured_path()
        with self._lock:
            self._records = _load_validated(path)
            self._loaded_path = path
            if waypoint_id not in self._records:
                raise KeyError("Waypoint {!r} not found".format(waypoint_id))
            removed = deepcopy(self._records[waypoint_id])

            yaml = YAML()
            yaml.preserve_quotes = True
            with path.open("r", encoding="utf-8") as stream:
                raw = yaml.load(stream) or {}
            waypoints = raw.get("waypoints")
            if not isinstance(waypoints, dict):
                raise ValueError("waypoint file waypoints must be a mapping")
            del waypoints[waypoint_id]
            self._write_raw_locked(path, raw)
            return removed

    def list(
        self,
        tags: Optional[List[str]] = None,
        navigable_only: bool = False,
    ) -> List[Dict[str, Any]]:
        self._ensure_loaded()

        requested_tags = set()
        if tags is not None:
            if not isinstance(tags, builtins.list):
                raise ValueError("tags must be a list of strings")
            for index, tag in enumerate(tags):
                requested_tags.add(
                    _require_text(tag, "tags[{}]".format(index)).casefold()
                )

        with self._lock:
            records = []
            for waypoint_id in sorted(self._records):
                record = self._records[waypoint_id]
                if not record["enabled"]:
                    continue
                if navigable_only and not record["navigable"]:
                    continue
                record_tags = {tag.casefold() for tag in record["tags"]}
                if requested_tags and not requested_tags.issubset(record_tags):
                    continue
                records.append(deepcopy(record))
            return records

    def get(self, id_or_name: str) -> Dict[str, Any]:
        self._ensure_loaded()
        query = _require_text(id_or_name, "id_or_name")

        with self._lock:
            if query in self._records:
                return deepcopy(self._records[query])

            folded = query.casefold()
            matches = [
                record
                for record in self._records.values()
                if record["name"].casefold() == folded
            ]

            if not matches:
                raise KeyError("Waypoint {!r} not found".format(query))
            if len(matches) > 1:
                ids = ", ".join(sorted(record["id"] for record in matches))
                raise ValueError(
                    "Waypoint name {!r} is ambiguous; use one of these IDs: {}".format(
                        query, ids
                    )
                )
            return deepcopy(matches[0])


_STORE = _WaypointStore()


def list(
    tags: Optional[List[str]] = None,
    navigable_only: bool = False,
) -> List[Dict[str, Any]]:
    """
    List my enabled waypoint records.

    Args:
        tags: Optional tags that every returned waypoint must contain.
        navigable_only: If True, omit visual-only waypoint records.

    Returns:
        Deep-copied waypoint dictionaries sorted by stable ID.
    """
    return _STORE.list(tags=tags, navigable_only=navigable_only)


def get(id_or_name: str) -> Dict[str, Any]:
    """
    Get one waypoint by exact ID or unique case-insensitive short name.

    Args:
        id_or_name: Stable waypoint ID or its complete short name.

    Returns:
        A deep copy of the validated waypoint record.
    """
    return _STORE.get(id_or_name)


@api_call(default_verbosity=Verbosity.ACK)
def reload() -> int:
    """
    Reload my waypoint YAML transactionally.

    Returns:
        Number of valid waypoint records now loaded.

    Note to self:
        A malformed edit raises an error without replacing my last-known-good
        in-memory registry.
    """
    return _STORE.reload()


def _current_map_pose() -> Any:
    from . import ros

    current = ros.get_pose()
    if current is None:
        raise RuntimeError("My current pose is unavailable")
    frame = _pose_frame(current)
    if frame is not None and frame.strip().lstrip("/") != "map":
        raise RuntimeError(
            "My current pose is in {!r}, not the map frame".format(frame)
        )
    return current


def _upsert(
    waypoint_id: str,
    pose: Any,
    current_pose: bool,
    fields: Dict[str, Any],
) -> Dict[str, Any]:
    waypoint_id = _require_text(waypoint_id, "waypoint_id")
    if not _ID_RE.match(waypoint_id):
        raise ValueError(
            "waypoint_id may contain only letters, numbers, '.', '_', and '-'"
        )
    if not isinstance(current_pose, bool):
        raise ValueError("current_pose must be true or false")
    if current_pose and pose is not None:
        raise ValueError("Pass either pose or current_pose=True, not both")

    unknown = sorted(
        set(fields.keys()) - _MUTABLE_FIELDS - _POSE_OVERRIDE_FIELDS
    )
    if unknown:
        raise ValueError(
            "Unknown waypoint field(s): {}".format(", ".join(unknown))
        )

    _STORE.reload()
    existing = _STORE.get_id(waypoint_id)
    if existing is None:
        display_name = waypoint_id.replace("_", " ").replace("-", " ").title()
        candidate: Dict[str, Any] = {
            "name": display_name,
            "description": "Saved waypoint: {}".format(display_name),
            "created_at": _utc_now_text(),
            "navigable": False,
        }
    else:
        candidate = _record_for_yaml(existing)

    pose_overrides = {
        key: fields.pop(key)
        for key in builtins.list(fields.keys())
        if key in _POSE_OVERRIDE_FIELDS
    }

    pose_source = pose
    if current_pose:
        pose_source = _current_map_pose()
    elif pose_source is None and existing is not None:
        pose_source = existing["pose"]

    if pose_source is not None or pose_overrides:
        candidate["pose"] = normalize_pose(
            pose_source,
            x=pose_overrides.get("x"),
            y=pose_overrides.get("y"),
            z=pose_overrides.get("z"),
            theta_deg=pose_overrides.get("theta_deg"),
            yaw_deg=pose_overrides.get("yaw_deg"),
            roll_deg=pose_overrides.get("roll_deg"),
            pitch_deg=pose_overrides.get("pitch_deg"),
        )
    elif existing is None:
        raise ValueError(
            "New waypoints need pose=..., x/y/theta_deg, or current_pose=True"
        )

    for key, value in fields.items():
        if value is None and key in ("emoji", "render"):
            candidate.pop(key, None)
        elif value is None and key == "tags":
            candidate["tags"] = []
        elif value is None and key == "metadata":
            candidate["metadata"] = {}
        else:
            candidate[key] = deepcopy(value)

    normalized = _normalize_waypoint(waypoint_id, candidate, "map")
    return _STORE.persist_upsert(waypoint_id, normalized)


@api_call(default_verbosity=Verbosity.ACK)
def upsert(
    waypoint_id: str,
    pose: Any = None,
    current_pose: bool = False,
    **fields: Any
) -> Dict[str, Any]:
    """
    Create or replace fields on one persistent waypoint.

    Args:
        waypoint_id: Stable machine-readable ID.
        pose: Any pose accepted by normalize_pose().
        current_pose: If True, capture my current map pose.
        **fields: Optional name, description, navigable, emoji, tags, enabled,
            render, metadata, created_at, or x/y/z/angle pose overrides.

    Returns:
        The complete validated record written to YAML.

    Note to self:
        New records default to navigable=False. Existing fields and pose values
        remain unchanged unless I explicitly replace or override them.
    """
    return _upsert(waypoint_id, pose, current_pose, dict(fields))


@api_call(default_verbosity=Verbosity.ACK)
def upsert_here(
    waypoint_id: str,
    **fields: Any
) -> Dict[str, Any]:
    """
    Create or move a waypoint to my current map pose.

    Args:
        waypoint_id: Stable machine-readable ID.
        **fields: The same optional record fields accepted by upsert().

    Returns:
        The complete validated record written to YAML.
    """
    return _upsert(waypoint_id, None, True, dict(fields))


@api_call(default_verbosity=Verbosity.ACK)
def update(
    id_or_name: str,
    pose: Any = None,
    current_pose: bool = False,
    **changes: Any
) -> Dict[str, Any]:
    """
    Partially update an existing waypoint by ID or unique short name.

    Args:
        id_or_name: Stable waypoint ID or unique complete short name.
        pose: Optional replacement pose in any supported representation.
        current_pose: If True, replace its pose with my current map pose.
        **changes: Record fields or individual pose components to replace.

    Returns:
        The complete updated waypoint record.
    """
    existing = get(id_or_name)
    if pose is None and not current_pose and not changes:
        raise ValueError("No waypoint changes were supplied")
    return _upsert(existing["id"], pose, current_pose, dict(changes))


@api_call(default_verbosity=Verbosity.ACK)
def remove(id_or_name: str) -> Dict[str, Any]:
    """
    Delete one persistent waypoint by ID or unique short name.

    Args:
        id_or_name: Stable waypoint ID or unique complete short name.

    Returns:
        The record that was removed.
    """
    existing = get(id_or_name)
    return _STORE.persist_remove(existing["id"])


@api_call(default_verbosity=Verbosity.BRIEF)
def go_to(id_or_name: str, wait: bool = False) -> Any:
    """
    Navigate to one of my explicitly navigable saved poses.

    Args:
        id_or_name: Stable waypoint ID or unique complete short name.
        wait: If True, wait for navigation to finish.

    Returns:
        The NavTask returned by logos.nav.go_to_abs().
    """
    record = get(id_or_name)
    if not record["enabled"]:
        raise ValueError("Waypoint {!r} is disabled".format(record["id"]))
    if not record["navigable"]:
        raise ValueError("Waypoint {!r} is not navigable".format(record["id"]))
    if record["frame"] != "map":
        raise ValueError("Navigation waypoints must be in the map frame")

    from . import nav

    position = record["pose"]["position"]
    yaw_deg = record["pose"]["rpy_deg"][2]
    return nav.go_to_abs(position[0], position[1], deg=yaw_deg, wait=wait)
