"""References section is rebuilt after citation clamp — unique [1]..[n], no duplicate labels."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.roles.synthesizer import SynthesizerNode


def _reference_line_numbers(ref_section: str) -> list[int]:
    return [int(m.group(1)) for m in re.finditer(r"^\[(\d+)\]\s", ref_section, re.MULTILINE)]


def test_clamp_body_then_references_are_consecutive_unique():
    numbered = [
        {"number": 1, "domain": "a.com", "url": "https://a.com/x", "content": ""},
        {"number": 2, "domain": "b.com", "url": "https://b.com/y", "content": ""},
    ]
    report = (
        "Intro [1] mid [3] tail [4].\n\n"
        "## References\n\n"
        "[1] old\n[3] old\n[4] old\n"
    )
    body, _ = SynthesizerNode._split_body_and_references(report)
    body, _issues = SynthesizerNode._clamp_citations(body, 2)
    ref_block = SynthesizerNode._format_references_block(numbered)
    final = f"{body}\n\n## References\n\n{ref_block}"
    ref_part = final.split("## References", 1)[-1].strip()
    nums = _reference_line_numbers(ref_part)
    assert nums == [1, 2]
    assert "Intro [1]" in final
    assert "[3]" not in final
    assert "[4]" not in final


def test_format_references_ignores_stale_number_field_uses_order():
    numbered = [
        {"number": 99, "domain": "z", "url": "https://z/1", "content": ""},
        {"number": 98, "domain": "z", "url": "https://z/2", "content": ""},
    ]
    block = SynthesizerNode._format_references_block(numbered)
    nums = _reference_line_numbers(block)
    assert nums == [1, 2]
