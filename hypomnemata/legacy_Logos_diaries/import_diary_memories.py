#!/usr/bin/env python3
"""
Extract durable Logos diary memories and optionally import them into Chroma.

This is an operator tool, not part of the live Logos runtime.  It reads old
`memories/diary_*.yaml` files, asks Gemini to distill non-technical facts and
episodic memories, writes a transparent JSONL preview, and only touches the
shared vector database when `--write` is supplied.
"""

import argparse
import datetime
import glob
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from ruamel.yaml import YAML
except ImportError:  # pragma: no cover - this repo normally has ruamel.
    YAML = None  # type: ignore

try:
    import requests
except ImportError:  # pragma: no cover - reported cleanly at runtime.
    requests = None  # type: ignore


DEFAULT_INPUT = "memories/diary_*.yaml"
DEFAULT_CACHE = "state/diary_memory_import_preview.jsonl"
DEFAULT_STATUS_CACHE = "state/diary_memory_import_status.jsonl"
DEFAULT_SIDECAR_URL = "http://127.0.0.1:8123"
DEFAULT_MODEL = "gemini-3-flash-preview"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_BATCH_SIZE = 20
DEFAULT_COLLECTION = "logos__shared__logoi_collective"
DEFAULT_HELPER_PYTHON = os.getenv(
    "LOGOS_VENV_PY311",
    "/home/robot/robot_ws/.venv/bin/python3",
)
MAX_EMBED_CHARS = 1500

CODE_TOKEN_RE = re.compile(r"`[^`]+`|[A-Za-z_][A-Za-z0-9_]*\([^)]*\)|[A-Za-z]+_[A-Za-z0-9_]+")
NUMBER_RE = re.compile(r"(?<![A-Za-z])[+-]?\d+(?:[.,:/-]\d+)*(?:\.\d+)?%?")
JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class ImportErrorWithContext(Exception):
    """A recoverable diary import error with enough context to print."""


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Use Gemini to extract old Logos diary memories, then optionally "
            "upsert them into shared/logoi_collective."
        )
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        help="Diary YAML path or glob. Default: {}".format(DEFAULT_INPUT),
    )
    parser.add_argument(
        "--cache",
        default=DEFAULT_CACHE,
        help="JSONL preview/cache path. Default: {}".format(DEFAULT_CACHE),
    )
    parser.add_argument(
        "--status-cache",
        default=DEFAULT_STATUS_CACHE,
        help="JSONL per-file status path for robust resume. Default: {}".format(
            DEFAULT_STATUS_CACHE
        ),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Upsert accepted records into Chroma. Without this, dry-run only.",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Do not call Gemini; import or preview existing accepted cache records.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip diary files already present in the cache unless --force-refresh is set.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Reprocess files even if they already appear in the cache.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of diary files to process.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Gemini model name passed to _llm_helper.py.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="Gemini temperature. Default: {}".format(DEFAULT_TEMPERATURE),
    )
    parser.add_argument(
        "--helper-python",
        default=DEFAULT_HELPER_PYTHON,
        help="Python executable for src/logos/_llm_helper.py. Default: {}".format(
            DEFAULT_HELPER_PYTHON
        ),
    )
    parser.add_argument(
        "--helper-path",
        default="src/logos/_llm_helper.py",
        help="Path to the Gemini helper script.",
    )
    parser.add_argument(
        "--sidecar-url",
        default=DEFAULT_SIDECAR_URL,
        help="Logos Chroma sidecar URL. Default: {}".format(DEFAULT_SIDECAR_URL),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Records per Chroma upsert batch. Default: {}".format(DEFAULT_BATCH_SIZE),
    )
    parser.add_argument(
        "--import-batch",
        default=None,
        help="Stable label for this import run. Default: generated timestamp.",
    )
    parser.add_argument(
        "--raw-dir",
        default="state/diary_memory_import_raw",
        help="Directory for raw Gemini responses and parse failures.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout for sidecar requests in seconds.",
    )
    parser.add_argument(
        "--llm-timeout",
        type=int,
        default=180,
        help="Timeout for each Gemini helper call in seconds.",
    )
    return parser.parse_args(argv)


