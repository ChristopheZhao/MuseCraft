#!/usr/bin/env python3
"""
Quick fixes for common issues
"""

import os
import sys
import subprocess
from pathlib import Path

def run_command(command, description):
    """Run a command and report results"""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"   ✅ {description} completed successfully")
            return True
        else:
            print(f"   ❌ {description} failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"   ❌ {description} failed with exception: {e}")
        return False

def create_directories():
    """Create necessary directories"""
    print("📁 Creating necessary directories...")
    
    directories = [
        "backend/storage/uploads",
        "backend/storage/generated", 
        "backend/storage/temp",
        "backend/logs",
        "test_results"
    ]
    
    for directory in directories:
        dir_path = Path(directory)
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"   ✅ Created directory: {directory}")
        except Exception as e:
            print(f"   ❌ Failed to create directory {directory}: {e}")

def install_backend_dependencies():
    """Install backend Python dependencies"""
    print("🐍 Installing backend dependencies...")
    
    # Change to backend directory
    backend_dir = Path("backend")
    if not backend_dir.exists():
        print("   ❌ Backend directory not found")
        return False
    
    os.chdir(backend_dir)
    
    # Install dependencies
    commands = [
        ("pip install -r requirements.txt", "Installing Python packages"),
        ("pip install --upgrade jinja2 pyyaml", "Updating template dependencies")
    ]
    
    success = True
    for command, description in commands:
        if not run_command(command, description):
            success = False
    
    os.chdir("..")
    return success

def install_frontend_dependencies():
    """Install frontend Node.js dependencies"""
    print("📦 Installing frontend dependencies...")
    
    # Check if package.json exists
    if not Path("package.json").exists():
        print("   ❌ package.json not found")
        return False
    
    commands = [
        ("npm install", "Installing Node.js packages"),
        ("npm audit fix --force", "Fixing security vulnerabilities")
    ]
    
    success = True
    for command, description in commands:
        if not run_command(command, description):
            # npm audit fix failing is not critical
            if "audit fix" not in command:
                success = False
    
    return success

def setup_environment():
    """Setup environment file"""
    print("🌱 Setting up environment...")
    
    if not Path(".env").exists():
        if Path(".env.example").exists():
            try:
                import shutil
                shutil.copy(".env.example", ".env")
                print("   ✅ Created .env from .env.example")
                print("   ⚠️ Please edit .env and add your API keys")
            except Exception as e:
                print(f"   ❌ Failed to create .env: {e}")
        else:
            print("   ❌ .env.example not found")
    else:
        print("   ✅ .env already exists")

def check_docker():
    """Check Docker availability"""
    print("🐳 Checking Docker...")
    
    if run_command("docker --version", "Checking Docker installation"):
        if run_command("docker-compose --version", "Checking Docker Compose"):
            print("   ✅ Docker environment ready")
            return True
    
    print("   ⚠️ Docker not available - manual setup required")
    return False

def run_validation():
    """Run system validation"""
    print("🔍 Running system validation...")
    
    validation_script = Path("backend/scripts/validate_system.py")
    if validation_script.exists():
        os.chdir("backend")
        success = run_command(
            "python scripts/validate_system.py", 
            "Running system validation"
        )
        os.chdir("..")
        return success
    else:
        print("   ❌ Validation script not found")
        return False

def main():
    """Main quick fix function"""
    print("🚀 Running Quick Fixes for Short Video Maker Platform\n")
    
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    fixes_applied = []
    fixes_failed = []
    
    # List of fixes to apply
    fixes = [
        (create_directories, "Create directories"),
        (setup_environment, "Setup environment"),
        (install_backend_dependencies, "Install backend dependencies"),
        (install_frontend_dependencies, "Install frontend dependencies"),
        (check_docker, "Check Docker (optional)"),
        (run_validation, "Run system validation")
    ]
    
    # Apply fixes
    for fix_func, fix_name in fixes:
        try:
            if fix_func():
                fixes_applied.append(fix_name)
            else:
                fixes_failed.append(fix_name)
        except Exception as e:
            print(f"   ❌ {fix_name} failed with exception: {e}")
            fixes_failed.append(fix_name)
        print()
    
    # Summary
    print("="*60)
    print("📊 QUICK FIXES SUMMARY")
    print("="*60)
    
    if fixes_applied:
        print(f"\n✅ Successfully Applied ({len(fixes_applied)}):")
        for fix in fixes_applied:
            print(f"   • {fix}")
    
    if fixes_failed:
        print(f"\n❌ Failed to Apply ({len(fixes_failed)}):")
        for fix in fixes_failed:
            print(f"   • {fix}")
    
    print(f"\n💡 Next Steps:")
    if fixes_failed:
        print("   1. Review failed fixes above")
        print("   2. Install missing dependencies manually")
        print("   3. Check your .env file and add required API keys")
    else:
        print("   1. Edit .env file and add your API keys (especially OPENAI_API_KEY)")
        print("   2. Start services with: docker-compose up -d")
        print("   3. Or run manually:")
        print("      Backend: cd backend && python -m app.main")
        print("      Frontend: npm run dev")
    
    print("="*60)
    
    # Return appropriate exit code
    if len(fixes_failed) > len(fixes_applied):
        return 1
    else:
        return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)