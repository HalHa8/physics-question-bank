"""Deterministic document text helpers, independent of the application and AI."""

import re


def normalize_fillin_macro(text: str) -> str:
    """Normalize proven blank lines; preserve literal TeX, subscripts and macros.

    Keep the legacy callable available to internal tools; new math-shell
    handling lives in the shared backend module and never migrates old rows.
    """
    if not text or not isinstance(text, str):
        return text or ""
    spans = []

    def escaped(position):
        previous = position - 1
        while previous >= 0 and text[previous] == "\\":
            previous -= 1
        return (position - previous - 1) % 2 == 1

    def covered(position):
        return any(start <= position < end for start, end, _ in spans)

    def group_end(position):
        stack = ["]" if text[position] == "[" else "}"]
        for index in range(position + 1, len(text)):
            if escaped(index):
                continue
            char = text[index]
            if char in "[{":
                stack.append("]" if char == "[" else "}")
            elif char in "]}":
                if char != stack[-1]:
                    return len(text)
                stack.pop()
                if not stack:
                    return index + 1
        return len(text)

    # Code/HTML literals, links, URLs and asset paths cannot supply blank lines.
    literal = re.compile(
        r"<(?P<literal_tag>code|pre|mathbank-math)\b[^>]*>[\s\S]*?</(?P=literal_tag)\s*>|<!--[\s\S]*?(?:-->|\Z)|"
        r"!?\[[^\]\n]*\]\([^\n)]*\)|(?:https?|ftp)://[^\s<>\"']+|"
        r"</?[A-Za-z][A-Za-z0-9:_-]*(?:\s+[^<>]*|/?)>", re.IGNORECASE)
    spans.extend((m.start(), m.end(), None) for m in literal.finditer(text))
    cursor = 0
    while match := re.search(r"`+|(?m:^[ \t]{0,3}~{3,})", text[cursor:]):
        start, end = cursor + match.start(), cursor + match.end()
        token = match.group().lstrip(" \t")
        if covered(start) or escaped(start):
            cursor = end
            continue
        line_start = text.rfind("\n", 0, start) + 1
        fence = len(token) >= 3 and not text[line_start:start].strip()
        if fence:
            newline = text.find("\n", end)
            body = newline + 1 if newline >= 0 else len(text)
            closing = re.search(r"(?m)^[ \t]{0,3}" + re.escape(token[0]) + "{" + str(len(token)) + r",}[ \t]*(?:\n|\Z)", text[body:])
            end = body + closing.end() if closing else len(text)
        else:
            closing = next((m for m in re.finditer(r"`+", text[end:]) if len(m.group()) == len(token)), None)
            end = end + closing.end() if closing else len(text)
        spans.append((start, end, None))
        cursor = end
    # Conservatively retain Markdown indented code. Lists' own content stays
    # active; four additional columns establish an indented literal block.
    offset, previous_blank, code_start, list_indent = 0, True, None, None
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        leading = re.match(r"[ \t]*", body).group()
        indent = len(leading.expandtabs(4))
        marker = re.match(r"(?:[-+*]|[0-9]{1,9}[.)])[ \t]+", body[len(leading):])
        threshold = list_indent + 4 if list_indent is not None else 4
        if not body.strip():
            previous_blank = True
        elif indent >= threshold and (previous_blank or code_start is not None):
            if code_start is None:
                code_start = offset
            previous_blank = False
        else:
            if code_start is not None:
                spans.append((code_start, offset, None))
                code_start = None
            if marker:
                list_indent = indent + len(marker.group().expandtabs(4))
            elif indent < 4:
                list_indent = None
            previous_blank = False
        offset += len(line)
    if code_start is not None:
        spans.append((code_start, len(text), None))

    environments = re.compile(r"\\begin\s*\{(tikzpicture|verbatim\*?|Verbatim\*?|lstlisting|minted)\}")
    for match in environments.finditer(text):
        if covered(match.start()) or escaped(match.start()):
            continue
        closing = re.search(r"\\end\s*\{" + re.escape(match.group(1)) + r"\}", text[match.end():])
        spans.append((match.start(), match.end() + closing.end() if closing else len(text), None))
    commands = re.compile(r"\\(verb|Verb|lstinline|mintinline|detokenize|texttt|url|path|includegraphics|fillin|underline)(?![A-Za-z])\*?")
    for match in commands.finditer(text):
        if covered(match.start()):
            continue
        name, cursor = match.group(1), match.end()
        while cursor < len(text) and text[cursor] in " \t":
            cursor += 1
        if name in {"verb", "Verb", "lstinline", "mintinline"}:
            if cursor < len(text) and text[cursor] == "[":
                cursor = group_end(cursor)
            if name == "mintinline" and text[cursor:cursor + 1] == "{":
                cursor = group_end(cursor)
            while cursor < len(text) and text[cursor] in " \t":
                cursor += 1
            if cursor < len(text) and not text[cursor].isspace():
                if text[cursor] == "{":
                    end = group_end(cursor)
                else:
                    closing = text.find(text[cursor], cursor + 1)
                    end = closing + 1 if closing >= 0 else len(text)
                spans.append((match.start(), end, None))
            continue
        arguments, end = [], match.end()
        while cursor < len(text) and text[cursor] in "[{":
            stop = group_end(cursor)
            arguments.append((cursor, stop))
            end = stop
            cursor = stop
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
        replacement = None
        if name == "underline" and not escaped(match.start()) and len(arguments) == 1:
            left, right = arguments[0]
            if text[left] == "{" and text[right - 1:right] == "}":
                inner = text[left + 1:right - 1]
                blank = re.fullmatch(r"(?:\s|_|\\_|~|\\(?:quad|qquad|strut)|\\hspace\{[0-9.]+(?:cm|mm|pt|em|ex|in)\})*", inner)
                if blank:
                    replacement = r"\fillin"
        # Preserve explicit fillin parameters/braces and nonblank underline.
        spans.append((match.start(), end, replacement))

    # An underscore inside a real subscript group is not an inferred blank.
    stack = []
    for index, char in enumerate(text):
        if char not in "{}" or escaped(index) or covered(index):
            continue
        if char == "{":
            stack.append((index, index > 0 and text[index - 1] == "_" and not escaped(index - 1)))
        elif stack:
            start, is_subscript = stack.pop()
            if is_subscript:
                spans.append((start + 1, index, None))
    spans.extend((start + 1, len(text), None) for start, is_subscript in stack if is_subscript)

    def normalize_segment(segment, base):
        def blank(match):
            start, end = base + match.start(), base + match.end()
            if escaped(start):
                return match.group()
            left = text[start - 1:start]
            right = text[end:end + 1]
            if re.fullmatch(r"[A-Za-z0-9_\u0370-\u03ff]", left) or re.fullmatch(r"[A-Za-z0-9_\u0370-\u03ff]", right):
                return match.group()
            if match.group().startswith("\\") and len(match.group()) < 6:
                # Single/double escaped glyphs need a declared value slot. This
                # covers the real textbook S_n = \_ without guessing literal _.
                before = text[max(0, start - 24):start].rstrip()
                after = text[end:]
                if not re.search(r"(?:=|为|是|等于|填写)\s*$", before) or not re.match(r"\s*(?:\$|\\[)\]]|[。，,；;.!?！？]|\Z)", after):
                    return match.group()
            return r"\fillin"
        return re.sub(r"(?:\\_)+|_{3,}", blank, segment)

    result, cursor = [], 0
    for start, end, replacement in sorted(spans, key=lambda row: (row[0], -row[1])):
        if start < cursor:
            continue
        result.append(normalize_segment(text[cursor:start], cursor))
        result.append(text[start:end] if replacement is None else replacement)
        cursor = end
    result.append(normalize_segment(text[cursor:], cursor))
    from mathbank.fillin import normalize_fillin_math_wrappers
    from mathbank.fillin_placeholders import normalize_fillin_placeholder_clusters
    return normalize_fillin_placeholder_clusters(normalize_fillin_math_wrappers("".join(result)))


