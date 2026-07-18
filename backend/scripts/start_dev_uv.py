#!/usr/bin/env python3
"""Start the local backend development stack from the locked uv environment."""
import argparse
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import psutil
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent
REPO_ROOT = BACKEND_ROOT  # Backward-compatible name used by focused launcher tests.


def _load_project_environment() -> bool:
    """Load the public root environment without overriding explicit process values."""

    return load_dotenv(PROJECT_ROOT / ".env", override=False)


_load_project_environment()


# -----------------------------
# Proxy helper: compose NO_PROXY
# -----------------------------
def _build_env_with_no_proxy(extra_hosts=None):
    """Return env copy with minimally-augmented NO_PROXY.

    - Non-intrusive: only ensures localhost entries are present.
    - Supplier-agnostic: does NOT hardcode vendor domains.
    - Optional: users may append more domains via BYPASS_PROXY_DOMAINS.
    """
    env = os.environ.copy()

    # Default bypass list (merge without duplicates)
    defaults = ["localhost", "127.0.0.1", "::1"]

    # User-provided domains to bypass (optional)
    user_extra = env.get("BYPASS_PROXY_DOMAINS", "")
    user_list = [x.strip() for x in user_extra.split(",") if x.strip()]

    # Call-site extra
    extra_list = extra_hosts or []

    existing_no_proxy = env.get("NO_PROXY") or env.get("no_proxy") or ""
    existing_list = [x.strip() for x in existing_no_proxy.split(",") if x.strip()]

    merged = []
    for host in existing_list + defaults + user_list + extra_list:
        if host and host not in merged:
            merged.append(host)

    merged_value = ",".join(merged)
    env["NO_PROXY"] = merged_value
    env["no_proxy"] = merged_value
    return env


# Add the backend directory to Python path for launcher-owned lazy application imports.
sys.path.insert(0, str(BACKEND_ROOT))

_API_COMMAND_TOKEN = "uvicorn app.main:app"
_WATCHDOG_COMMAND_TOKEN = "watchmedo auto-restart"
_WORKER_COMMAND_TOKEN = "celery -A app.services.celery_app worker"
_BEAT_COMMAND_TOKEN = "celery -A app.services.celery_app beat"
_PORT_PATTERN = re.compile(r"--port\s+(\d+)")
_LABEL_PRIORITY = {
    "api_server": 0,
    "celery_worker_watchdog": 1,
    "celery_worker": 2,
    "celery_beat": 3,
}


@dataclass(frozen=True)
class ManagedProcessGroup:
    label: str
    pgid: int
    pids: tuple[int, ...]
    commands: tuple[str, ...]
    cwd: str
    port: str | None = None


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Start the local MuseCraft backend dev stack.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate external dependencies and apply migrations without starting services.",
    )
    parser.add_argument(
        "--cleanup-residuals",
        action="store_true",
        help="Stop repo-local managed uvicorn/celery residuals before starting if they are detected.",
    )
    return parser.parse_args(argv)


def _detect_managed_label(command: str) -> str | None:
    if _WATCHDOG_COMMAND_TOKEN in command and _WORKER_COMMAND_TOKEN in command:
        return "celery_worker_watchdog"
    if _API_COMMAND_TOKEN in command:
        return "api_server"
    if _WORKER_COMMAND_TOKEN in command:
        return "celery_worker"
    if _BEAT_COMMAND_TOKEN in command:
        return "celery_beat"
    return None


def _extract_port(command: str) -> str | None:
    match = _PORT_PATTERN.search(command)
    return match.group(1) if match else None


def _select_group_label(labels: set[str]) -> str:
    return min(labels, key=lambda label: (_LABEL_PRIORITY.get(label, 999), label))


