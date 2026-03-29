#!/usr/bin/env python3
"""
使用uv的开发服务器启动脚本
"""
import argparse
import os
import sys
import subprocess
import signal
import time
import threading
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


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
    defaults = ['localhost', '127.0.0.1', '::1']

    # User-provided domains to bypass (optional)
    user_extra = env.get('BYPASS_PROXY_DOMAINS', '')
    user_list = [x.strip() for x in user_extra.split(',') if x.strip()]

    # Call-site extra
    extra_list = extra_hosts or []

    existing_no_proxy = env.get('NO_PROXY') or env.get('no_proxy') or ''
    existing_list = [x.strip() for x in existing_no_proxy.split(',') if x.strip()]

    merged = []
    for host in existing_list + defaults + user_list + extra_list:
        if host and host not in merged:
            merged.append(host)

    merged_value = ','.join(merged)
    env['NO_PROXY'] = merged_value
    env['no_proxy'] = merged_value
    return env

# Add the parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent

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
    parser = argparse.ArgumentParser(description="Start the local Short Video Maker dev stack.")
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


def _read_process_cwd(pid: int) -> Path | None:
    try:
        return Path(os.readlink(f"/proc/{pid}/cwd")).resolve()
    except OSError:
        return None


def _is_repo_scoped_process(pid: int, repo_root: Path) -> tuple[bool, Path | None]:
    cwd = _read_process_cwd(pid)
    if cwd is None:
        return False, None
    try:
        cwd.relative_to(repo_root.resolve())
    except ValueError:
        return False, cwd
    return True, cwd


def _select_group_label(labels: set[str]) -> str:
    return min(labels, key=lambda label: (_LABEL_PRIORITY.get(label, 999), label))


def _collect_repo_managed_process_groups(repo_root: Path) -> list[ManagedProcessGroup]:
    repo_root = repo_root.resolve()
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,pgid=,args="],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as exc:
        print(f"⚠ Failed to inspect local processes for repo residuals: {exc}")
        return []

    grouped: dict[int, dict] = {}
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid_str, pgid_str, command = parts
        label = _detect_managed_label(command)
        if label is None:
            continue
        try:
            pid = int(pid_str)
            pgid = int(pgid_str)
        except ValueError:
            continue

        is_repo_scoped, cwd = _is_repo_scoped_process(pid, repo_root)
        if not is_repo_scoped or cwd is None:
            continue

        entry = grouped.setdefault(
            pgid,
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
            pgid=pgid,
            pids=tuple(sorted(entry["pids"])),
            commands=tuple(entry["commands"]),
            cwd=entry["cwd"],
            port=entry["port"],
        )
        for pgid, entry in grouped.items()
    ]
    return sorted(groups, key=lambda group: (_LABEL_PRIORITY.get(group.label, 999), group.pgid))


def _print_managed_process_groups(groups: list[ManagedProcessGroup], *, action_hint: str) -> None:
    print("Detected repo-local managed service residuals:")
    for group in groups:
        port_bits = f" port={group.port}" if group.port else ""
        print(f"  - label={group.label} pgid={group.pgid}{port_bits}")
        print(f"    pids: {', '.join(str(pid) for pid in group.pids)}")
        print(f"    cwd: {group.cwd}")
        print(f"    command: {group.commands[0]}")
        print(f"    recommended action: {action_hint}")


def _process_group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(pgid: int, *, label: str, wait_timeout: float = 5.0) -> bool:
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except Exception as exc:
        print(f"⚠ Failed to send SIGTERM to {label} pgid={pgid}: {exc}")
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
        print(f"⚠ Failed to send SIGKILL to {label} pgid={pgid}: {exc}")
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
            print(f"✓ Stopped {group.label} pgid={group.pgid}")
        else:
            stopped_all = False
            print(f"✗ Failed to stop {group.label} pgid={group.pgid}")
    return stopped_all


def _handle_startup_residuals(repo_root: Path, *, cleanup_residuals: bool) -> bool:
    residuals = _collect_repo_managed_process_groups(repo_root)
    if not residuals:
        return True

    action_hint = "Re-run with --cleanup-residuals or stop the listed repo-local process groups manually."
    _print_managed_process_groups(residuals, action_hint=action_hint)

    if not cleanup_residuals:
        print("✗ Found repo-local managed service residuals. Refusing to start a new dev stack.")
        return False

    print("[dev] --cleanup-residuals enabled; attempting scoped startup cleanup...")
    _stop_managed_process_groups(residuals, context="startup preflight")
    remaining = _collect_repo_managed_process_groups(repo_root)
    if remaining:
        _print_managed_process_groups(
            remaining,
            action_hint="Stop the listed repo-local process groups manually before retrying startup.",
        )
        print("✗ Residual repo-local managed services remain after scoped startup cleanup.")
        return False

    print("✓ Cleared repo-local managed service residuals")
    return True

def check_uv_available():
    """检查uv是否可用"""
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ uv available: {result.stdout.strip()}")
            return True
        else:
            print("✗ uv not working properly")
            return False
    except FileNotFoundError:
        print("✗ uv not found in PATH")
        print("Please install uv: https://github.com/astral-sh/uv")
        return False

