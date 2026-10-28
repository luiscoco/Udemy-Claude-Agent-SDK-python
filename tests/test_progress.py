import json

import pytest

from agent_lab.progress import MAX_BYTES, export_progress, import_progress

STORE = {
    "lessons": {
        "5": {
            "checkpoints": [True, True, False, False],
            "notes": "Validation happens twice.",
            "draft": "",
            "attempts": [{"text": "My answer", "hints": 1, "at": "2026-10-28T10:00:00+00:00"}],
            "hints": 1,
            "answers": {"0": 2},
            "check": {"status": "passed", "detail": "The local evidence meets the criterion."},
            "tutor": [
                {
                    "mode": "prepared",
                    "intent": "hint",
                    "question": "",
                    "text": "## Lesson 5",
                    "model": None,
                    "cost_usd": None,
                    "at": "2026-10-28T10:01:00+00:00",
                }
            ],
        }
    },
    "sections": {"fundamentals": {"0": 1}},
    "theme": "dark",
    "text_size": "large",
    "last_lesson": 5,
    "unrelated_key": "never exported",
}


def test_export_round_trips_exactly_what_the_app_stores():
    exported = export_progress(STORE)
    document = json.loads(exported)
    assert document["format"] == "agent-lab-progress" and document["version"] == 1
    assert "unrelated_key" not in document["progress"]
    restored = import_progress(exported)
    assert restored == {key: STORE[key] for key in restored}


def test_export_of_an_empty_browser_is_still_importable():
    assert import_progress(export_progress({}))["lessons"] == {}


def corrupt(change):
    document = json.loads(export_progress(STORE))
    change(document)
    return json.dumps(document).encode()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"not json", "not valid JSON"),
        (b"\xff\xfe", "not valid JSON"),
        (corrupt(lambda d: d.update(format="other-app")), "format"),
        (corrupt(lambda d: d["progress"]["lessons"].update({"99": {}})), "lesson numbers"),
        (corrupt(lambda d: d["progress"].update(theme="neon")), "theme"),
        (corrupt(lambda d: d["progress"]["lessons"]["5"].update(script="<x>")), "script"),
        (
            corrupt(lambda d: d["progress"]["lessons"]["5"].update(checkpoints=[True])),
            "checkpoints",
        ),
        (b" " * (MAX_BYTES + 1), "larger than 2 MB"),
    ],
    # Short ids: Windows rejects a test id built from a 2 MB parameter.
    ids=[
        "not-json",
        "not-utf8",
        "wrong-format",
        "unknown-lesson",
        "bad-theme",
        "extra-field",
        "short-checklist",
        "too-large",
    ],
)
def test_import_rejects_files_the_app_did_not_write(content, message):
    with pytest.raises(ValueError, match=message):
        import_progress(content)
