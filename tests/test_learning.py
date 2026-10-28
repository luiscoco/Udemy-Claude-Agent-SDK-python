import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import ROOT, Settings
from agent_lab.curriculum import LESSONS, TOPICS
from agent_lab.learning import (
    STEP_TITLES,
    TUTOR_INTENTS,
    check_evidence,
    course,
    guide,
    guides,
    prepared_answer,
)
from agent_lab.models import LessonError, RunRequest
from agent_lab.runtime import RunService
from agent_lab.tutor import TutorRequest, TutorService

TYPESCRIPT_TERMS = ("TypeScript", "Zod", "npm ", "Node.js", "createSdkMcpServer")


def test_every_lesson_has_a_valid_python_guide():
    assert set(guides()) == set(LESSONS)
    for number, item in guides().items():
        assert [step.title for step in item.steps] == STEP_TITLES
        text = item.model_dump_json()
        assert not [term for term in TYPESCRIPT_TERMS if term in text], number
        for question in item.quiz:
            assert question.options[question.correct].explanation.startswith("Correct.")


def test_course_paths_sections_and_visual_guides_reference_real_content():
    data = course()
    assert {path.id for path in data.paths} == {
        "beginner",
        "application-developer",
        "advanced-harness",
    }
    assert all(set(path.lessons) <= set(LESSONS) for path in data.paths)
    assert {quiz.topic for quiz in data.section_quizzes} == set(TOPICS)
    for item in data.visual_guides:
        assert set(item.lessons) <= set(LESSONS)
        assert (ROOT / "public" / item.image.removeprefix("/assets/")).is_file()


@pytest.mark.parametrize("lesson_id", range(1, 76))
async def test_automatic_check_passes_on_actual_offline_evidence(lesson_id, tmp_path):
    service = RunService(Settings(data_dir=tmp_path))
    events = [event async for event in service.events(service.start(lesson_id, RunRequest()))]
    evidence = next(event.data["result"] for event in events if event.kind == "evidence")
    result = check_evidence(lesson_id, evidence, status=events[-1].data["status"])
    assert result.status == "passed", result.detail


def test_automatic_check_reports_failures_without_grading_the_student():
    key = guide(5).evidence_checks[0].key
    assert check_evidence(5, {}, status="completed").status == "needs-review"
    assert key in check_evidence(5, {}, status="completed").detail
    assert check_evidence(5, None, status="failed").detail.startswith("The run ended as failed")
    evidence = {check.key: check.value or "x" for check in guide(5).evidence_checks}
    assert check_evidence(5, evidence, status="completed", mode="live").status == "needs-review"
    assert (
        check_evidence(5, evidence, status="completed", mode="live", responded=True).status
        == "passed"
    )


@pytest.mark.parametrize("intent", TUTOR_INTENTS)
def test_prepared_tutor_answers_are_grounded_in_the_lesson(intent):
    text = prepared_answer(5, intent, "def calculator():\n    return 42")
    assert text.startswith("## Lesson 5: Custom tools")
    if intent == "code":
        assert "```python" in text
    with pytest.raises(ValueError):
        prepared_answer(5, "unknown")


async def test_live_tutor_requires_enablement_consent_and_a_listed_model(tmp_path, monkeypatch):
    disabled = TutorService(Settings(data_dir=tmp_path))
    with pytest.raises(PermissionError, match="disabled"):
        await disabled.answer(1, TutorRequest(mode="live", question="Why?", consent=True))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    tutor = TutorService(Settings(data_dir=tmp_path, enable_live=True))
    tutor._models = (time.monotonic() + 60, ["claude-haiku-4-5"])
    with pytest.raises(PermissionError, match="authorize"):
        await tutor.answer(1, TutorRequest(mode="live", question="Why?"))
    with pytest.raises(ValueError, match="listed models"):
        await tutor.answer(
            1, TutorRequest(mode="live", question="Why?", consent=True, model="claude-other")
        )


async def test_live_tutor_makes_one_bounded_toolless_sdk_call(tmp_path, monkeypatch):
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

    import agent_lab.tutor

    calls = []

    async def fake_query(prompt, options):
        calls.append(options)
        assert "Custom tools" in prompt and "Student request" in prompt
        yield AssistantMessage(content=[TextBlock(text="Validate in the handler.")], model="m")
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="s",
            total_cost_usd=0.001,
        )

    monkeypatch.setattr(agent_lab.tutor, "query", fake_query)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    tutor = TutorService(Settings(data_dir=tmp_path, enable_live=True))
    tutor._models = (time.monotonic() + 60, ["claude-haiku-4-5"])
    answer = await tutor.answer(
        5, TutorRequest(mode="live", intent="hint", question="Why validate?", consent=True)
    )
    assert answer.text == "Validate in the handler." and answer.cost_usd == 0.001
    (options,) = calls
    assert options.tools == [] and options.max_turns == 1 and options.max_budget_usd == 0.05
    assert options.setting_sources == [] and options.env["CLAUDE_CONFIG_DIR"]
    assert not (tmp_path / "tutor").exists() or not any((tmp_path / "tutor").iterdir())