def check_virtual_environment():
    """检查虚拟环境"""
    venv_path = REPO_ROOT / ".venv"
    
    if not venv_path.exists():
        print("✗ Virtual environment not found")
        print("Please run: python scripts/setup_uv_environment.py")
        return False
    
    print("✓ Virtual environment found")
    return True

def check_dependencies():
    """Check if required services are running"""
    
    print("Checking dependencies...")
    
    # Check Database (MySQL or PostgreSQL)
    try:
        # 使用uv运行Python代码来检查依赖
        check_code = """
from app.core.config import settings
from sqlalchemy import create_engine, text

try:
    # Support both MySQL and PostgreSQL
    sync_database_url = settings.DATABASE_URL
    if settings.DATABASE_URL.startswith("mysql://"):
        sync_database_url = settings.DATABASE_URL.replace("mysql://", "mysql+pymysql://")
    
    engine = create_engine(sync_database_url)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    
    db_type = "MySQL" if settings.DATABASE_URL.startswith("mysql://") else "PostgreSQL"
    print(f"✓ {db_type} connection successful")
except Exception as e:
    print(f"✗ Database connection failed: {e}")
    db_type = "MySQL" if settings.DATABASE_URL.startswith("mysql://") else "PostgreSQL"
    print(f"Please ensure {db_type} is running and database is created")
    exit(1)
"""
        
        result = subprocess.run(
            ["uv", "run", "python", "-c", check_code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(result.stdout.strip())
        else:
            print(result.stderr.strip())
            return False
            
    except Exception as e:
        print(f"✗ PostgreSQL check failed: {e}")
        return False
    
    # Check Redis
    try:
        check_code = """
import redis
from app.core.config import settings

try:
    r = redis.from_url(settings.REDIS_URL)
    r.ping()
    print("✓ Redis connection successful")
except Exception as e:
    print(f"✗ Redis connection failed: {e}")
    print("Please ensure Redis is running")
    exit(1)
"""
        
        result = subprocess.run(
            ["uv", "run", "python", "-c", check_code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(result.stdout.strip())
        else:
            print(result.stderr.strip())
            return False
            
    except Exception as e:
        print(f"✗ Redis check failed: {e}")
        return False
    
    return True

def run_migrations():
    """Run database migrations"""
    
    print("Running database migrations...")
    
    try:
        result = subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True
        )
        print("✓ Database migrations completed")
    except subprocess.CalledProcessError as e:
        print(f"✗ Migration failed: {e}")
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
        "preexec_fn": os.setsid,
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
        print(f"✗ {label} failed to start")
        print("output:", output)
    else:
        print(f"✗ {label} failed to start; see console output above for details")
    return None

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
        "celery", "-A", "app.services.celery_app", "worker",
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
            "uv", "run", "watchmedo", "auto-restart",
            "--directory=./",
            "--pattern=*.py",
            "--recursive",
            "--",
        ]
        + base_cmd
        if use_watchdog
        else ["uv", "run", *base_cmd]
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
            print("✓ Celery worker started")
            return process
        return None
    except Exception as e:
        print(f"✗ Failed to start Celery worker: {e}")
        return None

def start_celery_beat():
    """Start Celery beat scheduler in background"""
    
    print("Starting Celery beat...")
    
    # 优先使用 CELERY_BEAT_LOG_LEVEL；未设置时回退到全局 LOG_LEVEL，再回退到 info
    beat_log_level = (os.getenv("CELERY_BEAT_LOG_LEVEL") or os.getenv("LOG_LEVEL") or "info").lower()
    print(f"[dev] Celery beat effective log level: {beat_log_level}")
    beat_cmd = [
        "uv", "run", "celery", "-A", "app.services.celery_app", "beat",
        f"--loglevel={beat_log_level}"
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
            print("✓ Celery beat started")
            return process
        return None
    except Exception as e:
        print(f"✗ Failed to start Celery beat: {e}")
        return None

def start_api_server():
    """Start FastAPI server"""

    print("Starting FastAPI server...")

    # Read API server configuration from environment
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = os.getenv("API_PORT", "8000")

    api_cmd = [
        "uv", "run", "uvicorn", "app.main:app",
        "--host", api_host,
        "--port", api_port,
        "--log-level", "info"
    ]

    # Optional hot-reload (disabled by default to avoid WSL file-watcher storms)
    enable_reload = os.getenv("ENABLE_RELOAD", "0") == "1"
    if enable_reload:
        # Limit reload scope to backend app directory for stability on WSL
        api_cmd += ["--reload", "--reload-dir", "app"]
    
    # 代理处理：在 NO_PROXY 中加入本地/国内端点，避免代理引起的超时
    env = _build_env_with_no_proxy()
    
    try:
        # Add debug output
        print(f"Starting with command: {' '.join(api_cmd)}")
        print(f"Working directory: {REPO_ROOT}")
        print("Environment proxy variables after cleanup:")
        for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
            print(f"  {key}: {env.get(key, 'Not set')}")
        print(f"  NO_PROXY: {env.get('NO_PROXY', 'Not set')}")

        follow_logs = os.getenv("FOLLOW_API_LOGS", "0") == "1"

        if follow_logs:
            # Pipe and forward logs to current stdout
            process = subprocess.Popen(
                api_cmd,
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                preexec_fn=os.setsid
            )
            import threading
            def _forward():
                assert process.stdout is not None
                for line in process.stdout:
                    print(line, end="")
            threading.Thread(target=_forward, daemon=True).start()
        else:
            # Inherit stdout/stderr; uvicorn logs won't be reprinted by this script
            process = subprocess.Popen(
                api_cmd,
                cwd=REPO_ROOT,
                env=env,
                preexec_fn=os.setsid
            )
        if enable_reload:
            print(f"✓ FastAPI server started on http://localhost:{api_port} (reload ON)")
        else:
            print(f"✓ FastAPI server started on http://localhost:{api_port} (reload OFF)")
        print(f"✓ API accessible at http://127.0.0.1:{api_port} (bypassing proxy)")
        
        # Wait a moment and check if it's actually running
        import time
        time.sleep(2)
        if process.poll() is None:
            print("✓ Process is running")
        else:
            print("✗ Uvicorn exited early. Check above logs for the error.")
            return None
            
        return process
    except Exception as e:
        print(f"✗ Failed to start FastAPI server: {e}")
        return None

def cleanup_processes(processes, repo_root: Path | None = None):
    """Clean up background processes"""
    repo_root = (repo_root or REPO_ROOT).resolve()

    print("\nShutting down services...")
    
    for name, process in processes.items():
        if process and process.poll() is None:
            print(f"Stopping {name}...")
            try:
                # terminate whole process group
                os.killpg(process.pid, signal.SIGTERM)
            except Exception:
                process.terminate()

            # Wait for graceful shutdown
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"Force killing {name} (group)...")
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except Exception:
                    process.kill()

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
        print("⚠ Repo-local managed service residuals still remain after scoped shutdown.")
    else:
        print("✓ No repo-local managed service residuals remain")

def show_environment_info():
    """显示环境信息"""
    print("Environment Information:")
    print("=" * 40)
    
    # 显示uv信息
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        print(f"uv version: {result.stdout.strip()}")
    except:
        print("uv version: Not available")
    
    # 显示Python版本
    try:
        result = subprocess.run(
            ["uv", "run", "python", "--version"], 
            capture_output=True, 
            text=True,
            cwd=REPO_ROOT
        )
        print(f"Python version: {result.stdout.strip()}")
    except:
        print("Python version: Not available")
    
    # 显示已安装包数量
    try:
        result = subprocess.run(
            ["uv", "pip", "list"], 
            capture_output=True, 
            text=True,
            cwd=REPO_ROOT
        )
        package_count = len(result.stdout.strip().split('\n')) - 2  # 减去标题行
        print(f"Installed packages: {package_count}")
    except:
        print("Installed packages: Unknown")
    
    print("=" * 40)

def main(argv=None):
    """Main function"""
    args = _parse_args(argv)
    
    print("🎬 Short Video Maker Backend (Development Mode with uv)")
    print("=" * 60)
    
    # 检查uv可用性
    if not check_uv_available():
        sys.exit(1)
    
    # 检查虚拟环境
    if not check_virtual_environment():
        sys.exit(1)
    
    # 显示环境信息
    show_environment_info()

    if not _handle_startup_residuals(REPO_ROOT, cleanup_residuals=args.cleanup_residuals):
        sys.exit(1)
    
    processes = {}
    
    try:
        # Check dependencies
        if not check_dependencies():
            sys.exit(1)
        
        # Run migrations
        if not run_migrations():
            sys.exit(1)
        
        # Start Celery worker
        worker_process = start_celery_worker()
        processes["celery_worker"] = worker_process
        
        # Start Celery beat
        beat_process = start_celery_beat()
        processes["celery_beat"] = beat_process
        
        # Start API server
        api_process = start_api_server()
        processes["api_server"] = api_process
        
        if not api_process:
            sys.exit(1)
        
        api_port = os.getenv("API_PORT", "8000")
        print("\n" + "=" * 60)
        print("🎉 All services started successfully!")
        print(f"📚 API Documentation: http://localhost:{api_port}/docs")
        print(f"❤️  Health Check: http://localhost:{api_port}/health")
        print("")
        print("🔄 Development Tips:")
        print("   • Press Ctrl+C to stop all services")
        print("   • Celery worker uses watchdog for hot reload")
        print("   • Code changes in .py files auto-restart worker")
        print("   • FastAPI has hot reload for API changes")
        print("=" * 60)
        
        # Wait for API server
        api_process.wait()
        
    except KeyboardInterrupt:
        print("\n🛑 Received interrupt signal")
    except Exception as e:
        print(f"💥 Unexpected error: {e}")
    finally:
        cleanup_processes(processes, REPO_ROOT)
        print("🏁 All services stopped")

if __name__ == "__main__":
    main()
