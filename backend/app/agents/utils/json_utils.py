"""
通用 JSON 解析工具：在保持错误透明的前提下，尽量做最小化修复。

设计目标：
- 统一剥离常见 Markdown 代码围栏（```json / ```）。
- 首次解析失败时输出简洁诊断（限长预览），便于快速定位问题根因。
- 提供轻量"修复策略"以兼容供应商偶发格式问题；策略分两类：
  1. 语法修复（syntax repair）：只修正 JSON 语法错误，不改变实际内容
     - 补齐未闭合的引号
     - 转义字符串内的裸换行/控制字符
     - 补齐缺失的闭括号/方括号
     - 移除尾随逗号
  2. 内容兜底（content fallback）：当语法修复无法挽救时替换为空骨架
     - 仅为兼容旧行为，生产环境建议关闭
"""

from __future__ import annotations

import json
from typing import Any, Optional


def safe_json_loads(
    raw: str,
    logger=None,
    context: str = "",
    allow_fallback: bool = False,
    allow_syntax_repair: bool = True,
) -> Any:
    """解析可能包含围栏/附加文本的 JSON 字符串。

    行为说明：
    - 先剥离三反引号围栏（```json / ```）。
    - 尝试直接 json.loads；失败则记录简洁诊断并尝试修复。
    - 修复成功则返回修复结果；否则抛出原始解析异常。

    参数：
    - allow_syntax_repair: 是否允许纯语法修复（补括号、转义控制字符等），
      不改变实际内容，默认开启。
    - allow_fallback: 是否允许内容兜底（提取最外层 JSON 对象等，可能丢弃上下文文本），默认关闭；
      仅在“允许兼容/降级”的非关键路径上开启。

    典型用法：
    - 关键路径（不允许内容丢失）：allow_syntax_repair=True, allow_fallback=False
    - 非关键路径（容忍降级）：allow_syntax_repair=True, allow_fallback=True
    - 严格模式（不做任何修复）：allow_syntax_repair=False, allow_fallback=False
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
        # 简洁诊断：长度与首尾预览
        if logger is not None:
            clen = len(content)
            head = content[:400].replace("\n", " ")
            tail = content[-160:].replace("\n", " ") if clen > 560 else ""
            ctx = f" [{context}]" if context else ""
            # 解析失败永远给出可审计信号；避免静默兜底掩盖上游问题
            getattr(logger, "warning", print)(
                "JSON parse failed%s: %s | len=%d | head=%r tail=%r",
                ctx,
                parse_error,
                clen,
                head,
                tail,
            )

        # 严格模式：禁止任何修复
        if not allow_syntax_repair and not allow_fallback:
            raise

        # 尝试修复
        repaired = _attempt_json_repair(
            content,
            parse_error,
            allow_syntax_repair=allow_syntax_repair,
            allow_fallback=allow_fallback,
        )
        if repaired:
            if logger:
                logger.info("JSON syntax repaired%s", f" [{context}]" if context else "")
            return json.loads(repaired)
        # 仍失败：抛原始异常，保持错误透明
        raise


# ===== 修复策略 =====

# 语法修复策略（不改变内容）
# 顺序重要：先处理字符串问题，再处理结构问题
_SYNTAX_REPAIR_STRATEGIES = [
    "_fix_unterminated_strings",
    "_escape_unescaped_newlines",
    "_quote_bare_book_titles",
    "_fix_trailing_commas",
    "_fix_missing_brackets_and_braces",  # 组合修复，确保顺序正确
]

# 内容兜底策略（会改变/截断内容）
_CONTENT_FALLBACK_STRATEGIES = [
    "_extract_complete_json_object",
]


def _attempt_json_repair(
    content: str,
    original_error: json.JSONDecodeError,
    *,
    allow_syntax_repair: bool,
    allow_fallback: bool,
) -> Optional[str]:
    strategies = []
    if allow_syntax_repair:
        strategies.extend(_SYNTAX_REPAIR_STRATEGIES)
    if allow_fallback:
        strategies.extend(_CONTENT_FALLBACK_STRATEGIES)

    for st_name in strategies:
        try:
            st_func = globals().get(st_name)
            if not st_func:
                continue
            repaired = st_func(content, original_error)
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


def _escape_unescaped_newlines(content: str, error: json.JSONDecodeError) -> Optional[str]:
    """将字符串字面量中的裸换行替换为 \\n，匹配供应商偶发返回。"""
    try:
        chars = []
        in_string = False
        escape = False
        prev_cr = False
        for ch in content:
            if in_string:
                if escape:
                    chars.append(ch)
                    escape = False
                    prev_cr = False
                    continue
                if ch == '\\':
                    chars.append(ch)
                    escape = True
                    prev_cr = False
                    continue
                if ch == '"':
                    in_string = False
                    chars.append(ch)
                    prev_cr = False
                    continue
                if ch == '\r':
                    chars.append('\\n')
                    prev_cr = True
                    continue
                if ch == '\n':
                    if prev_cr:
                        prev_cr = False
                        continue
                    chars.append('\\n')
                    prev_cr = False
                    continue
                prev_cr = False
                chars.append(ch)
            else:
                if ch == '"':
                    in_string = True
                chars.append(ch)
                prev_cr = False
        repaired = "".join(chars)
        if repaired != content:
            return repaired
        return None
    except Exception:
        return None


def _quote_bare_book_titles(content: str, error: json.JSONDecodeError) -> Optional[str]:
    """Wrap bare tokens containing 《》 with double quotes when outside strings."""
    try:
        out = []
        in_string = False
        escape = False
        i = 0
        length = len(content)

        while i < length:
            ch = content[i]
            if in_string:
                out.append(ch)
                if escape:
                    escape = False
                else:
                    if ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                i += 1
                continue

            if ch == '"':
                in_string = True
                out.append(ch)
                i += 1
                continue

            if ch in [":", ",", "["]:
                out.append(ch)
                i += 1
                while i < length and content[i].isspace():
                    out.append(content[i])
                    i += 1
                if i >= length:
                    break
                next_ch = content[i]
                if next_ch in ['"', "{", "["] or next_ch.isdigit() or next_ch in ["-"]:
                    continue
                if content.startswith("true", i) or content.startswith("false", i) or content.startswith("null", i):
                    continue

                j = i
                while j < length and content[j] not in [",", "]", "}"]:
                    j += 1
                raw = content[i:j]
                token = raw.strip()
                if token and "《" in token and "》" in token:
                    raw_rstrip = raw.rstrip()
                    trailing = raw[len(raw_rstrip):]
                    escaped = token.replace("\\", "\\\\").replace('"', '\\"')
                    out.append('"' + escaped + '"' + trailing)
                else:
                    out.append(raw)
                i = j
                continue

            out.append(ch)
            i += 1

        repaired = "".join(out)
        if repaired != content:
            return repaired
        return None
    except Exception:
        return None


def _fix_missing_brackets_and_braces(content: str, error: json.JSONDecodeError) -> Optional[str]:
    """补齐缺失的方括号和花括号。

    策略：计算开/闭括号差值，按不同顺序尝试补齐。
    """
    try:
        open_braces = content.count('{')
        close_braces = content.count('}')
        open_brackets = content.count('[')
        close_brackets = content.count(']')

        missing_braces = open_braces - close_braces
        missing_brackets = open_brackets - close_brackets

        if missing_braces <= 0 and missing_brackets <= 0:
            return None

        # 生成需要补齐的字符
        braces = '}' * max(0, missing_braces)
        brackets = ']' * max(0, missing_brackets)

        # 尝试不同的补齐顺序
        candidates = []
        if braces and brackets:
            # 两种顺序都尝试
            candidates.append(content + brackets + braces)
            candidates.append(content + braces + brackets)
        elif braces:
            candidates.append(content + braces)
        elif brackets:
            candidates.append(content + brackets)

        for candidate in candidates:
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue

        # 如果简单补齐不行，尝试交错补齐（针对嵌套场景）
        if missing_braces > 0 and missing_brackets > 0:
            # 尝试交错: ]}, ]}, ...
            interleaved = content
            for _ in range(min(missing_brackets, missing_braces)):
                interleaved += ']}'
            # 补齐剩余
            remaining_brackets = missing_brackets - min(missing_brackets, missing_braces)
            remaining_braces = missing_braces - min(missing_brackets, missing_braces)
            interleaved += ']' * remaining_brackets + '}' * remaining_braces
            try:
                json.loads(interleaved)
                return interleaved
            except json.JSONDecodeError:
                pass

        return None
    except Exception:
        return None


def _fix_trailing_commas(content: str, error: json.JSONDecodeError) -> Optional[str]:
    """移除对象/数组末尾的尾随逗号（JSON 标准不允许）。"""
    import re
    try:
        # 匹配 }, 或 ], 前面的尾随逗号（允许空白）
        repaired = re.sub(r',(\s*[}\]])', r'\1', content)
        if repaired != content:
            return repaired
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


#
# NOTE:
# - 不提供“内容骨架兜底”（如返回固定结构的空对象），否则会跨调用方污染数据形态并掩盖上游问题。
# - 如需业务级降级，应由调用方在边界处显式实现并记录 fallback_reason。


def to_jsonable(value: Any) -> Any:
    """Convert runtime objects into JSON-serializable primitives.

    This is a generic boundary adapter used by OBS/WM write paths.
    It avoids leaking runtime object representations (e.g. `<object at 0x...>`)
    into prompts and enables deterministic trimming/serialization.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    # Pydantic v2 BaseModel (ToolOutput) and similar objects
    try:
        if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
            return to_jsonable(value.model_dump())
    except Exception:
        pass
    # Pydantic v1 BaseModel
    try:
        if hasattr(value, "dict") and callable(getattr(value, "dict")):
            return to_jsonable(value.dict())
    except Exception:
        pass
    # Dataclasses
    try:
        import dataclasses as _dc

        if _dc.is_dataclass(value):
            return to_jsonable(_dc.asdict(value))
    except Exception:
        pass
    # Best-effort fallback: avoid embedding large reprs; stringify.
    try:
        return str(value)
    except Exception:
        return "<unstringifiable>"


