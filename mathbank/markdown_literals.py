"""Literal-range scanner adapted from MathBank (AGPL-3.0); no asset writes."""

import re

_IMAGE = re.compile(
    r'!\[(?:\\.|[^\]\\])*\]\(\s*(?:<(?P<angle>[^>\n]+)>|(?P<markdown>[^\s)]+))(?:[ \t]+[^)\n]*)?\s*\)'
    r'|\\includegraphics\*?\s*(?:\[[^\]]*\]\s*)?\{(?P<latex>[^{}]+)\}'
    r'''|<img\b[^>]*?\bsrc\s*=\s*(?:"(?P<html_double>[^"]+)"|'(?P<html_single>[^']+)'|(?P<html_bare>[^\s>]+))[^>]*>''',
    re.IGNORECASE,
)

def markdown_literal_ranges(text: str, *, include_links=True) -> list[tuple[int, int]]:
    """Locate Markdown literal examples without treating list continuations as code.

    Image discovery excludes links from this mask. Formula locking includes
    them, so dollars in examples, URLs, and image filenames remain literal.
    """
    value = str(text or "")
    ranges = [match.span() for match in re.finditer(
        r"<!--[\s\S]*?(?:-->|$)|<(pre|code)\b[^>]*>[\s\S]*?(?:</\1\s*>|$)",
        value, re.IGNORECASE,
    )]

    def covered(position):
        return any(start <= position < end for start, end in ranges)

    opened = None
    for marker in re.finditer(r"^ {0,3}(`{3,}|~{3,})[^\n]*$", value, re.MULTILINE):
        if covered(marker.start()):
            continue
        fence = marker.group(1)
        if opened is None:
            opened = (marker.start(), fence[0], len(fence))
        elif (fence[0] == opened[1] and len(fence) >= opened[2]
              and re.fullmatch(r" {0,3}" + re.escape(fence[0]) + r"{" + str(opened[2]) + r",}[ \t]*", marker.group())):
            ranges.append((opened[0], marker.end()))
            opened = None
    if opened:
        ranges.append((opened[0], len(value)))

    # A blank line or document start establishes a top-level indented code
    # block. Under an active list, ordinary continuation indentation remains
    # visible; only four additional columns establish a code block.
    offset, block_start, previous_blank, list_content_indent = 0, None, True, None
    for line in value.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if covered(offset):
            if block_start is not None:
                ranges.append((block_start, offset))
                block_start = None
            previous_blank = not body.strip()
            offset += len(line)
            continue
        if not body.strip():
            previous_blank = True
            offset += len(line)
            continue
        leading = re.match(r"[ \t]*", body).group()
        indent = len(leading.expandtabs(4))
        marker = re.match(r"(?:[-+*]|\d{1,9}[.)])[ \t]+", body[len(leading):])
        code_indent = (list_content_indent + 4) if list_content_indent is not None else 4
        if (marker and (indent < 4 or list_content_indent is not None)
                and not (indent >= code_indent and (previous_blank or block_start is not None))):
            if block_start is not None:
                ranges.append((block_start, offset))
                block_start = None
            list_content_indent = indent + len(marker.group().expandtabs(4))
        else:
            if indent >= code_indent and (previous_blank or block_start is not None):
                if block_start is None:
                    block_start = offset
            else:
                if block_start is not None:
                    ranges.append((block_start, offset))
                    block_start = None
                if indent < 4:
                    list_content_indent = None
        previous_blank = False
        offset += len(line)
    if block_start is not None:
        ranges.append((block_start, len(value)))

    cursor = 0
    while marker := re.search(r"`+", value[cursor:]):
        start, end = cursor + marker.start(), cursor + marker.end()
        if covered(start) or _escaped(value, start):
            cursor = end
            continue
        closing = next((match for match in re.finditer(r"`+", value[end:])
                        if len(match.group()) == end - start), None)
        if closing is not None:
            end += closing.end()
            ranges.append((start, end))
        cursor = end
    if include_links:
        ranges.extend(match.span() for match in _IMAGE.finditer(value)
                      if not covered(match.start()) and not _escaped(value, match.start()))
        for pattern in (r"!?\[[^\[\]\n]*\]\([^\n)]*\)", r"(?:https?|ftp)://[^\s<>]+"):
            ranges.extend(match.span() for match in re.finditer(pattern, value, re.IGNORECASE)
                          if not covered(match.start()) and not _escaped(value, match.start()))
    return sorted(set(ranges))


def _escaped(value, start):
    cursor = start - 1
    while cursor >= 0 and value[cursor] == "\\":
        cursor -= 1
    return (start - cursor - 1) % 2 == 1
