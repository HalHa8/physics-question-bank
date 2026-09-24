"""Conservative normalization for mixed Chinese text and LaTeX math.

The AI import paths occasionally return valid LaTeX commands without math
delimiters.  This module repairs only high-confidence math-shaped runs while
leaving ordinary prose and document-structure commands untouched.
"""

from __future__ import annotations

import re
from collections.abc import Callable


_MATH_RUN_RE = re.compile(r"[A-Za-z0-9\\{}_^+\-*/=<>|(),.:\[\]\t ]+")
_MATH_COMMAND_RE = re.compile(r"\\([A-Za-z]+)")
_TABLE_ENVIRONMENTS = {
    "tabular", "tabular*", "tabularx", "longtable", "tblr", "longtblr", "talltblr",
}
# These environments already enter math mode. Adding dollars makes their
# otherwise valid source fail when it is later exported to LaTeX.
_STANDALONE_MATH_ENVIRONMENTS = {
    "equation", "equation*", "align", "align*", "alignat", "alignat*",
    "gather", "gather*", "multline", "multline*", "displaymath", "math",
}
_INNER_MATH_ENVIRONMENTS = {
    "cases", "aligned", "alignedat", "gathered", "matrix", "pmatrix",
    "bmatrix", "Bmatrix", "vmatrix", "Vmatrix", "smallmatrix", "array", "split",
}
_ENVIRONMENT_TOKEN_RE = re.compile(r"\\(begin|end)\{([^{}\n]+)\}")
_NON_MATH_COMMANDS = {
    "begin",
    "bottomrule",
    "centering",
    "cline",
    "end",
    "hline",
    "item",
    "fillin",
    "includegraphics",
    "midrule",
    "multicolumn",
    "multirow",
    "paren",
    "renewcommand",
    "textbf",
    "toprule",
}


def _replace_with_placeholders(
    value: str,
    pattern: re.Pattern[str],
    placeholders: list[tuple[str, str]],
    transform: Callable[[str], str] | None = None,
) -> str:
    def save(match: re.Match[str]) -> str:
        marker = f"\ue000{len(placeholders)}\ue001"
        original = match.group(0)
        placeholders.append((marker, transform(original) if transform else original))
        return marker

    return pattern.sub(save, value)


def _is_escaped(value: str, index: int) -> bool:
    cursor = index - 1
    while cursor >= 0 and value[cursor] == "\\":
        cursor -= 1
    return (index - cursor - 1) % 2 == 1


def _replace_delimited_math(value: str, replace: Callable[[str], str]) -> str:
    """Visit complete math spans without treating escaped dollars as delimiters."""
    parts: list[str] = []
    cursor = 0
    copied = 0
    while cursor < len(value):
        opening = next((token for token in ("$$", "$", r"\(", r"\[")
                        if value.startswith(token, cursor)), None)
        if opening is None or _is_escaped(value, cursor):
            cursor += 1
            continue
        closing = {r"\(": r"\)", r"\[": r"\]"}.get(opening, opening)
        end = value.find(closing, cursor + len(opening))
        while end >= 0 and _is_escaped(value, end):
            end = value.find(closing, end + len(closing))
        if end < 0:
            cursor += len(opening)
            continue
        end += len(closing)
        parts.extend((value[copied:cursor], replace(value[cursor:end])))
        cursor = copied = end
    parts.append(value[copied:])
    return "".join(parts)


def _replace_latex_environments(value: str, replace: Callable[[str, str], str]) -> str:
    """Protect complete outer structures, including nested cases/matrices/tables."""
    recognized = _TABLE_ENVIRONMENTS | _STANDALONE_MATH_ENVIRONMENTS | _INNER_MATH_ENVIRONMENTS
    parts: list[str] = []
    copied = 0
    cursor = 0
    while match := _ENVIRONMENT_TOKEN_RE.search(value, cursor):
        cursor = match.end()
        kind, name = match.groups()
        if kind != "begin" or name not in recognized or _is_escaped(value, match.start()):
            continue
        stack = [name]
        for token in _ENVIRONMENT_TOKEN_RE.finditer(value, cursor):
            if _is_escaped(value, token.start()):
                continue
            action, nested_name = token.groups()
            if action == "begin":
                stack.append(nested_name)
            elif nested_name != stack[-1]:
                break  # Preserve malformed structure; do not guess a repair.
            else:
                stack.pop()
            if not stack:
                parts.extend((value[copied:match.start()], replace(value[match.start():token.end()], name)))
                cursor = copied = token.end()
                break
    parts.append(value[copied:])
    return "".join(parts)


