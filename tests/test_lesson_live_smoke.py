"""Live acceptance remains opt-in and stops before spending on later failed cases."""

from types import SimpleNamespace

import pytest

from agent_lab.models import Event
from scripts import lesson_live_smoke as smoke


async def test_lesson_live_acceptance_default_never_starts_a_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.setattr(smoke, "RunService", lambda *args: pytest.fail("No live opt-in"))
    assert await smoke.run(17, False) == 0
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("fail_first", [False, True])
async def test_lesson_live_acceptance_grades_negative_controls_and_stops_on_failure(
    tmp_path, monkeypatch, fail_first
):
    called, closed = [], []
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.setattr(smoke, "Settings", lambda **kwargs: SimpleNamespace(**kwargs))

    class Service:
        def __init__(self, settings):
            pass

        def start(self, lesson, request):
            called.append(request)
            return request

        async def events(self, request):
            check = not request.lesson_options
            experiment = {
                "experiment_passed": False if fail_first else check,
                "connection_closed": True,
                "initialization": [{"session_id": "owned"}],
                "terminal_results": [
                    {"session_id": "owned", "subtype": "success", "is_error": False}
                ],
                "before_hash": "before",
                "changed_hash": "changed",
                "after_hash": "before" if check else "changed",
                "rewind_requested": check,
            }
            yield Event(kind="evidence", data={"result": {"experiment": experiment}})
            yield Event(kind="result", data={"total_cost_usd": 0.001})
            yield Event(kind="done", data={"status": "completed"})

        async def close(self):
            closed.append(True)

    monkeypatch.setattr(smoke, "RunService", Service)
    assert await smoke.run(17, True) == (1 if fail_first else 0)
    assert len(called) == (1 if fail_first else 4)
    assert closed == [True]
    assert len(list(tmp_path.glob(".lab-data/lesson-live-smoke/*/report.json"))) == 1


@pytest.mark.parametrize("observed", [True, False])
async def test_deep_hook_live_runner_requires_control_observations(tmp_path, monkeypatch, observed):
    from types import SimpleNamespace

    from agent_lab.models import Event

    called = []
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.setattr(smoke, "Settings", lambda **kwargs: SimpleNamespace(**kwargs))

    class Service:
        def __init__(self, settings):
            pass

        def start(self, lesson, request):
            called.append(request)
            return request

        async def events(self, request):
            yield Event(
                kind="evidence",
                data={
                    "result": {
                        "experiment": {
                            "experiment_passed": request.lesson_options.get("post_hook", True),
                            "observation_passed": observed,
                            "connection_closed": True,
                        }
                    }
                },
            )
            yield Event(kind="done", data={"status": "completed"})

        async def close(self):
            pass

    monkeypatch.setattr(smoke, "RunService", Service)
    assert await smoke.run(20, True) == (0 if observed else 1)
    assert len(called) == (7 if observed else 1)