def _collect_repo_managed_process_groups(repo_root: Path) -> list[ManagedProcessGroup]:
    repo_root = repo_root.resolve()
    grouped: dict[int, dict] = {}
    for process in psutil.process_iter(["pid", "cmdline", "cwd"]):
        try:
            pid = int(process.info["pid"])
            command = " ".join(process.info.get("cmdline") or ())
            cwd_value = process.info.get("cwd")
        except (psutil.Error, TypeError, ValueError):
            continue

        label = _detect_managed_label(command)
        if label is None or not cwd_value:
            continue

        try:
            cwd = Path(cwd_value).resolve()
            cwd.relative_to(repo_root)
        except (OSError, ValueError):
            continue

        if _is_windows():
            group_id = pid
        else:
            try:
                group_id = os.getpgid(pid)
            except (OSError, ProcessLookupError):
                continue

        entry = grouped.setdefault(
            group_id,
            {
                "labels": set(),
                "pids": [],
                "commands": [],
                "cwd": str(cwd),
                "port": None,
            },
        )
        entry["labels"].add(label)
        entry["pids"].append(pid)
        entry["commands"].append(command)
        entry["port"] = entry["port"] or _extract_port(command)

    groups = [
        ManagedProcessGroup(
            label=_select_group_label(entry["labels"]),
            pgid=group_id,
            pids=tuple(sorted(entry["pids"])),
            commands=tuple(entry["commands"]),
            cwd=entry["cwd"],
            port=entry["port"],
        )
        for group_id, entry in grouped.items()
    ]
    return sorted(groups, key=lambda group: (_LABEL_PRIORITY.get(group.label, 999), group.pgid))


def _print_managed_process_groups(groups: list[ManagedProcessGroup], *, action_hint: str) -> None:
    print("Detected repo-local managed service residuals:")
    for group in groups:
        port_bits = f" port={group.port}" if group.port else ""
        group_label = "pid" if _is_windows() else "pgid"
        print(f"  - label={group.label} {group_label}={group.pgid}{port_bits}")
        print(f"    pids: {', '.join(str(pid) for pid in group.pids)}")
        print(f"    cwd: {group.cwd}")
        print(f"    command: {group.commands[0]}")
        print(f"    recommended action: {action_hint}")


def _is_windows() -> bool:
    return os.name == "nt"


def _process_group_alive(pgid: int) -> bool:
    if _is_windows():
        return psutil.pid_exists(pgid)
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(pgid: int, *, label: str, wait_timeout: float = 5.0) -> bool:
    if _is_windows():
        try:
            root = psutil.Process(pgid)
            processes = root.children(recursive=True) + [root]
        except psutil.NoSuchProcess:
            return True
        except psutil.Error as exc:
            print(f"[warning] Failed to inspect {label} pid={pgid}: {exc}")
            return False

        for process in reversed(processes):
            try:
                process.terminate()
            except psutil.NoSuchProcess:
                continue
            except psutil.Error as exc:
                print(f"[warning] Failed to terminate {label} pid={process.pid}: {exc}")

        _, alive = psutil.wait_procs(processes, timeout=wait_timeout)
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                continue
            except psutil.Error as exc:
                print(f"[warning] Failed to kill {label} pid={process.pid}: {exc}")
        _, alive = psutil.wait_procs(alive, timeout=1.0)
        return not alive

    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except Exception as exc:
        print(f"[warning] Failed to send SIGTERM to {label} pgid={pgid}: {exc}")
        return False

    deadline = time.time() + wait_timeout
    while time.time() < deadline:
        if not _process_group_alive(pgid):
            return True
        time.sleep(0.2)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except Exception as exc:
        print(f"[warning] Failed to send SIGKILL to {label} pgid={pgid}: {exc}")
        return False

    deadline = time.time() + 1.0
    while time.time() < deadline:
        if not _process_group_alive(pgid):
            return True
        time.sleep(0.2)
    return not _process_group_alive(pgid)


def _stop_managed_process_groups(groups: list[ManagedProcessGroup], *, context: str) -> bool:
    if not groups:
        return True

    print(f"[dev] Stopping repo-local managed services ({context})...")
    stopped_all = True
    seen_pgids: set[int] = set()
    for group in groups:
        if group.pgid in seen_pgids:
            continue
        seen_pgids.add(group.pgid)
        stopped = _terminate_process_group(group.pgid, label=group.label)
        if stopped:
            print(f"[ok] Stopped {group.label} pgid={group.pgid}")
        else:
            stopped_all = False
            print(f"[error] Failed to stop {group.label} pgid={group.pgid}")
    return stopped_all