def estimate_tokens(value: Any) -> int:
    """Heuristic token estimation for JSON-like content."""
    try:
        payload = to_jsonable(value)
        text = json.dumps(payload, ensure_ascii=False)
        return max(0, len(text) // 4)
    except Exception:
        return 0


def shrink_jsonable(
    value: Any,
    *,
    max_string_chars: int = 400,
    max_list_items: int = 50,
    max_dict_items: int = 60,
    max_depth: int = 6,
) -> Any:
    """Best-effort shrink for large JSON-like payloads.

    Generic truncation used when OBS payload exceeds budget. It does not rely on
    domain-specific keys and is safe to apply to any JSONable value.
    """
    if max_depth <= 0:
        return {"truncated": True}
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if max_string_chars > 0 and len(value) > max_string_chars:
            return value[:max_string_chars] + "...(truncated)"
        return value
    if isinstance(value, list):
        items = value[: max(0, int(max_list_items))]
        out = [shrink_jsonable(v, max_string_chars=max_string_chars, max_list_items=max_list_items, max_dict_items=max_dict_items, max_depth=max_depth - 1) for v in items]
        if len(value) > len(items):
            out.append({"truncated": True, "omitted_items": len(value) - len(items)})
        return out
    if isinstance(value, dict):
        keys = list(value.keys())[: max(0, int(max_dict_items))]
        out = {}
        for k in keys:
            out[str(k)] = shrink_jsonable(value.get(k), max_string_chars=max_string_chars, max_list_items=max_list_items, max_dict_items=max_dict_items, max_depth=max_depth - 1)
        if len(value) > len(keys):
            out["_truncated_meta"] = {"omitted_keys": len(value) - len(keys)}
        return out
    # If caller passes non-jsonable, convert then shrink.
    return shrink_jsonable(
        to_jsonable(value),
        max_string_chars=max_string_chars,
        max_list_items=max_list_items,
        max_dict_items=max_dict_items,
        max_depth=max_depth - 1,
    )


__all__ = [
    "safe_json_loads",
    "to_jsonable",
    "estimate_tokens",
    "shrink_jsonable",
]
