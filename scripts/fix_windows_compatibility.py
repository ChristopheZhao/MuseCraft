#!/usr/bin/env python3
"""
Windows Compatibility Fixes
"""

import os
import platform
import re
from pathlib import Path
from typing import List, Dict, Any

def is_windows():
    """Check if running on Windows"""
    return platform.system() == "Windows"

def fix_path_separators():
    """Fix hardcoded path separators in configuration files"""
    print("🔧 Fixing path separators for Windows compatibility...")
    
    files_to_fix = [
        "backend/app/core/config.py",
        ".env",
        ".env.example"
    ]
    
    for file_path in files_to_fix:
        if not Path(file_path).exists():
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Fix path separators in default values
            # Replace ./storage/uploads with os-agnostic paths
            patterns = [
                (r'default="./storage/([^"]+)"', r'default=os.path.join(".", "storage", "\1")'),
                (r'default="([^"]*)/([^"]*)"', r'default=os.path.join("\1", "\2")'),
            ]
            
            modified = False
            for pattern, replacement in patterns:
                if re.search(pattern, content):
                    content = re.sub(pattern, replacement, content)
                    modified = True
            
            # Add os import if needed and not present
            if 'os.path.join' in content and 'import os' not in content:
                if 'from pathlib import Path' in content:
                    content = content.replace('from pathlib import Path', 'import os\nfrom pathlib import Path')
                else:
                    content = 'import os\n' + content
                modified = True
            
            if modified:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"   ✅ Fixed paths in {file_path}")
            else:
                print(f"   ✅ {file_path} already compatible")
                
        except Exception as e:
            print(f"   ❌ Failed to fix {file_path}: {e}")

def create_windows_env_file():
    """Create Windows-specific environment file"""
    print("🔧 Creating Windows-specific environment configuration...")
    
    windows_env_content = """# Windows-specific environment configuration
# Database URL for Windows PostgreSQL
DATABASE_URL=postgresql://postgres:password@localhost:5432/short_video_maker

# Redis URL for Windows Redis
REDIS_URL=redis://localhost:6379/0

# File storage paths (Windows compatible)
UPLOAD_PATH=.\\storage\\uploads
GENERATED_PATH=.\\storage\\generated
TEMP_PATH=.\\storage\\temp

# FFmpeg path (adjust if needed)
# FFMPEG_PATH=C:\\Program Files\\FFmpeg\\bin\\ffmpeg.exe

# Windows-specific Celery configuration
CELERY_WORKER_CONCURRENCY=2
CELERY_WORKER_POOL=solo

# Performance adjustments for Windows
MAX_MEMORY_USAGE_PERCENT=70
MAX_CPU_USAGE_PERCENT=75
"""
    
    try:
        with open(".env.windows", 'w', encoding='utf-8') as f:
            f.write(windows_env_content)
        print("   ✅ Created .env.windows with Windows-specific settings")
    except Exception as e:
        print(f"   ❌ Failed to create .env.windows: {e}")

