import argparse
import json

from agent_lab.config import Settings
from scripts import live_smoke


def configure(monkeypatch, tmp_path):
    monkeypatch.setattr(live_smoke, "ROOT", tmp_path)
    monkeypatch.setattr(live_smoke, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(live_smoke, "Settings", lambda: Settings(enable_live=False))
    monkeypatch.setattr(live_smoke, "diagnose", lambda settings: {"cli_available": True})


async def test_smoke_default_never_calls_provider(tmp_path, monkeypatch, capsys):
    configure(monkeypatch, tmp_path)

    def forbidden(*args):
        raise AssertionError("Preflight must not require live access or call a model")

    monkeypatch.setattr(live_smoke, "require_live_access", forbidden)
    for name in live_smoke.CHECKS:
        monkeypatch.setattr(live_smoke, name, forbidden)
    assert await live_smoke.main(argparse.Namespace(live=False)) == 0
    assert json.loads(capsys.readouterr().out)["model_calls"] == 0
    assert not (tmp_path / ".lab-data").exists()


async def test_smoke_failure_stops_paid_sequence_and_redacts_exception(
    tmp_path, monkeypatch, capsys
):
    configure(monkeypatch, tmp_path)
    monkeypatch.setattr(live_smoke, "require_live_access", lambda settings: None)
    called = []

    async def failed(settings):
        called.append("lesson1")
        raise RuntimeError("provider payload containing a credential-secret")

    async def forbidden(settings):
        raise AssertionError("A failed check must stop the sequence")

    monkeypatch.setattr(live_smoke, "lesson1", failed)
    for name in live_smoke.CHECKS[1:]:
        monkeypatch.setattr(live_smoke, name, forbidden)
    assert await live_smoke.main(argparse.Namespace(live=True, only=None, elicitation=True)) == 1
    (report_path,) = tmp_path.glob(".lab-data/live-smoke/*/report.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert called == ["lesson1"]
    assert report["checks"] == {"lesson1": {"passed": False, "error_type": "RuntimeError"}}
    assert "credential-secret" not in capsys.readouterr().out + report_path.read_text(
        encoding="utf-8"
    )


async def test_smoke_only_runs_selected_check_in_an_isolated_folder(tmp_path, monkeypatch):
    configure(monkeypatch, tmp_path)
    monkeypatch.setattr(live_smoke, "require_live_access", lambda settings: None)
    called = []

    async def selected(settings):
        called.append(settings.data_dir)
        return {"passed": True, "cost_usd": 0.001}

    monkeypatch.setattr(live_smoke, "elicitation", selected)
    args = argparse.Namespace(live=True, only="elicitation", elicitation=True)
    assert await live_smoke.main(args) == 0
    assert len(called) == 1 and called[0].parent == tmp_path / ".lab-data/live-smoke"
    report = json.loads((called[0] / "report.json").read_text(encoding="utf-8"))
    assert set(report["checks"]) == {"elicitation"}