async def test_live_tutor_reports_a_failed_result(tmp_path, monkeypatch):
    from claude_agent_sdk import ResultMessage

    import agent_lab.tutor

    async def failing(prompt, options):
        yield ResultMessage(
            subtype="error_max_budget_usd",
            duration_ms=1,
            duration_api_ms=1,
            is_error=True,
            num_turns=1,
            session_id="s",
        )

    monkeypatch.setattr(agent_lab.tutor, "query", failing)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    tutor = TutorService(Settings(data_dir=tmp_path, enable_live=True))
    tutor._models = (time.monotonic() + 60, ["claude-haiku-4-5"])
    with pytest.raises(LessonError):
        await tutor.answer(1, TutorRequest(mode="live", question="Why?", consent=True))


async def test_learning_api_routes(tmp_path):
    app = create_app(RunService(Settings(data_dir=tmp_path)), with_ui=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert len((await client.get("/api/course")).json()["visual_guides"]) == 4
        assert (await client.get("/api/lessons/5/guide")).json()["id"] == 5
        assert (await client.get("/api/lessons/76/guide")).status_code == 404
        prepared = await client.post("/api/lessons/5/tutor", json={"intent": "code"})
        assert prepared.status_code == 200 and "```python" in prepared.json()["text"]
        live = await client.post("/api/lessons/5/tutor", json={"mode": "live", "consent": True})
        assert live.status_code == 403
        assert (await client.post("/api/lessons/5/tutor", json={"intent": "x"})).status_code == 422
        models = (await client.get("/api/tutor/models")).json()
        assert models == {"live_enabled": False, "models": ["claude-haiku-4-5"]}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """The real NiceGUI server; a page-building error appears as a failed request or log."""
    data = tmp_path_factory.mktemp("server")
    port = free_port()
    env = os.environ | {
        "LAB_DATA_DIR": str(data),
        "LAB_PORT": str(port),
        "LAB_ENABLE_LIVE": "false",
        "NICEGUI_STORAGE_PATH": str(data / "storage"),
    }
    # A file, not a pipe: an unread pipe fills up and blocks the server.
    log_path = data / "server.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "agent_lab", "serve"],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(120):
                try:
                    httpx.get(base + "/api/health")
                    break
                except httpx.TransportError:
                    time.sleep(0.25)
            yield base, data
        finally:
            process.terminate()
            process.wait(timeout=30)
    output = log_path.read_text(errors="replace")
    # Windows reports a browser closing its socket as a callback traceback; that is not ours.
    unexpected = output.count("Traceback") - output.count("_call_connection_lost()>")
    assert unexpected == 0, output[-3000:]


def test_browser_pages_render_every_learning_tab(server):
    base, data = server
    with httpx.Client(base_url=base, timeout=30) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "Learning paths" in home.text and "Advanced Harness" in home.text
        for lesson_id in (1, 5, 57, 75):
            page = client.get(f"/?lesson={lesson_id}")
            assert page.status_code == 200, lesson_id
            for text in ("Lab walkthrough", "Visual guide", "AI Tutor", "Your review"):
                assert text in page.text, (lesson_id, text)
        assert client.get("/assets/visual-guides/c01-foundations.png").status_code == 200
    assert (data / "storage-secret").is_file()


def launch_browser(playwright):
    for options in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
        try:
            return playwright.chromium.launch(**options)
        except Exception:
            continue
    pytest.skip("No Chromium, Edge or Chrome is available for Playwright.")


def test_browser_run_check_workbook_and_tutor_persist(server):
    """Click through a lesson: controls must be wired, and progress must survive a reload."""
    from playwright.sync_api import sync_playwright

    base, _ = server
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=5")
        page.get_by_text("I understand the objective and preparation.").click()
        page.get_by_label("Private notes").fill("calculator rejects NaN")
        page.get_by_role("button", name="Show small hint").click()
        page.get_by_role("tab", name="Run the exercise").click()
        page.get_by_role("button", name="Run exercise").click()
        page.get_by_text("Check passed", exact=True).wait_for(timeout=15000)
        page.get_by_role("tab", name="AI Tutor").click()
        page.get_by_role("button", name="Ask the tutor").click()
        page.get_by_text("PREPARED ANSWER", exact=True).wait_for()
        page.get_by_role("button", name="Save this answer").click()
        page.reload()
        assert page.get_by_label("Private notes").input_value() == "calculator rejects NaN"
        assert page.get_by_text("Small hint:").count() == 1
        page.get_by_role("tab", name="Run the exercise").click()
        page.get_by_text("Check passed", exact=True).wait_for()
        page.get_by_role("tab", name="AI Tutor").click()
        page.get_by_text("Saved answers (1)").wait_for()
        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile.goto(base + "/?lesson=1")
        assert not mobile.evaluate("document.documentElement.scrollWidth > innerWidth")
        browser.close()
    assert errors == []
