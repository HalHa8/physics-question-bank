"""Pure helpers for question form detection and paper type grouping."""

import re


PAPER_TYPE_ORDER = ("single_choice", "multi_choice", "fill_in_blank", "detailed_answer")


def normalize_section_order(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(item for item in value if isinstance(item, str) and item))


def paper_type_order(present_types, paper_type: str, question_types=None, section_order=None) -> list[str]:
    """Use saved section order, appending any types that were added afterwards."""
    order = list(PAPER_TYPE_ORDER)
    if paper_type == "exam_19":
        return order
    present = list(dict.fromkeys(present_types))
    for item in question_types or []:
        value = item.get("value") if isinstance(item, dict) else None
        if isinstance(value, str) and value in present and value not in order:
            order.append(value)
    order.extend(value for value in present if value not in order)
    preferred = normalize_section_order(section_order)
    return preferred + [value for value in order if value not in preferred]


def custom_type_labels(question_types=None) -> dict[str, str]:
    """Custom labels are plain text; each output format must escape them itself."""
    labels = {}
    for item in question_types or []:
        if not isinstance(item, dict):
            continue
        value, label = item.get("value"), item.get("label")
        if isinstance(value, str) and isinstance(label, str) and label.strip():
            labels.setdefault(value, label)
    return labels


def is_written_question_type(q_type: str) -> bool:
    return q_type not in ("single_choice", "multi_choice", "fill_in_blank")


QUESTION_FORM_CHOICE = "choice"
QUESTION_FORM_FILL_IN_BLANK = "fill_in_blank"
QUESTION_FORM_DETAILED_ANSWER = "detailed_answer"
QUESTION_FORM_UNKNOWN = "unknown"


_CHOICES_ENV_PATTERN = re.compile(
    r"\\begin\s*\{\s*choices\s*\}",
    re.IGNORECASE,
)
_FILLIN_PATTERN = re.compile(r"\\fillin\b", re.IGNORECASE)


def detect_structured_question_form(content: str) -> str | None:
    """Return a definitive form only when normalized LaTeX structure proves it.

    A choices environment takes precedence because a choice option can itself
    contain a blank-like expression without changing the enclosing question
    into a fill-in-the-blank item.
    """

    normalized = str(content or "")
    if _CHOICES_ENV_PATTERN.search(normalized):
        return QUESTION_FORM_CHOICE
    if _FILLIN_PATTERN.search(normalized):
        return QUESTION_FORM_FILL_IN_BLANK
    return None


def normalize_ai_question_form(value: object) -> str:
    """Collapse model output to a coarse form that cannot encode single/multi."""

    normalized = str(value or "").strip().lower()
    mapping = {
        "choice": QUESTION_FORM_CHOICE,
        "choice_question": QUESTION_FORM_CHOICE,
        "single_choice": QUESTION_FORM_CHOICE,
        "multi_choice": QUESTION_FORM_CHOICE,
        "选择题": QUESTION_FORM_CHOICE,
        "单选题": QUESTION_FORM_CHOICE,
        "多选题": QUESTION_FORM_CHOICE,
        "fill_in_blank": QUESTION_FORM_FILL_IN_BLANK,
        "fill-in-blank": QUESTION_FORM_FILL_IN_BLANK,
        "填空题": QUESTION_FORM_FILL_IN_BLANK,
        "detailed_answer": QUESTION_FORM_DETAILED_ANSWER,
        "解答题": QUESTION_FORM_DETAILED_ANSWER,
        "计算题": QUESTION_FORM_DETAILED_ANSWER,
        "experiment": "experiment",
        "实验题": "experiment",
        "short_answer": "short_answer",
        "简答题": "short_answer",
        "unknown": QUESTION_FORM_UNKNOWN,
        "未知": QUESTION_FORM_UNKNOWN,
    }
    return mapping.get(normalized, QUESTION_FORM_UNKNOWN)
