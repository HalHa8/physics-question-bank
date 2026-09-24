"""MTEF tab stops are layout data, never printable formula characters."""

from pathlib import Path
import struct

import pytest

from mathbank.mtef_helper import decode_mtef_formula


HEADER = b"\x05\x01\x00\x07\x00DSMT7\x00\x00"
TABBED_INTERVAL = bytes.fromhex(
    (Path(__file__).parent / "fixtures/mtef/tabbed_interval.hex").read_text()
)


def _char(value):
    return b"\x02\x00\x83" + struct.pack("<H", ord(value))


def _ruler(count):
    return bytes([count]) + b"".join(
        bytes([index % 5]) + struct.pack("<H", (index + 1) * 32)
        for index in range(count)
    )


@pytest.mark.parametrize("count", [0, 1, 7])
@pytest.mark.parametrize("extra_options,prefix", [(0, b""), (0x0C, b"\x80\x81\x40\x00")])
def test_line_embeds_ruler_body_without_a_record_tag(count, extra_options, prefix):
    payload = HEADER + bytes([1, 2 | extra_options]) + prefix + _ruler(count) + _char("x") + b"\x00\x00"
    result = decode_mtef_formula(payload)
    assert result.success and result.confidence == "structural", result
    assert result.latex == "x"


def test_pile_embeds_ruler_body_and_preserves_both_rows():
    rows = b"".join(b"\x01\x00" + _char(value) + b"\x00" for value in "xy")
    result = decode_mtef_formula(HEADER + b"\x04\x02\x00\x00" + _ruler(1) + rows + b"\x00\x00")
    assert result.confidence == "structural", result
    assert result.latex == r"\begin{gathered}x \\ y\end{gathered}"


def test_standalone_ruler_keeps_its_record_tag():
    result = decode_mtef_formula(HEADER + b"\x07" + _ruler(7) + b"\x01\x00" + _char("x") + b"\x00\x00")
    assert result.confidence == "structural", result
    assert result.latex == "x"


def test_real_mathtype_tabbed_fraction_interval_is_structural():
    # The formula-only MTEF fragment from the reported DOCX, checked against
    # its embedded preview: 1/2 <= m < 3/4. No paper text or model response.
    result = decode_mtef_formula(TABBED_INTERVAL)
    assert result.success and result.confidence == "structural", result
    assert result.latex == r"\dfrac{1}{2}\le m<\dfrac{3}{4}"
    assert not result.warning


@pytest.mark.parametrize("payload", [
    TABBED_INTERVAL[:-12],
    HEADER + b"\x13WinAllCodePages\x00\x01\x00" + _char("x") + b"\x30+1\x00\x00",
    HEADER + b"WinAllCodePages x\x01+1\x00",
    HEADER + b"\x01\x02\x01\x05\x30\x18" + _char("x") + b"\x00\x00",
])
def test_malformed_binary_never_falls_back_to_printable_byte_soup(payload):
    result = decode_mtef_formula(payload)
    assert not result.success, result
    assert result.latex == ""
    assert "无法可靠转换" in result.warning


def test_explicit_legacy_text_payload_still_has_compatibility_support():
    result = decode_mtef_formula(HEADER + b"WinAllCodePages cos x + 3 sin x\x00")
    assert result.success and result.confidence == "compatibility", result
    assert result.latex == r"\cos x + 3\sin x"