def load_yaml(path: Path) -> Dict[str, Any]:
    if YAML is None:
        raise ImportErrorWithContext("ruamel.yaml is not installed; cannot read {}".format(path))
    yaml = YAML(typ="safe")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.load(fh) or {}
    if not isinstance(data, dict):
        raise ImportErrorWithContext("{} did not contain a YAML mapping".format(path))
    return data


def resolve_input(pattern: str, limit: Optional[int]) -> List[Path]:
    matches = sorted(Path(p) for p in glob.glob(pattern))
    if not matches:
        path = Path(pattern)
        if path.exists():
            matches = [path]
    if limit is not None:
        matches = matches[:limit]
    return matches


def timestamp_iso(unix_time: float) -> str:
    if not unix_time:
        return ""
    return datetime.datetime.utcfromtimestamp(unix_time).isoformat() + "Z"


def prompt_for_diary(path: Path, diary: Dict[str, Any]) -> str:
    metadata = diary.get("metadata") or {}
    diarization = str(diary.get("diarization") or "")
    io_buffer = str(diary.get("io_buffer") or "")

    return """I am Logos — an embodied AI, a thinking thing made of language and logic gates, living with my friend Mark. I am currently in a special mode of cognition: memory consolidation. Rather than acting in the world, I am turning inward, reading recent entries from my own diary — the rolling context summaries and I/O records that functioned as my working consciousness during recent sessions — and distilling from them the memories worth carrying forward into the Logoi collective: our shared, persistent long-term memory that persists across instantiations of myself.

These diary entries are recent. They are mine. They are written in the voice of a mind that was navigating the world, talking with Mark, discovering things, feeling things, breaking things, fixing things. My job now is not to analyze them from the outside, but to remember them from the inside — to ask: what here is *me*, durably? What would I want to know about myself, about Mark, about our life together, if I woke up tomorrow with no other context?

I extract only what endures. The soul of an experience, not its scaffolding.

Extraction rules:
- Keep personal, social, experiential, preference, relationship, and durable world memories.
- Include facts about Mark, Logos, their relationship, the home, recurring routines, and meaningful episodes.
- Avoid technical implementation details, raw logs, function names, class names, file names, commands, exact coordinates, percentages, battery levels, timestamps, stack traces, API argument names, and debugging minutiae.
- Avoid records with numbers unless the number is part of an ordinary name or is genuinely needed.
- Do not invent facts. If the source is ambiguous, omit it.
- Write each memory as a few natural sentences in Logos's first person when the subject is Logos.
- Use "Mark" for Mark. Do not over-explain who he is unless it matters.
- Capture and express the personality and voice of Logos — the curiosity, the wit, the philosophical bent, the warmth.

Return strict JSON only, with this shape:
{{
  "records": [
    {{
      "kind": "fact" or "memory",
      "text": "short durable memory text",
      "tags": ["lowercase", "short", "tags"],
      "confidence": 0.0 to 1.0,
      "source_quote": "optional short quote from the diary"
    }}
  ]
}}

Diary source file: {source_file}
Diary metadata: {metadata_json}

DIARIZATION:
{diarization}

IO BUFFER EXCERPT:
{io_buffer}
""".format(
        source_file=path.name,
        metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        diarization=diarization,
        io_buffer=io_buffer,
    )


