"""Preview constant support must not alter authored physics export source."""

from copy import deepcopy

from mathbank.paper_helper import build_latex_document
from test_school_math_export import NATIVE, _compile_direct


CONTENT = (
    r"电流衰减 $i(t)=I_0\eu^{-t/\tau}$，其初始电流为 $I_0=3.00\,\mathrm{mA}$。"
    "\n\n"
    r"相位表示 $\tilde{I}=I_0\eu^{\iu\omega t}$；别名 $\upe^{\upi\omega t}$。"
    "\n\n"
    r"电荷 $e=1.60\times10^{-19}\,\mathrm{C}$；力 $\vec{F}=-2.00\,\mathrm{mN}\,\hat{x}$。"
)


def _physics_tex():
    questions = [{"question": {"id": 1, "question_type": "detailed_answer", "content": CONTENT}, "score": 10}]
    original = deepcopy(questions)
    tex = build_latex_document(
        "物理常数与变量验证", "", "quiz", questions,
        show_secret=False, show_notice=False,
    )
    assert questions == original
    return tex


def test_export_keeps_explicit_constants_variables_case_signs_and_precision():
    tex = _physics_tex()
    for formula in (
        r"i(t)=I_0\eu^{-t/\tau}", r"\eu^{\iu\omega t}", r"\upe^{\upi\omega t}",
        r"e=1.60\times10^{-19}\,\mathrm{C}", r"\vec{F}=-2.00\,\mathrm{mN}\,\hat{x}",
        r"I_0=3.00\,\mathrm{mA}",
    ):
        assert formula in tex
    assert r"\mathrm{i}(t)" not in tex
    assert r"\mathrm{e}=1.60" not in tex


@NATIVE
def test_native_examzh_physics_constants_with_variables_and_units(tmp_path):
    _compile_direct(_physics_tex(), tmp_path / "physics-constants")