def extract_title_from_latex(latex: str) -> str:
    """从 LaTeX 源码中尝试自动提取试卷标题"""
    if not latex:
        return ""
    import re

    def clean_latex(txt: str) -> str:
        # 移除字体大小命令等
        txt = re.sub(r'\\(large|Large|LARGE|huge|Huge|small|bf|bfseries|it|itshape|sf|tt|heiti|kaishu|fangsong|songti)', '', txt)
        # 解包 textbf 等
        txt = re.sub(r'\\text(bf|it|sf|tt)?\s*\{([^}]+)\}', r'\2', txt)
        txt = txt.replace('{', '').replace('}', '').replace('\\\\', '\n').strip()
        lines = [line.strip() for line in txt.split('\n') if line.strip()]
        if lines:
            return lines[0][:60]
        return ""

    # 1. 尝试匹配 \title{...}
    match = re.search(r'\\title\s*\{([^}]+)\}', latex)
    if match:
        cleaned = clean_latex(match.group(1))
        if cleaned:
            return cleaned

    # 2. 尝试匹配 \chead{...}
    match = re.search(r'\\chead\s*\{([^}]+)\}', latex)
    if match:
        cleaned = clean_latex(match.group(1))
        if cleaned and "页" not in cleaned and "绝密" not in cleaned:
            return cleaned

    # 3. 尝试匹配 \begin{center} ... \end{center} 头部区域
    top_part = latex[:1500]
    match = re.search(r'\\begin\s*\{center\}([\s\S]*?)\\end\s*\{center\}', top_part)
    if match:
        cleaned = clean_latex(match.group(1))
        if cleaned:
            return cleaned

    return ""