def create_platform_detection():
    """Add platform detection utility"""
    print("🔧 Creating platform detection utility...")
    
    platform_utils_content = '''"""
Platform utilities for cross-platform compatibility
"""

import os
import platform
import shutil
from pathlib import Path
from typing import Optional

def is_windows() -> bool:
    """Check if running on Windows"""
    return platform.system() == "Windows"

def is_linux() -> bool:
    """Check if running on Linux"""
    return platform.system() == "Linux"

def is_macos() -> bool:
    """Check if running on macOS"""
    return platform.system() == "Darwin"

def get_platform_name() -> str:
    """Get platform name"""
    return platform.system()

def normalize_path(path: str) -> str:
    """Normalize path for current platform"""
    return str(Path(path))

def get_executable_path(executable: str) -> Optional[str]:
    """Get path to executable, handling platform differences"""
    
    # First try standard location
    exe_path = shutil.which(executable)
    if exe_path:
        return exe_path
    
    # Windows-specific search paths
    if is_windows():
        common_paths = {
            "ffmpeg": [
                "C:\\\\Program Files\\\\FFmpeg\\\\bin\\\\ffmpeg.exe",
                "C:\\\\ffmpeg\\\\bin\\\\ffmpeg.exe",
                "C:\\\\Users\\\\%s\\\\ffmpeg\\\\bin\\\\ffmpeg.exe" % os.getenv("USERNAME", ""),
            ],
            "redis-server": [
                "C:\\\\Program Files\\\\Redis\\\\redis-server.exe",
                "C:\\\\Redis\\\\redis-server.exe",
            ],
            "psql": [
                "C:\\\\Program Files\\\\PostgreSQL\\\\*\\\\bin\\\\psql.exe",
            ]
        }
        
        if executable in common_paths:
            for path_template in common_paths[executable]:
                # Handle wildcards for version numbers
                if "*" in path_template:
                    import glob
                    matches = glob.glob(path_template)
                    if matches:
                        return matches[0]
                else:
                    if os.path.exists(path_template):
                        return path_template
    
    return None

def get_platform_specific_config() -> dict:
    """Get platform-specific configuration"""
    if is_windows():
        return {
            "path_separator": "\\\\",
            "line_ending": "\\r\\n",
            "default_shell": "cmd",
            "supports_signals": False,
            "max_path_length": 260,
            "case_sensitive_paths": False,
            "preferred_redis_implementation": "redis-windows",
            "celery_worker_pool": "solo",  # Windows doesn't support fork()
        }
    elif is_linux():
        return {
            "path_separator": "/",
            "line_ending": "\\n", 
            "default_shell": "bash",
            "supports_signals": True,
            "max_path_length": 4096,
            "case_sensitive_paths": True,
            "preferred_redis_implementation": "redis",
            "celery_worker_pool": "prefork",
        }
    else:  # macOS and others
        return {
            "path_separator": "/",
            "line_ending": "\\n",
            "default_shell": "zsh",
            "supports_signals": True, 
            "max_path_length": 1024,
            "case_sensitive_paths": True,
            "preferred_redis_implementation": "redis",
            "celery_worker_pool": "prefork",
        }

def create_platform_directories():
    """Create necessary directories with proper permissions"""
    directories = [
        "storage/uploads",
        "storage/generated", 
        "storage/temp",
        "logs",
        "test_results"
    ]
    
    for directory in directories:
        dir_path = Path(directory)
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            
            # Set permissions on non-Windows systems
            if not is_windows():
                os.chmod(dir_path, 0o755)
                
        except Exception as e:
            print(f"Warning: Could not create directory {directory}: {e}")

def get_redis_config():
    """Get Redis configuration for current platform"""
    if is_windows():
        return {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "socket_timeout": 30,
            "socket_connect_timeout": 30,
            "retry_on_timeout": True,
            "health_check_interval": 30,
        }
    else:
        return {
            "host": "localhost", 
            "port": 6379,
            "db": 0,
            "socket_timeout": 5,
            "socket_connect_timeout": 5,
            "retry_on_timeout": True,
            "health_check_interval": 30,
        }
'''
    
    try:
        utils_dir = Path("backend/app/utils")
        utils_dir.mkdir(exist_ok=True)
        
        with open(utils_dir / "platform_utils.py", 'w', encoding='utf-8') as f:
            f.write(platform_utils_content)
        print("   ✅ Created platform_utils.py")
    except Exception as e:
        print(f"   ❌ Failed to create platform utilities: {e}")

