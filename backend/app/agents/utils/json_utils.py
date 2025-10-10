"""
通用 JSON 解析工具：在保持错误透明的前提下，尽量做最小化修复。

设计目标：
- 统一剥离常见 Markdown 代码围栏（```json / ```）。
- 首次解析失败时输出简洁诊断（限长预览），便于快速定位问题根因。
- 提供轻量“修复策略”以兼容供应商偶发格式问题；策略尽量保守。
- 维持现有行为的兼容性（包括兜底空骨架的策略），具体是否启用可后续通过配置开关治理。
"""

from __future__ import annotations

import json
from typing import Any, Optional


def safe_json_loads(raw: str, logger=None, context: str = "") -> Any:
    """解析可能包含围栏/附加文本的 JSON 字符串。

    行为说明：
    - 先剥离三反引号围栏（```json / ```）。
    - 尝试直接 json.loads；失败则记录简洁诊断并尝试修复。
    - 修复成功则返回修复结果；否则抛出原始解析异常。

    提示：
    - 本方法延续了旧实现的“兜底空骨架”修复策略（create_fallback_concept），
      以保证兼容现有流程；是否保留该修复可在后续迭代按配置开关控制。
    """
    content = (raw or "").strip()
    # 兼容：既处理 ```json 也处理裸 ```
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]

    try:
        return json.loads(content)
    except json.JSONDecodeError as parse_error:
        # 简洁诊断：长度与首尾预览，避免日志刷屏
        if logger:
            clen = len(content)
            head = content[:400].replace("\n", " ")
            tail = content[-160:].replace("\n", " ") if clen > 560 else ""
            ctx = f" [{context}]" if context else ""
            logger.debug(
                "JSON parse failed%s: %s | len=%d | head=%r tail=%r",
                ctx,
                parse_error,
                clen,
                head,
                tail,
            )

        repaired = _attempt_json_repair(content, parse_error)
        if repaired:
            return json.loads(repaired)
        # 仍失败：抛原始异常，保持错误透明
        raise


# ===== 轻量修复策略（与旧实现保持一致，便于平滑迁移） =====

def _attempt_json_repair(content: str, original_error: json.JSONDecodeError) -> Optional[str]:
    strategies = [
        _fix_unterminated_strings,
        _fix_missing_closing_braces,
        _extract_complete_json_object,
        _create_fallback_concept,
    ]
    for st in strategies:
        try:
            repaired = st(content, original_error)  # type: ignore[arg-type]
            if repaired:
                # 二次确认
                json.loads(repaired)
                return repaired
        except Exception:
            continue
    return None


def _fix_unterminated_strings(content: str, error: json.JSONDecodeError) -> Optional[str]:
    try:
        repaired = content
        # 简单策略：若引号数为奇数，补一个引号
        if repaired.count('"') % 2 != 0:
            repaired += '"'
        return repaired
    except Exception:
        return None


def _fix_missing_closing_braces(content: str, error: json.JSONDecodeError) -> Optional[str]:
    try:
        open_braces = content.count('{')
        close_braces = content.count('}')
        if open_braces > close_braces:
            return content + ('}' * (open_braces - close_braces))
        return None
    except Exception:
        return None


def _extract_complete_json_object(content: str, error: json.JSONDecodeError) -> Optional[str]:
    try:
        # 仅提取最外层完整的 {...} 对象（不处理顶层数组，保持与旧实现一致）
        brace_count = 0
        start_pos = content.find('{')
        if start_pos == -1:
            return None
        for i, ch in enumerate(content[start_pos:], start_pos):
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    return content[start_pos : i + 1]
        return None
    except Exception:
        return None


def _create_fallback_concept(content: str, error: json.JSONDecodeError) -> Optional[str]:
    """兜底：返回最小可序列化对象（与原实现一致）。

    注意：此策略仅为兼容旧行为，可能掩盖上游格式问题；
    后续可通过配置关闭该策略，改为直接报错。
    """
    try:
        fallback = {
            "overview": "Generated video concept",
            "scene_blueprint": [],
        }
        return json.dumps(fallback)
    except Exception:
        return None
