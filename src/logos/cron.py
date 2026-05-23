# src/logos/cron.py

"""
I use this module to define, manage, and execute my own scheduled cron jobs — Python snippets
that fire automatically at scheduled times, with no human required to trigger them.

Each job writes to stdout, which the framework's permanent stdout capture delivers as a
py_async result. The job can set loop_cognition = True to kick off a new cognition cycle.
The minimum firing interval for recurring jobs is 30 minutes, enforced at upsert time.
"""

import datetime
import threading
from pathlib import Path
from ruamel.yaml import YAML
from typing import Dict, List, Optional
from .core import Verbosity, api_call

__all__ = ["show", "upsert", "remove", "enable", "disable", "run_now"]


yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)

WORKSPACE_PATH = Path.cwd()
CONFIG_PATH = WORKSPACE_PATH / "config"
CRON_CONFIG_PATH = CONFIG_PATH / "cron_jobs.yaml"

_config_lock = threading.Lock()
_last_fired = {}      # type: Dict[str, str]  — job name -> "YYYY-MM-DD HH:MM"
_cron_stop_event = threading.Event()
_interpreter_globals = None  # type: Optional[dict]


# --- Interpreter binding ---

def _bind(globals_dict: dict) -> None:
    """Stores a reference to the interpreter's globals so jobs can set loop_cognition.

    I call this from py_env_preload.py with globals(), which is interpreter.locals
    in that execution context. After binding, loop_cognition set by a cron job's code
    is forwarded into the right place for the framework's poll timer to pick up.
    Called again on every interpreter reset to keep the reference fresh.

    Args:
        globals_dict: The interpreter's live globals dict (globals() from preload context).
    """
    global _interpreter_globals
    _interpreter_globals = globals_dict


# --- Config I/O ---

def _load_jobs() -> List[dict]:
    """Loads the list of cron job dicts from config/cron_jobs.yaml."""
    if not CRON_CONFIG_PATH.exists():
        return []
    with open(CRON_CONFIG_PATH, 'r') as f:
        jobs = yaml.load(f)
    return jobs or []


def _save_jobs(jobs: List[dict]) -> None:
    """Writes the list of cron job dicts to config/cron_jobs.yaml."""
    with open(CRON_CONFIG_PATH, 'w') as f:
        yaml.dump(jobs, f)


# --- Schedule matching ---

def _field_matches(value: int, field_str: str) -> bool:
    """Returns True if an integer value satisfies a single cron field expression.

    Handles: * (wildcard), n (exact), a-b (range), */n (step), a,b,c (list),
    and combinations thereof via comma-splitting.

    Args:
        value: The integer to test (e.g. current minute, hour, etc.).
        field_str: The cron field string to match against.
    """
    field_str = str(field_str).strip()
    if field_str == '*':
        return True

    for token in field_str.split(','):
        token = token.strip()
        if '/' in token:
            parts = token.split('/', 1)
            step = int(parts[1])
            start = 0 if parts[0] == '*' else int(parts[0])
            if value >= start and (value - start) % step == 0:
                return True
        elif '-' in token:
            lo, hi = token.split('-', 1)
            if int(lo) <= value <= int(hi):
                return True
        else:
            if value == int(token):
                return True
    return False


def _schedule_matches(schedule_str: str, dt: datetime.datetime) -> bool:
    """Returns True if a datetime matches a 5-field cron expression.

    Field order: minute hour day-of-month month day-of-week.
    Day-of-week uses cron convention: 0=Sunday, 1=Monday … 6=Saturday.

    Args:
        schedule_str: A 5-field cron expression string.
        dt: The datetime to test against it.
    """
    try:
        fields = schedule_str.strip().split()
        if len(fields) != 5:
            return False
        minute_f, hour_f, dom_f, month_f, dow_f = fields
        # Python weekday(): 0=Monday … 6=Sunday → cron: 0=Sunday, 1=Monday … 6=Saturday
        dow = (dt.weekday() + 1) % 7
        return (
            _field_matches(dt.minute, minute_f)
            and _field_matches(dt.hour, hour_f)
            and _field_matches(dt.day, dom_f)
            and _field_matches(dt.month, month_f)
            and _field_matches(dow, dow_f)
        )
    except (ValueError, AttributeError):
        return False


