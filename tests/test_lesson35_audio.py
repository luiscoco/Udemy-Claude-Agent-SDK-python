"""Offline narration plan and alignment validation; no synthesis calls."""

import pytest

from agent_lab.lesson35_audio import clip_for_section
from scripts.lesson35_audio import checked_timing, plan, record, reviewed_sections


def test_lesson35_recording_plan_is_source_reviewed_and_zero_cost() -> None:
    script, settings = reviewed_sections()
    result = plan(script, settings)
    assert result["total_characters"] == sum(item["utf16_characters"] for item in result["sections"])
    assert result["network_requests"] == 0
    assert result["billing_usd"] is None
    assert settings["voiceId"] == "Yash"
    for index, section in enumerate(script["sections"]):
        assert clip_for_section(index, section["path"], section["start_line"],
                                section["end_line"]).startswith("/assets/audio/code/")
    with pytest.raises(ValueError, match="max-characters"):
        record(script, settings, result["total_characters"] - 1)


def test_alignment_requires_exact_order_and_valid_clocks() -> None:
    good = {"words": ["The", "store", "works"],
            "wordStartTimeSeconds": [0.0, 0.2, 0.5],
            "wordEndTimeSeconds": [0.1, 0.4, 0.8]}
    assert [cue["word"] for cue in checked_timing("The store works.", good, 1.0)] == ["The", "store", "works"]
    with pytest.raises(ValueError):
        checked_timing("The store works.", {**good, "words": ["The", "wrong", "works"]}, 1.0)
    with pytest.raises(ValueError):
        checked_timing("The store works.", {**good, "wordEndTimeSeconds": [0.1, 0.4, 1.3]}, 1.0)