def _handle_startup_residuals(repo_root: Path, *, cleanup_residuals: bool) -> bool:
    residuals = _collect_repo_managed_process_groups(repo_root)
    if not residuals:
        return True

    action_hint = (
        "Re-run with --cleanup-residuals or stop the listed repo-local process groups manually."
    )
    _print_managed_process_groups(residuals, action_hint=action_hint)

    if not cleanup_residuals:
        print(
            "[error] Found repo-local managed service residuals. Refusing to start a new dev stack."
        )
        return False

    print("[dev] --cleanup-residuals enabled; attempting scoped startup cleanup...")
    _stop_managed_process_groups(residuals, context="startup preflight")
    remaining = _collect_repo_managed_process_groups(repo_root)
    if remaining:
        _print_managed_process_groups(
            remaining,
            action_hint="Stop the listed repo-local process groups manually before retrying startup.",
        )
        print("[error] Residual repo-local managed services remain after scoped startup cleanup.")
        return False

    print("[ok] Cleared repo-local managed service residuals")
    return True


def check_uv_available():
    """检查uv是否可用"""
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[ok] uv available: {result.stdout.strip()}")
            return True
        else:
            print("[error] uv not working properly")
            return False
    except FileNotFoundError:
        print("[error] uv not found in PATH")
        print("Please install uv: https://github.com/astral-sh/uv")
        return False


def check_virtual_environment():
    """Require execution from an activated environment, normally provided by uv run."""

    if sys.prefix == sys.base_prefix:
        print("[error] No active Python virtual environment detected")
        print(
            "Run with: uv run --project backend --frozen " "python backend/scripts/start_dev_uv.py"
        )
        return False

    print(f"[ok] Active Python environment: {sys.prefix}")
    return True


def _check_database_dependency(*, profile: str, database_url: str | None) -> bool:
    from app.infrastructure.database_runtime import preflight_database_runtime

    result = preflight_database_runtime(
        profile=profile,
        database_url=database_url,
    )
    profile_name = result.profile.value if result.profile is not None else profile
    backend_name = result.backend_name or "unknown"
    if result.accepted:
        print(f"[ok] Database connection successful profile={profile_name} backend={backend_name}")
        return True

    reason_code = result.reason_code.value if result.reason_code is not None else "unknown"
    error_type = f" error_type={result.error_type}" if result.error_type else ""
    print(
        f"[error] reason_code={reason_code} profile={profile_name} "
        f"backend={backend_name}{error_type}"
    )
    return False


def check_dependencies():
    """Check if required services are running"""

    print("Checking dependencies...")

    try:
        from app.core.config import settings

        if not _check_database_dependency(
            profile=settings.DATABASE_PROFILE,
            database_url=settings.DATABASE_URL,
        ):
            return False
    except Exception as exc:
        print(
            "[error] reason_code=database_contract_check_failed " f"error_type={type(exc).__name__}"
        )
        return False

    # Check Redis
    try:
        check_code = """
import redis
from app.core.config import settings

try:
    r = redis.from_url(settings.REDIS_URL)
    r.ping()
    print("[ok] Redis connection successful")
except Exception as e:
    print(f"[error] reason_code=redis_connection_failed error_type={type(e).__name__}")
    print("Please ensure Redis is running")
    exit(1)
"""

        result = subprocess.run(
            [sys.executable, "-c", check_code], cwd=REPO_ROOT, capture_output=True, text=True
        )

        if result.returncode == 0:
            print(result.stdout.strip())
        else:
            diagnostic = "\n".join(
                part.strip() for part in (result.stdout, result.stderr) if part.strip()
            )
            print(diagnostic or "[error] Redis dependency check failed without output")
            return False

    except Exception as e:
        print("[error] reason_code=redis_contract_check_failed " f"error_type={type(e).__name__}")
        return False

    return True