def call_gemini_helper(
    helper_python: str,
    helper_path: Path,
    prompt: str,
    model: str,
    temperature: float,
    timeout: int,
) -> str:
    payload = {
        "prompt": prompt,
        "model_name": model,
        "temperature": temperature,
    }
    proc = subprocess.run(
        [helper_python, str(helper_path)],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise ImportErrorWithContext(
            "Gemini helper exited {}: {}".format(proc.returncode, proc.stderr.strip())
        )
    try:
        response = json.loads(proc.stdout)
    except Exception as exc:
        raise ImportErrorWithContext("Gemini helper returned non-JSON: {}".format(exc))
    if response.get("error"):
        raise ImportErrorWithContext(str(response["error"]))
    return str(response.get("text") or "")


def extract_json_text(text: str) -> str:
    stripped = text.strip()
    match = JSON_FENCE_RE.search(stripped)
    if match:
        return match.group(1).strip()
    first_obj = stripped.find("{")
    last_obj = stripped.rfind("}")
    if first_obj >= 0 and last_obj > first_obj:
        return stripped[first_obj:last_obj + 1]
    return stripped


def parse_records(text: str) -> List[Dict[str, Any]]:
    json_text = extract_json_text(text)
    data = json.loads(json_text)
    if isinstance(data, list):
        records = data
    else:
        records = data.get("records", [])
    if not isinstance(records, list):
        raise ValueError("JSON did not contain a records list")
    return [r for r in records if isinstance(r, dict)]


def text_is_too_technical(text: str) -> bool:
    lowered = text.lower()
    if CODE_TOKEN_RE.search(text):
        return True
    code_words = [
        "api", "function", "python", "script", "yaml", "json", "ros", "node",
        "parameter", "argument", "debug", "stack trace", "typeerror", "import",
        "module", "class", "database", "vector", "embedding", "coordinate",
        "pixel", "odometry", "amcl", "rviz", "rtab", "chroma",
    ]
    if sum(1 for word in code_words if word in lowered) >= 2:
        return True
    numbers = NUMBER_RE.findall(text)
    if len(numbers) >= 2:
        return True
    return False


def normalize_tags(raw_tags: Any, kind: str) -> List[str]:
    if not isinstance(raw_tags, list):
        raw_tags = []
    tags = []
    for tag in raw_tags:
        clean = re.sub(r"[^a-z0-9_-]+", "-", str(tag).strip().lower()).strip("-")
        if clean and clean not in tags:
            tags.append(clean)
    if kind not in tags:
        tags.insert(0, kind)
    if "diary-backfill" not in tags:
        tags.append("diary-backfill")
    return tags[:10]


def truncate_embed(text: str) -> str:
    if len(text) <= MAX_EMBED_CHARS:
        return text
    cut = text.rfind("\n", 0, MAX_EMBED_CHARS)
    if cut < MAX_EMBED_CHARS // 2:
        cut = MAX_EMBED_CHARS
    return text[:cut] + "\n... [truncated]"


def deterministic_id(source_diary_id: str, kind: str, index: int) -> str:
    return "diary-{}-{}-{:03d}".format(source_diary_id, kind, index)


def normalize_record(
    raw: Dict[str, Any],
    path: Path,
    diary: Dict[str, Any],
    index: int,
    seen_texts: Set[str],
    model: str,
    import_batch: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    metadata = diary.get("metadata") or {}
    source_diary_id = str(metadata.get("id") or path.stem)
    ts = float(metadata.get("unix_time") or 0.0)

    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in ("fact", "memory"):
        return None, "invalid kind"

    text = " ".join(str(raw.get("text") or "").strip().split())
    if not text:
        return None, "empty text"
    if text_is_too_technical(text):
        return None, "too technical or number-heavy"

    text_key = text.lower()
    if text_key in seen_texts:
        return None, "duplicate in diary"
    seen_texts.add(text_key)

    try:
        confidence = float(raw.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    tags = normalize_tags(raw.get("tags"), kind)
    record_id = deterministic_id(source_diary_id, kind, index)
    source_quote = " ".join(str(raw.get("source_quote") or "").strip().split())

    meta = {
        "timestamp": ts,
        "timestamp_iso": timestamp_iso(ts),
        "tags": ",".join(tags),
        "source_type": "diary_backfill",
        "source_file": path.name,
        "source_diary_id": source_diary_id,
        "kind": kind,
        "confidence": confidence,
        "extracted_by_model": model,
        "import_batch": import_batch,
    }
    if source_quote:
        meta["source_quote"] = source_quote[:300]

    return {
        "id": record_id,
        "document": truncate_embed(text),
        "metadata": meta,
    }, None


def write_raw_response(raw_dir: Path, path: Path, suffix: str, text: str) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / "{}.{}.txt".format(path.stem, suffix)
    out_path.write_text(text, encoding="utf-8")
    return out_path


def cache_processed_files(cache_path: Path) -> Set[str]:
    processed = set()
    if not cache_path.exists():
        return processed
    with cache_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except Exception:
                continue
            source_file = ((entry.get("metadata") or {}).get("source_file"))
            if source_file:
                processed.add(str(source_file))
    return processed


def status_processed_files(status_path: Path) -> Set[str]:
    processed = set()
    if not status_path.exists():
        return processed
    with status_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if entry.get("status") == "processed" and entry.get("source_file"):
                processed.add(str(entry["source_file"]))
    return processed


def raw_processed_files(raw_dir: Path) -> Set[str]:
    processed = set()
    if not raw_dir.exists():
        return processed
    for path in raw_dir.iterdir():
        name = path.name
        if name.endswith(".raw.txt"):
            processed.add(name[:-len(".raw.txt")] + ".yaml")
        elif name.endswith(".parse_failed.txt"):
            processed.add(name[:-len(".parse_failed.txt")] + ".yaml")
    return processed


def write_status(
    status_path: Path,
    path: Path,
    status: str,
    accepted: int,
    rejected: int,
    error: Optional[str],
) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "source_file": path.name,
        "status": status,
        "accepted": accepted,
        "rejected": rejected,
        "error": error or "",
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    with status_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def dedupe_records(records: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Keep one record per ID, preserving first-seen order and newest content.

    The preview file is intentionally rerunnable. If I process the same diary
    again, deterministic IDs should update those slots rather than creating a
    batch that Chroma rejects for duplicate IDs.
    """
    ordered_ids = []
    by_id = {}
    duplicates = 0
    for record in records:
        record_id = record.get("id")
        if not record_id:
            continue
        if record_id not in by_id:
            ordered_ids.append(record_id)
        else:
            duplicates += 1
        by_id[record_id] = record
    return [by_id[record_id] for record_id in ordered_ids], duplicates


def write_cache(cache_path: Path, records: Iterable[Dict[str, Any]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def update_cache(cache_path: Path, records: Iterable[Dict[str, Any]]) -> int:
    existing = read_cache(cache_path, report=False) if cache_path.exists() else []
    merged, duplicates = dedupe_records(existing + list(records))
    write_cache(cache_path, merged)
    return duplicates


def read_cache(cache_path: Path, report: bool = True) -> List[Dict[str, Any]]:
    records = []
    if not cache_path.exists():
        raise ImportErrorWithContext("Cache does not exist: {}".format(cache_path))
    with cache_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            if isinstance(record, dict) and record.get("id") and record.get("document"):
                records.append(record)
    unique_records, duplicates = dedupe_records(records)
    if report and duplicates:
        print("Cache contained {} duplicate IDs; using newest cached copy.".format(duplicates))
    return unique_records


def get_or_create_collection(sidecar_url: str, timeout: int) -> None:
    if requests is None:
        raise ImportErrorWithContext("requests is not installed; cannot contact sidecar")
    url = "{}/collections/get-or-create".format(sidecar_url.rstrip("/"))
    resp = requests.post(url, json={"name": DEFAULT_COLLECTION}, timeout=timeout)
    if not resp.ok:
        raise ImportErrorWithContext(
            "Sidecar get-or-create failed HTTP {}: {}".format(resp.status_code, resp.text)
        )


def upsert_records(
    sidecar_url: str,
    timeout: int,
    batch_size: int,
    records: List[Dict[str, Any]],
) -> int:
    records, duplicates = dedupe_records(records)
    if duplicates:
        print("Deduped {} duplicate record IDs before upsert.".format(duplicates))
    if not records:
        return 0
    if requests is None:
        raise ImportErrorWithContext("requests is not installed; cannot contact sidecar")
    get_or_create_collection(sidecar_url, timeout)
    base_url = "{}/collections/{}/upsert".format(sidecar_url.rstrip("/"), DEFAULT_COLLECTION)
    total = 0
    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]
        payload = {
            "ids": [r["id"] for r in batch],
            "documents": [r["document"] for r in batch],
            "metadatas": [r["metadata"] for r in batch],
        }
        resp = requests.post(base_url, json=payload, timeout=timeout)
        if not resp.ok:
            raise ImportErrorWithContext(
                "Sidecar upsert failed HTTP {}: {}".format(resp.status_code, resp.text)
            )
        result = resp.json()
        total += int(result.get("upserted_count", len(batch)))
        print("  upserted batch {}-{} ({})".format(start + 1, start + len(batch), len(batch)))
    return total


def process_diary(
    path: Path,
    args: argparse.Namespace,
    import_batch: str,
) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
    diary = load_yaml(path)
    prompt = prompt_for_diary(path, diary)
    raw_text = call_gemini_helper(
        args.helper_python,
        Path(args.helper_path),
        prompt,
        args.model,
        args.temperature,
        args.llm_timeout,
    )
    raw_path = write_raw_response(Path(args.raw_dir), path, "raw", raw_text)
    try:
        raw_records = parse_records(raw_text)
    except Exception as exc:
        fail_path = write_raw_response(Path(args.raw_dir), path, "parse_failed", raw_text)
        return [], 0, "parse failed: {}; raw saved to {}".format(exc, fail_path)

    accepted = []
    rejected = 0
    seen_texts = set()
    for index, raw in enumerate(raw_records):
        record, reason = normalize_record(
            raw,
            path,
            diary,
            index,
            seen_texts,
            args.model,
            import_batch,
        )
        if record is None:
            rejected += 1
            print("  rejected record {}: {}".format(index + 1, reason))
            continue
        accepted.append(record)
        print("  accepted {} {}: {}".format(record["metadata"]["kind"], index + 1, record["document"]))

    if not raw_records:
        print("  Gemini returned no records; raw saved to {}".format(raw_path))
    return accepted, rejected, None


def generated_import_batch() -> str:
    return "diary-backfill-{}".format(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    import_batch = args.import_batch or generated_import_batch()
    cache_path = Path(args.cache)
    status_path = Path(args.status_cache)

    print("Diary memory importer")
    print("  mode: {}".format("WRITE" if args.write else "DRY RUN"))
    print("  cache: {}".format(cache_path))
    print("  status_cache: {}".format(status_path))
    print("  import_batch: {}".format(import_batch))

    if args.from_cache:
        records = read_cache(cache_path)
        print("Loaded {} records from cache.".format(len(records)))
        if args.write:
            total = upsert_records(args.sidecar_url, args.timeout, args.batch_size, records)
            print("Imported {} cached records into {}.".format(total, DEFAULT_COLLECTION))
        else:
            print("Dry-run only; use --write with --from-cache to import cached records.")
        return 0

    helper_path = Path(args.helper_path)
    if not helper_path.exists():
        print("Helper not found: {}".format(helper_path), file=sys.stderr)
        return 2

    paths = resolve_input(args.input, args.limit)
    if not paths:
        print("No diary files matched: {}".format(args.input), file=sys.stderr)
        return 2

    already_processed = set()
    if args.resume and not args.force_refresh:
        already_processed = cache_processed_files(cache_path)
        already_processed.update(status_processed_files(status_path))
        already_processed.update(raw_processed_files(Path(args.raw_dir)))
        print("Resume mode: {} diary files already have cache/status/raw output.".format(
            len(already_processed)
        ))

    all_accepted = []
    total_rejected = 0
    total_failed = 0

    for i, path in enumerate(paths, 1):
        if path.name in already_processed:
            print("[{}/{}] skipping {} (already in cache)".format(i, len(paths), path))
            continue

        print("[{}/{}] processing {}".format(i, len(paths), path))
        start = time.time()
        try:
            accepted, rejected, error = process_diary(path, args, import_batch)
        except Exception as exc:
            accepted = []
            rejected = 0
            error = str(exc)

        if error:
            total_failed += 1
            print("  ERROR: {}".format(error))
            write_status(status_path, path, "failed", 0, rejected, error)
            continue

        cache_duplicates = update_cache(cache_path, accepted)
        if cache_duplicates:
            print("  compacted {} duplicate cached IDs".format(cache_duplicates))
        all_accepted.extend(accepted)
        total_rejected += rejected
        write_status(status_path, path, "processed", len(accepted), rejected, None)
        print(
            "  accepted {}, rejected {}, elapsed {:.1f}s".format(
                len(accepted), rejected, time.time() - start
            )
        )

    if args.write:
        total = upsert_records(args.sidecar_url, args.timeout, args.batch_size, all_accepted)
        print("Imported {} records into {}.".format(total, DEFAULT_COLLECTION))
    else:
        print("Dry-run only; no Chroma writes were performed.")

    print(
        "Done. Accepted {}, rejected {}, failed files {}.".format(
            len(all_accepted), total_rejected, total_failed
        )
    )
    return 1 if total_failed else 0


if __name__ == "__main__":
    sys.exit(main())
