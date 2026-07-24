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
from pathlib import Path
import re
import threading
from typing import Any, Dict, List, Optional

from ruamel.yaml import YAML

from .core import Verbosity, api_call


__all__ = ["list", "get", "reload", "go_to"]


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