def _protect_non_candidates(value: str) -> tuple[str, Callable[[str], str]]:
    placeholders: list[tuple[str, str]] = []
    protected = value
    protected = _replace_with_placeholders(
        protected,
        re.compile(r"```[\s\S]*?```"),
        placeholders,
    )
    protected = _replace_with_placeholders(
        protected,
        re.compile(r"`[^`\n]*`"),
        placeholders,
    )
    protected = _replace_with_placeholders(
        protected,
        re.compile(r"!\[[^\]\n]*\]\([^\n)]*\)"),
        placeholders,
    )
    protected = _replace_with_placeholders(
        protected,
        re.compile(r"\[\[MBM_[A-Za-z0-9_:-]+\]\]"),
        placeholders,
    )
    protected = _replace_with_placeholders(
        protected,
        re.compile(r"\[ILLUSTRATION_BOX:\s*[^\]\n]*\]", re.IGNORECASE),
        placeholders,
    )
    def save(original: str) -> str:
        marker = f"\ue000{len(placeholders)}\ue001"
        placeholders.append((marker, original))
        return marker

    protected = _replace_delimited_math(protected, save)
    protected = _replace_latex_environments(
        protected,
        lambda environment, name: save(
            f"${environment}$" if name in _INNER_MATH_ENVIRONMENTS else environment
        ),
    )
    patterns = (
        re.compile(r"\\(?:begin|end)\{[^}\n]+\}"),
        re.compile(r"\\item\b"),
        re.compile(r"\\fillin\b"),
        re.compile(r"\\paren\b"),
        re.compile(r"\\textbf\{[^{}\n]*\}"),
        re.compile(r"\\includegraphics(?:\s*\[[^\]\n]*\])?\s*\{[^}\n]+\}"),
        re.compile(r"</?[A-Za-z][^>\n]*>"),
    )
    for pattern in patterns:
        protected = _replace_with_placeholders(protected, pattern, placeholders)

    def restore(result: str) -> str:
        for marker, original in reversed(placeholders):
            result = result.replace(marker, original)
        return result

    return protected, restore


def _is_high_confidence_math(value: str) -> bool:
    commands = {
        command.lower() for command in _MATH_COMMAND_RE.findall(value)
    } - _NON_MATH_COMMANDS
    if commands:
        return True
    if re.search(r"[A-Za-z0-9})\]]\s*[_^](?:\s*\{|\s*[A-Za-z0-9\\])", value):
        return True
    if re.search(
        r"[A-Za-z0-9})\]]\s*(?:=|<|>)\s*(?:[A-Za-z0-9({\[\\+\-])",
        value,
    ):
        return True
    if re.search(r"\b[A-Za-z]\s*\([^)]*[A-Za-z0-9_+\-,\\][^)]*\)", value):
        return True
    if re.search(r"\(\s*[+\-]?(?:\d+(?:\.\d+)?|[A-Za-z])\s*,[^)]*\)", value):
        return True
    return False


def _wrap_math_run(match: re.Match[str]) -> str:
    raw = match.group(0)
    leading_length = len(raw) - len(raw.lstrip())
    trailing_length = len(raw) - len(raw.rstrip())
    leading = raw[:leading_length]
    trailing = raw[len(raw) - trailing_length :] if trailing_length else ""
    core_end = len(raw) - trailing_length if trailing_length else len(raw)
    core = raw[leading_length:core_end]
    if not core or not _is_high_confidence_math(core):
        return raw
    return f"{leading}${core}${trailing}"


def normalize_question_math_markdown(value: str) -> str:
    """Wrap high-confidence naked LaTeX/math runs in inline delimiters.

    Existing math blocks, Markdown images, content-lock references, table
    environments and structural LaTeX commands are preserved byte-for-byte.
    Inner math environments are wrapped as a whole; standalone display math
    retains its original, exportable delimiters. Explicit typography such
    as ``\\mathbf`` or ``\\boldsymbol`` is never inferred from prose.
    """

    if not isinstance(value, str) or not value:
        return value or ""
    protected, restore = _protect_non_candidates(value)
    repaired_lines = [
        _MATH_RUN_RE.sub(_wrap_math_run, line)
        for line in protected.splitlines(keepends=True)
    ]
    return restore("".join(repaired_lines))
