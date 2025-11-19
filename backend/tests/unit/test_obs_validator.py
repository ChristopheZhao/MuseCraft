import os
import sys
import json

# 确保 backend 包可导入
CURRENT_DIR = os.path.dirname(__file__)
BACKEND_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.append(BACKEND_ROOT)

from app.agents.utils.obs_validator import parse_and_validate_structured  # type: ignore


def test_parse_and_validate_non_strict_missing_scenes_returns_none():
    """在非严格模式下，若 schema 声明了 scenes 但内容缺失，应返回 None（而非抛错）。"""
    # 给定内容不包含 scenes
    content = json.dumps({"foo": 1}, ensure_ascii=False)
    # schema 的 properties 声明了 scenes 键
    schema = {
        "type": "object",
        "properties": {
            "scenes": {"type": "array"},
        },
    }

    result = parse_and_validate_structured(
        content=content,
        schema=schema,
        strict=False,  # 非严格：不抛异常，返回 None
        logger=None,
        context="test_structured_observation",
        require_scenes_if_declared=True,
    )

    assert result is None

