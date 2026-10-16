"""Paper-only image presentation. Never rewrite the question bank or image files."""

import re

DEFAULT_IMAGE_SCALE = 70
MIN_IMAGE_SCALE = 20
MAX_IMAGE_SCALE = 150


def normalize_image_scale(value=None, *, default=DEFAULT_IMAGE_SCALE) -> int:
    """Accept bounded integer percentages, never CSS or TeX fragments."""
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("图片大小必须是 20–150 之间的整数百分比。")
    try:
        number = float(value)
        if not number.is_integer() or not MIN_IMAGE_SCALE <= number <= MAX_IMAGE_SCALE:
            raise ValueError
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("图片大小必须是 20–150 之间的整数百分比。") from exc
    return int(number)


def paper_image_factor(question: dict) -> float:
    # Direct library callers retain their old sizes; paper APIs supply 70%.
    return normalize_image_scale(question.get("paper_image_scale"), default=100) / 100


_IMAGE = r"!\[[^\]\r\n]*\]\([^)\r\n]+\)"
_PLAIN_IMAGE_CHOICES = re.compile(
    r"^[ \t]*A[.．、][ \t\r\n]*(" + _IMAGE + r")[ \t\r\n]+"
    r"B[.．、][ \t\r\n]*(" + _IMAGE + r")[ \t\r\n]+"
    r"C[.．、][ \t\r\n]*(" + _IMAGE + r")[ \t\r\n]+"
    r"D[.．、][ \t\r\n]*(" + _IMAGE + r")[ \t\r\n]*\Z",
    re.MULTILINE,
)


def normalize_paper_image_choices(content: str, question_type: str) -> str:
    """Recognize only a complete A/B/C/D image-only suffix in a choice question."""
    source = str(content or "")
    if question_type not in ("single_choice", "multi_choice"):
        return source
    if r"\begin{choices}" in source or "~~~" in source or chr(96) in source:
        return source
    match = _PLAIN_IMAGE_CHOICES.search(source)
    if not match:
        return source
    prefix = source[:match.start()]
    # Do not reinterpret labels inside authored TeX tables/math environments.
    if len(re.findall(r"\\begin\{", prefix)) != len(re.findall(r"\\end\{", prefix)):
        return source
    return prefix + "\\begin{choices}\n" + "\n".join(
        r"\item " + image for image in match.groups()
    ) + "\n\\end{choices}"


def scaled_cm(value: str, factor: float) -> str:
    """Scale a generated physical limit, leaving surrounding text untouched."""
    if factor == 1:
        return value
    return f"{float(value.removesuffix('cm')) * factor:.3f}".rstrip("0").rstrip(".") + "cm"