def fix_celery_configuration():
    """Fix Celery configuration for Windows"""
    print("🔧 Fixing Celery configuration for Windows...")
    
    celery_file = Path("backend/app/services/celery_app.py")
    if not celery_file.exists():
        print("   ⚠️ Celery configuration file not found")
        return
    
    try:
        with open(celery_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Add Windows-specific Celery configuration
        windows_config = '''
# Windows-specific Celery configuration
if platform.system() == "Windows":
    # Windows doesn\'t support fork(), use solo pool
    app.conf.worker_pool = "solo"
    app.conf.worker_concurrency = 1
    app.conf.worker_prefetch_multiplier = 1
    
    # Disable signal handling on Windows
    app.conf.worker_disable_rate_limits = True
    app.conf.task_always_eager = False
'''
        
        # Add platform import if not present
        if 'import platform' not in content:
            content = 'import platform\n' + content
        
        # Add Windows config if not present
        if 'Windows-specific Celery configuration' not in content:
            # Find a good place to insert (after app creation)
            if 'app = Celery(' in content:
                insertion_point = content.find('app = Celery(')
                # Find end of app creation block
                lines = content[insertion_point:].split('\n')
                insert_after = insertion_point
                for i, line in enumerate(lines):
                    if line.strip() == '' or (i > 0 and not line.startswith(' ') and not line.startswith('\t')):
                        insert_after = insertion_point + len('\n'.join(lines[:i]))
                        break
                
                content = content[:insert_after] + windows_config + content[insert_after:]
        
        with open(celery_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print("   ✅ Added Windows-specific Celery configuration")
        
    except Exception as e:
        print(f"   ❌ Failed to fix Celery configuration: {e}")

def create_windows_docker_override():
    """Create Windows-specific Docker override"""
    print("🔧 Creating Windows Docker override...")
    
    docker_override_content = '''version: '3.8'

# Windows-specific Docker Compose overrides
services:
  api:
    volumes:
      # Windows-style volume mounts
      - .\\backend:/app
      - .\\storage:/app/storage
      - .\\logs:/app/logs
    environment:
      # Windows-specific environment
      - CELERY_WORKER_POOL=solo
      - CELERY_WORKER_CONCURRENCY=2
      
  frontend:
    volumes:
      - .\\src:/app/src
      - .\\public:/app/public
      - .\\package.json:/app/package.json
      - .\\next.config.js:/app/next.config.js
      
  postgres:
    volumes:
      - postgres_data:/var/lib/postgresql/data
      # Windows-compatible initialization
      - .\\database\\init.sql:/docker-entrypoint-initdb.d/init.sql
      
  redis:
    # Use Windows-compatible Redis settings
    command: >
      redis-server 
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
      --save 60 1000
      --appendonly yes

volumes:
  postgres_data:
    driver: local
'''
    
    try:
        with open("docker-compose.windows.yml", 'w', encoding='utf-8') as f:
            f.write(docker_override_content)
        print("   ✅ Created docker-compose.windows.yml")
        print("   ℹ️ Use: docker-compose -f docker-compose.yml -f docker-compose.windows.yml up -d")
    except Exception as e:
        print(f"   ❌ Failed to create Docker override: {e}")

def update_requirements_for_windows():
    """Update requirements.txt with Windows-compatible packages"""
    print("🔧 Updating requirements for Windows compatibility...")
    
    requirements_file = Path("backend/requirements.txt")
    if not requirements_file.exists():
        print("   ⚠️ requirements.txt not found")
        return
    
    try:
        with open(requirements_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Windows-specific package adjustments
        replacements = [
            # Use binary wheel for psycopg2 on Windows
            ('psycopg2==', 'psycopg2-binary=='),
            # Add Windows-specific packages if not present
        ]
        
        modified = False
        for old, new in replacements:
            if old in content and new not in content:
                content = content.replace(old, new)
                modified = True
        
        # Add Windows-specific packages
        windows_packages = [
            "# Windows-specific packages",
            "pywin32==306; sys_platform == 'win32'",
            "colorama==0.4.6; sys_platform == 'win32'",
        ]
        
        for package in windows_packages:
            if package not in content:
                content += f"\n{package}"
                modified = True
        
        if modified:
            with open(requirements_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print("   ✅ Updated requirements.txt for Windows")
        else:
            print("   ✅ requirements.txt already Windows-compatible")
            
    except Exception as e:
        print(f"   ❌ Failed to update requirements: {e}")

def main():
    """Run all Windows compatibility fixes"""
    print("🪟 Windows Compatibility Fixer")
    print("=" * 50)
    
    if not is_windows():
        print("ℹ️  Not running on Windows - applying cross-platform fixes only")
    else:
        print("✅ Running on Windows - applying Windows-specific fixes")
    
    print()
    
    # Apply fixes
    fixes = [
        fix_path_separators,
        create_windows_env_file,
        create_platform_detection,
        fix_celery_configuration,
        create_windows_docker_override,
        update_requirements_for_windows,
    ]
    
    for fix_func in fixes:
        try:
            fix_func()
        except Exception as e:
            print(f"❌ Error in {fix_func.__name__}: {e}")
        print()
    
    print("=" * 50)
    print("✅ Windows compatibility fixes completed!")
    print()
    print("Next steps:")
    print("1. Run: scripts\\windows_setup.bat")
    print("2. Edit .env file with your API keys")
    print("3. Start with: start_platform.bat")
    print("   OR use Docker: docker-compose -f docker-compose.yml -f docker-compose.windows.yml up -d")

if __name__ == "__main__":
    main()