from __future__ import annotations

"""
静态守护：禁止生产代码重新引入短期记忆单例或直接暴露 MemoryManager。
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/
APP_ROOT = REPO_ROOT / "app"

# 允许出现 MemoryManager 的实现层路径前缀
ALLOWED_MM_PREFIXES = [
    APP_ROOT / "agents" / "memory" / "long_term",
    APP_ROOT / "agents" / "memory" / "managers",
    APP_ROOT / "agents" / "memory" / "services" / "long_term.py",
    APP_ROOT / "agents" / "memory" / "storage" / "slot",
    APP_ROOT / "services" / "memory_provider.py",
    APP_ROOT / "services" / "global_memory_service.py",
]

# 禁止恢复的单例 API 名称
FORBIDDEN_SINGLETON_SYMBOLS = ("get_working_memory_service", "get_memory_services")


def _is_allowed_mm_path(path: Path) -> bool:
    for prefix in ALLOWED_MM_PREFIXES:
        try:
            # prefix may be a file or directory
            if prefix.is_dir() and prefix in path.parents:
                return True
            if prefix.is_file() and path == prefix:
                return True
        except Exception:
            continue
    return False


def test_no_forbidden_singleton_symbols():
    offenders = []
    for py_file in APP_ROOT.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        for symbol in FORBIDDEN_SINGLETON_SYMBOLS:
            if symbol in text:
                offenders.append(f"{py_file}: contains {symbol}")
    assert not offenders, f"Forbidden singleton symbols found:\n" + "\n".join(offenders)


def test_no_memory_manager_exposure_in_app_layer():
    offenders = []
    for py_file in APP_ROOT.rglob("*.py"):
        if _is_allowed_mm_path(py_file):
            continue
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        if "MemoryManager" in text:
            offenders.append(str(py_file))
    assert not offenders, "MemoryManager should not appear outside implementation/allowed layers:\n" + "\n".join(offenders)