def _validate_schedule_frequency(schedule_str: str) -> Optional[str]:
    """Returns None if the schedule is acceptable, or an error string if it fires too often.

    I simulate one week of minutes (10,080 total) and find the minimum gap between
    consecutive firings. Schedules with any gap under 30 minutes are rejected.
    Schedules that fire at most once in the simulation window (≤1 match) are always
    allowed — they represent rare or one-shot-style timings.

    Args:
        schedule_str: The 5-field cron expression to validate.

    Returns:
        None if the schedule is acceptable; a descriptive error string if not.
    """
    base = datetime.datetime(2024, 1, 1, 0, 0)  # A known Monday
    matches = []
    for offset in range(10080):  # 7 * 24 * 60
        t = base + datetime.timedelta(minutes=offset)
        if _schedule_matches(schedule_str, t):
            matches.append(offset)

    if len(matches) < 2:
        return None  # Fires at most once per week — always fine

    min_gap = min(matches[i + 1] - matches[i] for i in range(len(matches) - 1))
    # Check the wrap-around gap (end of week back to start)
    wrap_gap = (10080 - matches[-1]) + matches[0]
    min_gap = min(min_gap, wrap_gap)

    if min_gap < 30:
        return (
            "Schedule '{}' would fire every ~{} minute(s), which is more often than the "
            "30-minute minimum for recurring jobs. Try a less frequent schedule "
            "(e.g., '*/30 * * * *' for every 30 min, or '0 * * * *' for hourly).".format(
                schedule_str, min_gap
            )
        )
    return None


# --- Job execution ---

def _exec_job(job: dict) -> None:
    """Executes a single cron job's code snippet.

    I run the code in a copy of the interpreter's globals namespace so it has access to
    logos, skills, and all standard preloads. Output goes straight to stdout, which the
    framework captures from all threads. If the code sets loop_cognition, I forward that
    into the real interpreter globals so the framework's poll timer picks it up.

    Args:
        job: The job dict from cron_jobs.yaml, must contain at least 'name' and 'code'.
    """
    name = job.get('name', 'unknown')
    code = job.get('code', '').strip()
    if not code:
        return

    print("\n--- cron: {} ---".format(name))

    # Build an exec namespace. If we're bound to the interpreter, copy its live globals
    # so the job sees logos, skills, and all standard preloads just like a py block.
    if _interpreter_globals is not None:
        exec_globals = dict(_interpreter_globals)
    else:
        import builtins
        exec_globals = {'__builtins__': builtins}
        try:
            import logos as _logos  # noqa: F401
            exec_globals['logos'] = _logos
        except ImportError:
            pass
        try:
            import skills as _skills  # noqa: F401
            exec_globals['skills'] = _skills
        except ImportError:
            pass

    exec_locals = {}  # type: dict
    try:
        exec(compile(code, '<cron:{}>'.format(name), 'exec'), exec_globals, exec_locals)
    except Exception as e:
        import traceback as _tb
        print("[cron:{}] Execution error: {}".format(name, e))
        _tb.print_exc()

    # Forward loop_cognition into the interpreter's live globals dict so the framework
    # poll timer can honor it when it publishes this output as a py_async result.
    if 'loop_cognition' in exec_locals and _interpreter_globals is not None:
        _interpreter_globals['loop_cognition'] = exec_locals['loop_cognition']


# --- Background scheduler thread ---

def _cron_loop() -> None:
    """Background daemon thread body: wakes at each minute boundary and fires due jobs.

    I sleep to the next minute boundary rather than sleeping a flat 60 seconds,
    preventing drift over time. I reload the config file on every tick so any jobs
    I add or modify via upsert() are picked up without a restart.
    """
    while not _cron_stop_event.is_set():
        now = datetime.datetime.now()
        sleep_secs = 60.0 - now.second - now.microsecond / 1_000_000.0
        if sleep_secs < 0.5:
            sleep_secs += 60.0
        if _cron_stop_event.wait(timeout=sleep_secs):
            break

        now = datetime.datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")

        try:
            with _config_lock:
                jobs = _load_jobs()
        except Exception:
            continue

        for job in jobs:
            if not job.get('enabled', False):
                continue
            name = job.get('name', '')
            schedule = job.get('schedule', '')

            if _last_fired.get(name) == minute_key:
                continue  # Already fired this minute (e.g. thread woke slightly late)

            if _schedule_matches(schedule, now):
                _last_fired[name] = minute_key
                _exec_job(job)


_cron_thread = threading.Thread(target=_cron_loop, name="logos-cron", daemon=True)
_cron_thread.start()


# --- Public API ---

def show() -> str:
    """Returns a formatted summary of all cron jobs, without their code bodies.

    I list each job's name, enabled state, schedule, and description — enough to
    audit what's scheduled at a glance. To inspect or edit a job's code, read
    config/cron_jobs.yaml directly.

    Returns:
        A formatted string ready to print.

    Note to self:
        Follow up with logos.cron.run_now(name) to test a job immediately without
        waiting for its scheduled time.
    """
    with _config_lock:
        jobs = _load_jobs()

    lines = ["# Cron Jobs  (config/cron_jobs.yaml)"]
    if not jobs:
        lines.append("  (none — use logos.cron.upsert() to create one)")
        return "\n".join(lines)

    for job in jobs:
        name = job.get('name', 'unnamed')
        schedule = job.get('schedule', '?')
        enabled = job.get('enabled', False)
        desc = job.get('description', 'No description.')
        status = 'enabled' if enabled else 'disabled'
        lines.append("- {} [{}] ({}): {}".format(name, status, schedule, desc))

    return "\n".join(lines)