def process_ocr_illustrations(text: str) -> str:
    """(已关闭 AI 自动插图裁剪) 仅进行安全标签清洗，擦除任何潜在的视觉定位标签或 box 坐标标记，返回纯净 OCR 结果"""
    import re
    if not text:
        return text

    # 1. 擦除 Qwen 视觉定位标签: <|box_start|>(ymin,xmin,ymax,xmax)<|box_end|>
    cleaned = re.sub(r"(?i)<\|box_start\|>.*?<\|box_end\|>", "", text)

    # 2. 擦除 ILLUSTRATION_BOX 标签: [ILLUSTRATION_BOX: ymin, xmin, ymax, xmax]
    cleaned = re.sub(r"(?i)\[ILLUSTRATION_BOX:.*?\]", "", cleaned)
    cleaned = re.sub(r"(?i)ILLUSTRATION_BOX\s*[:：\(（\[\s]*[^\]\)\n\r]+[\s\]\)]*", "", cleaned)

    return cleaned.strip()


def find_source_page_by_overlap(q_text: str, ocr_results: list) -> int:
    """利用 3-shingle（三字符切片）特征重合度，计算题目最可能所属的 PDF 原始物理页码"""
    if not q_text or not ocr_results:
        return 0

    import re
    def clean_for_compare(t: str) -> str:
        # 仅保留中文字符、英文字母和数字，过滤掉干扰公式渲染的标点符号
        return "".join(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]', t))

    cleaned_q = clean_for_compare(q_text)
    if not cleaned_q:
        return 0

    best_page = 0
    max_overlap = -1

    for idx, page_text in enumerate(ocr_results):
        if not page_text:
            continue
        cleaned_page = clean_for_compare(page_text)

        # 构建 3-shingle 切片集合
        if len(cleaned_q) >= 3:
            shingles_q = set(cleaned_q[i:i+3] for i in range(len(cleaned_q)-2))
        else:
            shingles_q = {cleaned_q}

        if len(cleaned_page) >= 3:
            shingles_page = set(cleaned_page[i:i+3] for i in range(len(cleaned_page)-2))
        else:
            shingles_page = {cleaned_page}

        overlap = len(shingles_q.intersection(shingles_page))
        if overlap > max_overlap:
            max_overlap = overlap
            best_page = idx

    return best_page


def parse_page_range(range_str: str, total_pages: int) -> list:
    """
    解析用户输入的页码范围字符串（1-indexed），转换为包含 0-indexed 页面索引的列表。
    支持格式如 "1-5", "1,3,5", "1-3,5,7-9"。
    """
    if total_pages <= 0:
        raise ValueError("PDF 没有有效页面。")
    if not range_str or not range_str.strip():
        return list(range(total_pages))

    pages = set()
    parts = str(range_str).replace(" ", "").split(",")
    for part in parts:
        if not part:
            raise ValueError("页码范围格式无效。")
        if "-" in part:
            sub_parts = part.split("-")
            if len(sub_parts) != 2:
                raise ValueError("页码范围格式无效。")
            try:
                start = int(sub_parts[0])
                end = int(sub_parts[1])
            except ValueError as exc:
                raise ValueError("页码范围必须使用数字。") from exc
            if start < 1 or end < start or end > total_pages:
                raise ValueError(f"页码范围必须位于 1 到 {total_pages}。")
            pages.update(range(start - 1, end))
        else:
            try:
                page_number = int(part)
            except ValueError as exc:
                raise ValueError("页码范围必须使用数字。") from exc
            if page_number < 1 or page_number > total_pages:
                raise ValueError(f"页码范围必须位于 1 到 {total_pages}。")
            pages.add(page_number - 1)

    if not pages:
        raise ValueError("页码范围不能为空。")
    return sorted(pages)
