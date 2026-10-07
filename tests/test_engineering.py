from pathlib import Path

import pytest
from claude_agent_sdk import ResultMessage

from agent_lab.config import Settings
from agent_lab.engineering import run_live_team, validate_source
from agent_lab.models import RunRequest


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef run():\n    os.system('echo unsafe')\n",
        "def run():\n    return eval('1+1')\n",
        "def run():\n    return (1).__class__\n",
        "open('outside.txt', 'w')\n",
        "from tags import normalize_tag as evil\n",
        "@print\ndef f():\n    return 1\n",
    ],
)
def test_source_policy_rejects_process_io_eval_and_object_escape(source):
    with pytest.raises(ValueError):
        validate_source(source, "src/tags.py")


async def test_model_team_uses_structured_proposals_host_ownership_and_real_acceptance(
    tmp_path, monkeypatch
):
    import agent_lab.engineering as engineering

    sources = {
        "T1": {
            "path": "src/tags.py",
            "source": "def normalize_tag(value):\n    return value.strip().lower()\n",
        },
        "T2": {
            "path": "src/search.py",
            "source": "from tags import normalize_tag\ndef find_by_tag(notes, tag):\n    return [n for n in notes if normalize_tag(tag) in [normalize_tag(t) for t in n['tags']]]\n",
        },
        "T3": {
            "path": "src/report.py",
            "source": "from tags import normalize_tag\ndef tag_counts(notes):\n    counts = {}\n    for note in notes:\n        for tag in set(map(normalize_tag, note['tags'])):\n            counts[tag] = counts.get(tag, 0) + 1\n    return counts\n",
        },
    }
    calls = []

    async def query(*, prompt, options):
        role = Path(options.env["CLAUDE_CONFIG_DIR"]).name
        calls.append(role)
        assert options.tools == []
        assert options.max_budget_usd <= 0.01
        if role == "lead":
            structured = {
                "tasks": [
                    {"id": "T1", "files": ["src/tags.py"], "depends_on": []},
                    {"id": "T2", "files": ["src/search.py"], "depends_on": ["T1"]},
                    {"id": "T3", "files": ["src/report.py"], "depends_on": ["T1"]},
                ]
            }
        elif role == "reviewer":
            structured = {"approved": True, "findings": []}
        else:
            structured = {"files": [sources[role]], "handoff": "Exports implemented."}
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="fixture",
            total_cost_usd=0.001,
            structured_output=structured,
        )

    monkeypatch.setattr(engineering, "query", query)
    events = []

    async def emit(event):
        events.append(event)

    await run_live_team(
        RunRequest(mode="live"), tmp_path, tmp_path / "config", Settings(enable_live=True), emit
    )
    assert calls[0] == "lead" and calls[-1] == "reviewer"
    assert set(calls) == {"lead", "T1", "T2", "T3", "reviewer"}
    result = events[-1].data
    assert result["release_gate"]
    assert result["cost_usd"] == 0.005
    assert result["acceptance"].strip() == "4 acceptance checks passed"
    assert not result["published"]