def run_migrations():
    """Run database migrations"""

    print("Running database migrations...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        print("[ok] Database migrations completed")
    except subprocess.CalledProcessError as e:
        print(f"[error] Migration failed: {e}")
        print("stdout:", e.stdout)
        print("stderr:", e.stderr)
        return False

    return True


def _start_long_lived_process(
    cmd,
    *,
    cwd: Path,
    env: dict,
    label: str,
    follow_logs_env_var: str,
):
    """Start a long-lived process without leaving stdout/stderr pipes undrained."""

    follow_logs = os.getenv(follow_logs_env_var, "0") == "1"
    popen_kwargs = {
        "cwd": cwd,
        "env": env,
        **_new_process_group_kwargs(),
    }

    if follow_logs:
        popen_kwargs.update(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )

    process = subprocess.Popen(cmd, **popen_kwargs)

    time.sleep(2)

    if process.poll() is None:
        if follow_logs:
            print(f"[dev] {label} logs forwarded to parent stdout ({follow_logs_env_var}=1)")

            def _forward_stream():
                assert process.stdout is not None
                for line in process.stdout:
                    print(line, end="")

            threading.Thread(target=_forward_stream, daemon=True).start()
        else:
            print(f"[dev] {label} logs inherited by parent stdout/stderr")
        return process

    if follow_logs:
        output, _ = process.communicate()
        print(f"[error] {label} failed to start")
        print("output:", output)
    else:
        print(f"[error] {label} failed to start; see console output above for details")
    return None


def _new_process_group_kwargs() -> dict:
    if _is_windows():
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)}
    return {"start_new_session": True}


def _raise_shutdown_interrupt(signum, frame) -> None:
    del signum, frame
    raise KeyboardInterrupt


def _install_shutdown_signal_handlers() -> dict:
    previous_handlers = {}
    handled_signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        handled_signals.append(signal.SIGBREAK)

    for handled_signal in handled_signals:
        previous_handlers[handled_signal] = signal.getsignal(handled_signal)
        signal.signal(handled_signal, _raise_shutdown_interrupt)
    return previous_handlers


def _restore_signal_handlers(previous_handlers: dict) -> None:
    for handled_signal, previous_handler in previous_handlers.items():
        signal.signal(handled_signal, previous_handler)


def _terminate_started_process(process, *, label: str, wait_timeout: float = 5.0) -> bool:
    if _is_windows():
        stopped = _terminate_process_group(process.pid, label=label, wait_timeout=wait_timeout)
        try:
            process.wait(timeout=1)
        except (subprocess.TimeoutExpired, OSError):
            pass
        return stopped

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError as exc:
        print(f"[warning] Failed to send SIGTERM to {label} pgid={process.pid}: {exc}")
        return False

    try:
        process.wait(timeout=wait_timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        except OSError as exc:
            print(f"[warning] Failed to send SIGKILL to {label} pgid={process.pid}: {exc}")
            return False
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            return False

    if _process_group_alive(process.pid):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        except OSError as exc:
            print(f"[warning] Failed to clear {label} pgid={process.pid}: {exc}")
            return False
    return True


def start_celery_worker():
    """Start Celery worker in background"""

    print("Starting Celery worker with watchdog hot reload...")

    # 允许用环境变量控制关键参数（不改业务）：
    #  CELERY_LOG_LEVEL=debug|info（默认 info）
    #  CELERY_WORKER_POOL=solo|prefork（默认 solo，开发期 Ctrl+C 更友好）
    #  CELERY_WORKER_CONCURRENCY=1（默认 1，便于调试）
    #  CELERY_QUEUES=celery,video_processing（监听的队列列表）
    #  CELERY_SOFT_TIME_LIMIT/CELERY_TIME_LIMIT（可选，单位秒）
    # 优先使用 CELERY_LOG_LEVEL；未设置时回退到全局 LOG_LEVEL，再回退到 info
    log_level = (os.getenv("CELERY_LOG_LEVEL") or os.getenv("LOG_LEVEL") or "info").lower()
    print(f"[dev] Celery worker effective log level: {log_level}")
    pool = os.getenv("CELERY_WORKER_POOL", "solo")
    concurrency = os.getenv("CELERY_WORKER_CONCURRENCY", "1")
    queues = os.getenv("CELERY_QUEUES", "celery,video_processing")
    soft_tl = os.getenv("CELERY_SOFT_TIME_LIMIT")
    hard_tl = os.getenv("CELERY_TIME_LIMIT")

    # 使用 watchmedo 实现热重载；允许通过 CELERY_DISABLE_WATCHDOG=1 关闭
    use_watchdog = os.getenv("CELERY_DISABLE_WATCHDOG", "0") != "1"

    base_cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.services.celery_app",
        "worker",
        f"--loglevel={log_level}",
        f"--concurrency={concurrency}",
        f"--queues={queues}",
        "--without-gossip",
        "--without-mingle",
        "--without-heartbeat",
        "-Ofair",
        f"--pool={pool}",
    ]
    if soft_tl:
        base_cmd.append(f"--soft-time-limit={soft_tl}")
    if hard_tl:
        base_cmd.append(f"--time-limit={hard_tl}")

    celery_cmd = (
        [
            sys.executable,
            "-m",
            "watchdog.watchmedo",
            "auto-restart",
            "--directory=./",
            "--pattern=*.py",
            "--recursive",
            "--",
        ]
        + base_cmd
        if use_watchdog
        else base_cmd
    )

    try:
        env = _build_env_with_no_proxy()
        process = _start_long_lived_process(
            celery_cmd,
            cwd=REPO_ROOT,
            env=env,
            label="Celery worker",
            follow_logs_env_var="FOLLOW_CELERY_LOGS",
        )
        if process is not None:
            print("[ok] Celery worker started")
            return process
        return None
    except Exception as e:
        print(f"[error] Failed to start Celery worker: {e}")
        return None