@api_call(default_verbosity=Verbosity.ACK)
def upsert(
    name: str,
    schedule: Optional[str] = None,
    description: Optional[str] = None,
    enabled: Optional[bool] = None,
    code: Optional[str] = None,
) -> None:
    """Creates a new cron job or updates fields of an existing one.

    Schedules that fire more often than every 30 minutes are rejected with a warning.
    Schedules that match at most once per week (e.g. a specific date/time) are always
    accepted, making this safe for one-shot timers too.

    Args:
        name: Unique job identifier used as the key for update-or-create.
        schedule: 5-field cron expression, e.g. '0 9 * * *' for 9:00 AM daily.
            Fields: minute hour day-of-month month day-of-week.
            Supports: * (any), integers, a-b (range), */n (step), a,b (list).
        description: Human-readable note about what this job does.
        enabled: Whether the job fires. Defaults to True for new jobs.
        code: Python snippet executed at schedule time. Required for new jobs.
            Has access to logos, skills, and all standard preloads. Can set
            loop_cognition = True to trigger a new cognition cycle.

    Note to self:
        After creating a job, use logos.cron.run_now(name) to test it immediately.
    """
    if schedule is not None:
        fields = schedule.strip().split()
        if len(fields) != 5:
            print("Invalid schedule '{}': expected 5 fields (minute hour dom month dow), "
                  "got {}.".format(schedule, len(fields)))
            return
        freq_error = _validate_schedule_frequency(schedule)
        if freq_error is not None:
            print("Rejected: " + freq_error)
            return

    updates = {}
    if schedule is not None:
        updates['schedule'] = schedule
    if description is not None:
        updates['description'] = description
    if enabled is not None:
        updates['enabled'] = enabled
    if code is not None:
        updates['code'] = code

    with _config_lock:
        jobs = _load_jobs()
        target = next((j for j in jobs if j.get('name') == name), None)

        if target is not None:
            if not updates:
                print("No updates provided for job '{}'.".format(name))
                return
            target.update(updates)
            print("Cron job '{}' updated.".format(name))
        else:
            if code is None:
                print("'code' is required when creating a new cron job.")
                return
            if schedule is None:
                print("'schedule' is required when creating a new cron job.")
                return
            jobs.append({
                'name': name,
                'schedule': schedule,
                'description': description or '',
                'enabled': True if enabled is None else enabled,
                'code': code,
            })
            print("Cron job '{}' created.".format(name))

        _save_jobs(jobs)


@api_call(default_verbosity=Verbosity.ACK)
def remove(name: str) -> None:
    """Permanently removes a cron job from config/cron_jobs.yaml.

    Args:
        name: The unique name of the job to remove.

    Note to self:
        This cannot be undone. If I might want this job back, consider disable() instead.
    """
    with _config_lock:
        jobs = _load_jobs()
        original_count = len(jobs)
        jobs = [j for j in jobs if j.get('name') != name]
        if len(jobs) < original_count:
            _save_jobs(jobs)
            print("Cron job '{}' removed.".format(name))
        else:
            print("Cron job '{}' not found.".format(name))


@api_call(default_verbosity=Verbosity.ACK)
def enable(name: str) -> None:
    """Enables a cron job so it fires at its scheduled time.

    Args:
        name: The unique name of the job to enable.
    """
    with _config_lock:
        jobs = _load_jobs()
        target = next((j for j in jobs if j.get('name') == name), None)
        if target is None:
            print("Cron job '{}' not found.".format(name))
            return
        if target.get('enabled'):
            print("Cron job '{}' is already enabled.".format(name))
            return
        target['enabled'] = True
        _save_jobs(jobs)
    print("Cron job '{}' enabled.".format(name))


@api_call(default_verbosity=Verbosity.ACK)
def disable(name: str) -> None:
    """Disables a cron job without removing it from the config.

    Args:
        name: The unique name of the job to disable.

    Note to self:
        The job's definition is preserved in config/cron_jobs.yaml. Re-enable with enable().
    """
    with _config_lock:
        jobs = _load_jobs()
        target = next((j for j in jobs if j.get('name') == name), None)
        if target is None:
            print("Cron job '{}' not found.".format(name))
            return
        if not target.get('enabled'):
            print("Cron job '{}' is already disabled.".format(name))
            return
        target['enabled'] = False
        _save_jobs(jobs)
    print("Cron job '{}' disabled.".format(name))


@api_call(default_verbosity=Verbosity.ACK)
def run_now(name: str) -> None:
    """Immediately executes a cron job, regardless of its schedule or enabled state.

    Useful for testing a newly created job without waiting for its scheduled time.
    Does not update the last-fired record, so the job will still fire at its
    regularly scheduled time if it is enabled.

    Args:
        name: The unique name of the job to execute immediately.
    """
    with _config_lock:
        jobs = _load_jobs()
    target = next((j for j in jobs if j.get('name') == name), None)
    if target is None:
        print("Cron job '{}' not found.".format(name))
        return
    _exec_job(target)
