#!/usr/bin/env python3
"""
使用uv的开发服务器启动脚本
"""
import os
import sys
import subprocess
import signal
import time
from pathlib import Path

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
    venv_path = Path(__file__).parent.parent / ".venv"
    
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
            cwd=Path(__file__).parent.parent,
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
            cwd=Path(__file__).parent.parent,
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
            cwd=Path(__file__).parent.parent,
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

def start_celery_worker():
    """Start Celery worker in background"""
    
    print("Starting Celery worker with watchdog hot reload...")
    
    # 使用 watchmedo 实现真正的热重载
    celery_cmd = [
        "uv", "run", "watchmedo", "auto-restart",
        "--directory=./",
        "--pattern=*.py",
        "--recursive",
        "--",
        "celery", "-A", "app.services.celery_app", "worker",
        "--loglevel=info",
        "--concurrency=1",  # 减少并发以便于调试
        "--queues=celery,video_processing",  # 监听默认队列和视频处理队列
        "--without-gossip",  # 修复Windows/WSL任务执行问题
        "--without-mingle",
        "--without-heartbeat",
        "-Ofair",
        "--pool=solo"  # 单线程模式，确保任务执行
    ]
    
    try:
        env = _build_env_with_no_proxy()
        process = subprocess.Popen(
            celery_cmd,
            cwd=Path(__file__).parent.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            preexec_fn=os.setsid  # create new process group for clean shutdown
        )
        
        # Give it a moment to start
        time.sleep(2)
        
        if process.poll() is None:
            print("✓ Celery worker started")
            return process
        else:
            stdout, stderr = process.communicate()
            print(f"✗ Celery worker failed to start")
            print("stdout:", stdout.decode())
            print("stderr:", stderr.decode())
            return None
    except Exception as e:
        print(f"✗ Failed to start Celery worker: {e}")
        return None

def start_celery_beat():
    """Start Celery beat scheduler in background"""
    
    print("Starting Celery beat...")
    
    beat_cmd = [
        "uv", "run", "celery", "-A", "app.services.celery_app", "beat",
        "--loglevel=info"
    ]
    
    try:
        env = _build_env_with_no_proxy()
        process = subprocess.Popen(
            beat_cmd,
            cwd=Path(__file__).parent.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            preexec_fn=os.setsid
        )
        
        # Give it a moment to start
        time.sleep(2)
        
        if process.poll() is None:
            print("✓ Celery beat started")
            return process
        else:
            stdout, stderr = process.communicate()
            print(f"✗ Celery beat failed to start")
            print("stdout:", stdout.decode())
            print("stderr:", stderr.decode())
            return None
    except Exception as e:
        print(f"✗ Failed to start Celery beat: {e}")
        return None

def start_api_server():
    """Start FastAPI server"""
    
    print("Starting FastAPI server...")
    
    api_cmd = [
        "uv", "run", "uvicorn", "app.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
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
        print(f"Working directory: {Path(__file__).parent.parent}")
        print("Environment proxy variables after cleanup:")
        for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
            print(f"  {key}: {env.get(key, 'Not set')}")
        print(f"  NO_PROXY: {env.get('NO_PROXY', 'Not set')}")

        follow_logs = os.getenv("FOLLOW_API_LOGS", "0") == "1"

        if follow_logs:
            # Pipe and forward logs to current stdout
            process = subprocess.Popen(
                api_cmd,
                cwd=Path(__file__).parent.parent,
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
                cwd=Path(__file__).parent.parent,
                env=env,
                preexec_fn=os.setsid
            )
        if enable_reload:
            print("✓ FastAPI server started on http://localhost:8000 (reload ON)")
        else:
            print("✓ FastAPI server started on http://localhost:8000 (reload OFF)")
        print("✓ API accessible at http://127.0.0.1:8000 (bypassing proxy)")
        
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

def cleanup_processes(processes):
    """Clean up background processes"""
    
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
    
    # 额外清理可能残留的Celery进程
    # Best-effort extra cleanup of stray processes (Celery worker/beat, watchmedo, uvicorn)
    try:
        patterns = [
            "celery.*worker",
            "celery.*beat",
            "watchmedo auto-restart",
            "uvicorn app.main:app"
        ]
        for pat in patterns:
            subprocess.run(["pkill", "-f", pat], capture_output=True, text=True)
        print("✓ Attempted cleanup of residual processes (celery/watchmedo/uvicorn)")
    except Exception:
        pass  # 忽略清理错误

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
            cwd=Path(__file__).parent.parent
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
            cwd=Path(__file__).parent.parent
        )
        package_count = len(result.stdout.strip().split('\n')) - 2  # 减去标题行
        print(f"Installed packages: {package_count}")
    except:
        print("Installed packages: Unknown")
    
    print("=" * 40)

def main():
    """Main function"""
    
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
        
        print("\n" + "=" * 60)
        print("🎉 All services started successfully!")
        print("📚 API Documentation: http://localhost:8000/docs")
        print("❤️  Health Check: http://localhost:8000/health")
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
        cleanup_processes(processes)
        print("🏁 All services stopped")

if __name__ == "__main__":
    main()