def start_celery_beat():
    """Start Celery beat scheduler in background"""

    print("Starting Celery beat...")

    # 优先使用 CELERY_BEAT_LOG_LEVEL；未设置时回退到全局 LOG_LEVEL，再回退到 info
    beat_log_level = (
        os.getenv("CELERY_BEAT_LOG_LEVEL") or os.getenv("LOG_LEVEL") or "info"
    ).lower()
    print(f"[dev] Celery beat effective log level: {beat_log_level}")
    beat_cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.services.celery_app",
        "beat",
        f"--loglevel={beat_log_level}",
    ]

    try:
        env = _build_env_with_no_proxy()
        process = _start_long_lived_process(
            beat_cmd,
            cwd=REPO_ROOT,
            env=env,
            label="Celery beat",
            follow_logs_env_var="FOLLOW_CELERY_LOGS",
        )
        if process is not None:
            print("[ok] Celery beat started")
            return process
        return None
    except Exception as e:
        print(f"[error] Failed to start Celery beat: {e}")
        return None


def start_api_server():
    """Start FastAPI server"""

    print("Starting FastAPI server...")

    # Read API server configuration from environment
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = os.getenv("API_PORT", "8000")

    api_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        api_host,
        "--port",
        api_port,
        "--log-level",
        "info",
    ]

    # Optional hot-reload (disabled by default to avoid WSL file-watcher storms)
    enable_reload = os.getenv("ENABLE_RELOAD", "0") == "1"
    if enable_reload:
        # Limit reload scope to backend app directory for stability on WSL
        api_cmd += ["--reload", "--reload-dir", "app"]

    # 代理处理：在 NO_PROXY 中加入本地/国内端点，避免代理引起的超时
    env = _build_env_with_no_proxy()

    try:
        print(f"Starting with command: {' '.join(api_cmd)}")
        print(f"Working directory: {REPO_ROOT}")

        process = _start_long_lived_process(
            api_cmd,
            cwd=REPO_ROOT,
            env=env,
            label="FastAPI server",
            follow_logs_env_var="FOLLOW_API_LOGS",
        )
        if process is None:
            return None
        if enable_reload:
            print(f"[ok] FastAPI server started on http://localhost:{api_port} (reload ON)")
        else:
            print(f"[ok] FastAPI server started on http://localhost:{api_port} (reload OFF)")
        print(f"[ok] API accessible at http://127.0.0.1:{api_port} (bypassing proxy)")

        return process
    except Exception as e:
        print(f"[error] Failed to start FastAPI server: {e}")
        return None


def cleanup_processes(processes, repo_root: Path | None = None):
    """Clean up background processes"""
    repo_root = (repo_root or REPO_ROOT).resolve()

    print("\nShutting down services...")

    for name, process in processes.items():
        if process and process.poll() is None:
            print(f"Stopping {name}...")
            if not _terminate_started_process(process, label=name):
                print(f"[warning] Failed to fully stop {name} process group")

    residuals = _collect_repo_managed_process_groups(repo_root)
    if residuals:
        _print_managed_process_groups(
            residuals,
            action_hint="Launcher is attempting scoped shutdown for these repo-local residuals.",
        )
        _stop_managed_process_groups(residuals, context="shutdown residual cleanup")
        residuals = _collect_repo_managed_process_groups(repo_root)

    if residuals:
        _print_managed_process_groups(
            residuals,
            action_hint="Use repo-scoped manual cleanup only as an emergency escape hatch.",
        )
        print("[warning] Repo-local managed service residuals still remain after scoped shutdown.")
    else:
        print("[ok] No repo-local managed service residuals remain")


def show_environment_info():
    """显示环境信息"""
    print("Environment Information:")
    print("=" * 40)

    # 显示uv信息
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        print(f"uv version: {result.stdout.strip()}")
    except (OSError, subprocess.SubprocessError):
        print("uv version: Not available")

    print(f"Python version: {sys.version.split()[0]}")
    print(f"Python executable: {sys.executable}")
    print(f"Environment file: {PROJECT_ROOT / '.env'}")

    print("=" * 40)


def main(argv=None):
    """Main function"""
    args = _parse_args(argv)

    print("MuseCraft Backend (Development Mode with uv)")
    print("=" * 60)

    # 检查uv可用性
    if not check_uv_available():
        return 1

    # 检查虚拟环境
    if not check_virtual_environment():
        return 1

    # 显示环境信息
    show_environment_info()

    if not _handle_startup_residuals(REPO_ROOT, cleanup_residuals=args.cleanup_residuals):
        return 1

    processes = {}
    previous_signal_handlers = _install_shutdown_signal_handlers()

    try:
        # Check dependencies
        if not check_dependencies():
            return 1

        # Run migrations
        if not run_migrations():
            return 1

        if getattr(args, "check", False):
            print("[ok] uv backend preflight completed; dependencies and migrations are ready")
            return 0

        # Start Celery worker
        worker_process = start_celery_worker()
        processes["celery_worker"] = worker_process
        if not worker_process:
            print("[error] Backend startup aborted because the Celery worker did not start")
            return 1

        # Start Celery beat
        beat_process = start_celery_beat()
        processes["celery_beat"] = beat_process
        if not beat_process:
            print("[error] Backend startup aborted because Celery beat did not start")
            return 1

        # Start API server
        api_process = start_api_server()
        processes["api_server"] = api_process

        if not api_process:
            print("[error] Backend startup aborted because the API did not start")
            return 1

        api_port = os.getenv("API_PORT", "8000")
        print("\n" + "=" * 60)
        print("API, Celery worker, and Celery beat started successfully")
        print(f"API documentation: http://localhost:{api_port}/docs")
        print(f"Health check: http://localhost:{api_port}/health")
        print("")
        print("Development tips:")
        print("   - Press Ctrl+C to stop all services")
        print("   - Celery worker uses watchdog for hot reload")
        print("   - Code changes in .py files auto-restart worker")
        print("   - Set ENABLE_RELOAD=1 to enable FastAPI hot reload")
        print("=" * 60)

        # Wait for API server
        api_process.wait()
        if api_process.poll() not in (None, 0):
            print(f"[error] API process exited with status {api_process.poll()}")
            return 1
        return 0

    except KeyboardInterrupt:
        print("\nReceived interrupt signal")
        return 0
    except Exception as e:
        print(f"[error] Unexpected error: {e}")
        return 1
    finally:
        cleanup_processes(processes, REPO_ROOT)
        _restore_signal_handlers(previous_signal_handlers)
        print("All services stopped")


if __name__ == "__main__":
    sys.exit(main())
