import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

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
        assert not [term for term in TYPESCRIPT_TERMS if term in text
                    and not (number == 42 and term == "Node.js")], number
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
    errors = [event.data["message"] for event in events if event.kind == "error"]
    evidence = next((event.data["result"] for event in events if event.kind == "evidence"), None)
    assert evidence is not None, errors
    result = check_evidence(lesson_id, evidence, status=events[-1].data["status"])
    assert result.status == "passed", result.detail


def test_automatic_check_reports_failures_without_grading_the_student():
    assert check_evidence(5, {}, status="completed").status == "needs-review"
    assert "missing" in check_evidence(5, {}, status="completed").detail.lower()
    assert check_evidence(5, None, status="failed").detail.startswith("The run ended as failed")
    evidence = {check.key: check.value or "x" for check in guide(5).evidence_checks}
    assert check_evidence(5, evidence, status="completed", mode="live").status == "needs-review"
    assert check_evidence(5, evidence, status="completed", mode="live", responded=True).status == "needs-review"


@pytest.mark.parametrize("intent", TUTOR_INTENTS)
def test_prepared_tutor_answers_are_grounded_in_the_lesson(intent):
    text = prepared_answer(5, intent)
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
    # Each error chain ends in one "Name: message" line. Two are known and harmless: Windows
    # reporting a browser closing its socket, and NiceGUI's drawer asking the browser for its
    # state when a test leaves a page within a second of loading it.
    benign = (
        "ConnectionResetError: [WinError 10054]",
        "TimeoutError: JavaScript did not respond within",
    )
    final_errors = re.findall(r"^[A-Za-z_.]*(?:Error|Exception): .*$", output, re.MULTILINE)
    unexpected = [line for line in final_errors if not line.startswith(benign)]
    assert not unexpected, unexpected


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


def test_browser_settings_controls_checks_and_sources(server):
    from playwright.sync_api import expect, sync_playwright

    base, data = server
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/?lesson=16")
            expect(page.locator(".quiz-question")).to_have_count(7)
            page.get_by_role("tab", name="Python source", exact=True).click()
            expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
            page.get_by_role("tab", name="Run the exercise", exact=True).click()
            page.get_by_label("Filesystem settings sources", exact=True).click()
            page.get_by_role("option", name="Owned project and local fixtures", exact=True).click()
            page.get_by_label("Demo environment value", exact=True).click()
            page.get_by_role("option", name="beta", exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
            page.get_by_label("Recorded scenario", exact=True).click()
            page.get_by_role("option", name="Mismatched child configuration", exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
            page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
            page.screenshot(path=str(data / "settings-phone.png"))
            assert not errors
        finally:
            browser.close()


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


def test_tutor_context_includes_the_classes_an_exercise_uses():
    from agent_lab.exercises import exercise_context

    calculator = exercise_context("calculator")
    assert "class Calculation(BaseModel):" in calculator
    assert "allow_inf_nan=False" in calculator
    assert "class Lesson(" not in calculator  # signature types are not context
    support = exercise_context("support")
    assert "class Approval:" in support and "class Refund(BaseModel):" in support


async def test_live_tutor_api_sends_the_model_source_to_claude(tmp_path, monkeypatch):
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

    import agent_lab.tutor

    prompts = []

    async def fake_query(prompt, options):
        prompts.append(prompt)
        yield AssistantMessage(content=[TextBlock(text="Grounded answer.")], model="m")
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
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-not-a-real-key")
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=True)), with_ui=False)
    app.state.tutor._models = (time.monotonic() + 60, ["claude-haiku-4-5"])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/lessons/5/tutor",
            json={"mode": "live", "question": "Why validate twice?", "consent": True},
        )
    assert response.status_code == 200 and response.json()["text"] == "Grounded answer."
    assert "class Calculation(BaseModel):" in prompts[0]
    # Source is sent verbatim, not JSON-escaped, so quoted code keeps its quotes.
    assert 'ConfigDict(extra="forbid", strict=True)' in prompts[0]


def test_browser_enables_the_prompt_only_for_offline_exercises_that_read_it(server):
    from playwright.sync_api import sync_playwright

    base, _ = server
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page()
        page.goto(base + "/?lesson=59")
        page.get_by_role("tab", name="Run the exercise").click()
        prompt = page.get_by_label("Prompt (optional)")
        assert prompt.is_enabled()
        prompt.fill("compare a complex workflow")
        page.get_by_role("button", name="Run exercise").click()
        page.get_by_text("Check passed", exact=True).wait_for(timeout=15000)
        assert page.get_by_text("capable").count() >= 1
        page.goto(base + "/?lesson=51")
        page.get_by_role("tab", name="Run the exercise").click()
        assert page.get_by_label("Agent prompt (live mode)").is_disabled()
        browser.close()


def test_lesson58_mobile_catalog_controls_and_prepared_refund(server, guide_browser_context):
    base, _ = server
    page = guide_browser_context.new_page()
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        page.goto(base + "/?lesson=58")
        page.get_by_role("tab", name="Run the exercise").click()
        page.get_by_text("Tool search across 64 tools").wait_for(timeout=15000)
        page.get_by_role("button", name="Local search").click()
        page.get_by_text("mcp__ops__billing_refund_invoice").first.wait_for(timeout=15000)
        page.get_by_role("button", name="Estimate load").click()
        page.get_by_text('"loadedCount": 0').wait_for(timeout=15000)
        page.get_by_role("button", name="Prepared refund").click()
        page.get_by_text('"check": "pass"').wait_for(timeout=15000)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
    finally:
        page.close()


def test_browser_exports_progress_and_imports_it_into_another_browser(server, tmp_path):
    """A fresh browser context has its own storage, like moving to another browser."""
    from playwright.sync_api import sync_playwright

    base, _ = server
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        first = browser.new_context().new_page()
        first.goto(base + "/?lesson=5")
        first.get_by_label("Private notes").fill("moved between browsers")
        first.get_by_text("I understand the objective and preparation.").click()
        first.wait_for_timeout(500)  # let the note reach the server-side store
        first.goto(base + "/")
        with first.expect_download() as download:
            first.get_by_role("button", name="Export progress").click()
        exported = tmp_path / "progress.json"
        download.value.save_as(exported)

        second = browser.new_context().new_page()
        second.goto(base + "/?lesson=5")
        assert second.get_by_label("Private notes").input_value() == ""
        second.goto(base + "/")
        second.locator("input[type=file]").set_input_files(str(exported))
        second.get_by_text("Replace your progress?").wait_for()
        # Replacing progress reloads the page; wait for it before navigating again.
        with second.expect_navigation():
            second.get_by_role("button", name="Replace progress").click()
        second.goto(base + "/?lesson=5")
        assert second.get_by_label("Private notes").input_value() == "moved between browsers"
        browser.close()


def test_browser_renders_the_generated_exercise_diagram(server):
    from playwright.sync_api import sync_playwright

    base, _ = server
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page()
        page.goto(base + "/?lesson=26")
        page.get_by_role("tab", name="Visual guide").click()
        diagram = page.locator(".exercise-diagram svg").first
        diagram.wait_for(timeout=15000)
        assert "Scripted CLI fixture" in (diagram.text_content() or "")
        assert page.get_by_text("Syntax error").count() == 0
        browser.close()


def test_browser_lessons_focus_on_concept_code_and_show_live_tutor_option(server):
    from playwright.sync_api import sync_playwright

    base, _ = server
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(base + "/?lesson=1")
        page.get_by_text("The concept in code").first.wait_for()
        assert page.locator(".nicegui-code").filter(has_text="query(").count() >= 1
        page.get_by_role("tab", name="Python source").click()
        page.get_by_text("How the offline lab checks this concept").wait_for()
        # The harness is folded away; the concept code is what the tab shows first.
        assert not page.get_by_text("recorded_messages").first.is_visible()
        page.get_by_role("tab", name="Visual guide").click()
        page.locator(".infographic").get_by_text("LESSON 01", exact=True).wait_for()
        page.get_by_role("tab", name="AI Tutor").click()
        page.get_by_role("button", name="Live Claude answer").click()
        page.get_by_text("Live answers are turned off").wait_for()
        assert page.get_by_role("button", name="Ask the tutor").is_disabled()
        browser.close()


def test_browser_study_coach_runs_the_selected_coach_implementation(server):
    from playwright.sync_api import sync_playwright

    base, _ = server
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.goto(base + "/coach")
        page.get_by_role("button", name="Reference").click()
        page.get_by_text("is at stage 7 of 7").wait_for()
        # Start-here cards lead the guide; a saved recognition check never completes a lesson.
        page.get_by_label("Concept").click()
        page.get_by_role("option", name="Start here · Understand what an LLM does").click()
        page.get_by_text("Start here: Understand what an LLM does").wait_for()
        page.get_by_role("radio", name="Only that text was produced").click()
        page.get_by_text("1 correct of 1 answered").wait_for()
        page.reload()
        page.get_by_text("1 correct of 1 answered").wait_for()
        page.get_by_role("button", name="Previous concept").click()
        page.get_by_text("Start here: Run a first query").wait_for()
        page.get_by_label("Concept").click()
        page.get_by_role("option", name="1. ", exact=False).first.click()
        page.get_by_text("Lab source: agent_lab/exercises.py").wait_for()
        page.get_by_role("button", name="Simple code").click()
        page.get_by_role("button", name="Ask", exact=True).click()
        # Wait for the answer itself: "RUNNING" may not have appeared yet.
        answer = page.locator(".response-prose").filter(has_text="async for message").first
        answer.wait_for(timeout=15000)
        page.get_by_text("RUNNING").wait_for(state="hidden", timeout=15000)
        page.get_by_role("button", name="Try invalid prepared plan").click()
        page.get_by_text("REJECTED").wait_for()
        page.get_by_role("button", name="Inspect saved turn").click()
        page.get_by_text("Reuse the saved answer").wait_for()
        browser.close()


def test_browser_evaluation_studio_keeps_a_limited_run_a_failure(server):
    from playwright.sync_api import sync_playwright

    base, _ = server
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.goto(base + "/studio")
        page.get_by_role("button", name="Reference").click()
        page.get_by_text("is at stage 7 of 7").wait_for()
        page.get_by_label("Prepared scenario").click()
        page.get_by_role("option", name="Turn limit, then a stream error").click()
        page.get_by_role("button", name="Run", exact=True).click()
        page.locator(".q-badge").filter(has_text="error_max_turns").wait_for()
        page.get_by_text("SDK stream stopped").wait_for()
        page.get_by_role("button", name="Save review").click()
        page.get_by_text("needs work").first.wait_for()
        browser.close()


def test_browser_code_tour_highlights_each_section(server):
    from playwright.sync_api import sync_playwright

    from agent_lab.learning import code_tour

    base, _ = server
    sections = code_tour(1)
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.goto(base + "/?lesson=1")
        page.get_by_role("button", name="Start code tour").click()
        page.get_by_text(f"Step 1 of {len(sections)}").wait_for()
        page.get_by_text(sections[0].title, exact=True).wait_for()
        assert page.locator(".tour-code .hll").count() >= 1
        page.get_by_role("button", name="Next step").click()
        page.get_by_text(sections[1].title, exact=True).wait_for()
        # Every highlighted line must render on its own row, not collapse out of sight.
        rows = page.evaluate(
            "new Set([...document.querySelectorAll('.tour-code .hll')]"
            ".map(e => Math.round(e.getBoundingClientRect().top))).size"
        )
        assert rows == sections[1].end - sections[1].start + 1, rows
        page.get_by_role("button", name="Read aloud").click()
        page.get_by_role("button", name="End tour").click()
        page.get_by_role("button", name="Start code tour").wait_for()
        browser.close()


def test_browser_publishing_studio_builds_and_downloads_a_document(server, tmp_path):
    from playwright.sync_api import sync_playwright

    base, _ = server
    source = tmp_path / "notes.txt"
    source.write_text("Results end with a ResultMessage.", encoding="utf-8")
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.goto(base + "/publish")
        page.get_by_role("button", name="Reference").click()
        page.get_by_text("is at stage 8 of 8").wait_for()
        page.locator("input[type=file]").set_input_files(str(source))
        page.get_by_text("notes.txt · 33 characters extracted").wait_for()
        page.get_by_role("button", name="Send").click()
        page.get_by_text("Attached sources: notes.txt").wait_for()
        page.get_by_text("PREPARED SAMPLE", exact=True).wait_for()
        page.get_by_role("button", name="Build files").click()
        page.get_by_role("link", name="Download PDF").wait_for(timeout=60000)
        with page.expect_download() as download:
            page.get_by_role("link", name="Download DOCX").click()
        assert download.value.suggested_filename.endswith(".docx")
        assert Path(download.value.path()).read_bytes().startswith(b"PK")
        page.get_by_role("button", name="Live SDK answer").click()
        page.get_by_role("button", name="Send").click()
        page.get_by_text("Authorize this paid answer").first.wait_for()
        phone = browser.new_page(viewport={"width": 390, "height": 844})
        phone.goto(base + "/publish")
        phone.get_by_text("4 · Download").wait_for()
        assert not phone.evaluate("document.documentElement.scrollWidth > innerWidth")
        browser.close()


def assert_guide_target_fits(page):
    """The whole outline must clear the fixed header and floating guide, not just exist."""
    page.wait_for_function("""() => {
        const target = document.querySelector('.learning-guide-target');
        const panel = document.querySelector('.learning-guide');
        const header = document.querySelector('.q-header');
        if (!target || !panel || !header) return false;
        const box = target.getBoundingClientRect();
        const guide = panel.getBoundingClientRect();
        const style = getComputedStyle(target);
        // A tab can be on screen while its slide transition still clips the frame.
        if (target.closest('[class*="-enter-active"], [class*="-leave-active"]')) return false;
        for (let parent = target.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
            const css = getComputedStyle(parent);
            const clip = parent.getBoundingClientRect();
            if (['hidden', 'clip', 'auto', 'scroll'].includes(css.overflowX)
                && (box.left - 8 < clip.left || box.right + 8 > clip.right)) return false;
            if (['hidden', 'clip', 'auto', 'scroll'].includes(css.overflowY)
                && (box.top - 8 < clip.top || box.bottom + 8 > clip.bottom)) return false;
        }
        return box.width > 0 && box.height > 0 && box.left >= 8 && box.right <= innerWidth - 8
            && style.outlineStyle === 'solid' && parseFloat(style.outlineWidth) >= 2
            && style.outlineColor === 'rgb(220, 38, 38)'
            && box.top >= header.getBoundingClientRect().bottom + 8
            && box.bottom <= guide.top - 8;
    }""")


def test_browser_written_guide_preserves_work_and_only_changes_tour_position(server):
    import json

    from playwright.sync_api import expect, sync_playwright

    from agent_lab.lesson_guide import learning_guides
    from agent_lab.ui_guide import INITIAL_LESSON_START

    base, _ = server
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(base + "/?lesson=1&path=application-developer")
        page.get_by_label("Private notes", exact=True).fill("My saved guide note")
        page.get_by_label("Private notes", exact=True).press("Tab")
        launch = page.get_by_role("button", name="Open Learning Guide", exact=True)
        launch.focus()
        launch.press("Enter")
        panel = page.get_by_role("region", name="Lesson 1 Learning Guide", exact=True)
        expect(panel).to_be_focused()
        # A delayed startup callback must not steal focus from an opened guide.
        page.evaluate(INITIAL_LESSON_START)
        expect(panel).to_be_focused()
        expect(launch).to_have_attribute("aria-expanded", "true")
        panel.get_by_role("button", name="Start guided tour", exact=True).press("Enter")
        for index, section in enumerate(learning_guides()[1].sections):
            if index:
                panel.get_by_role("button", name="Next section", exact=True).click()
            panel.get_by_text(f"Section {index + 1} of 7", exact=False).wait_for()
            target = page.locator(section.target + ".learning-guide-target")
            expect(target).to_be_visible(timeout=10000)
            expect(page.locator(".learning-guide-target")).to_have_count(1)
            expect(panel.locator(".learning-guide-step")).to_be_focused()
            assert_guide_target_fits(page)
            if section.id in {"example", "source"}:
                expect(target.locator("code")).to_contain_text(guide(1).concept_code)
                assert target.evaluate("e => e.scrollHeight > e.clientHeight")
            assert target.bounding_box()["height"] < 350  # Small teaching target, not a whole card.
        page.get_by_role("tab", name="AI Tutor", exact=True).click()
        panel.get_by_text("Tour paused after a tab change.", exact=False).wait_for()
        expect(page.locator(".learning-guide-target")).to_have_count(0)
        panel.get_by_role("button", name="Show section", exact=True).click()
        expect(page.locator(".guide-practice-target.learning-guide-target")).to_be_visible()
        panel.get_by_role("button", name="Minimize Learning Guide", exact=True).click()
        expect(panel.get_by_role("button", name="Finish tour", exact=True)).not_to_be_visible()
        panel.get_by_role("button", name="Expand Learning Guide", exact=True).click()
        panel.get_by_role("button", name="Close Learning Guide", exact=True).focus()
        page.keyboard.press("Escape")
        expect(panel).not_to_be_visible()
        expect(page.locator(".learning-guide-target")).to_have_count(0)
        page.reload()
        page.get_by_role("button", name="Open Learning Guide", exact=True).click()
        panel = page.get_by_role("region", name="Lesson 1 Learning Guide", exact=True)
        expect(page.locator(".learning-guide-target")).to_have_count(0)
        panel.get_by_role("button", name="Resume: Explain and practise", exact=True).click()
        expect(page.locator(".guide-practice-target.learning-guide-target")).to_be_visible()
        expect(page.get_by_label("Private notes", exact=True)).to_have_value("My saved guide note")
        panel.get_by_role("button", name="Finish tour", exact=True).click()
        expect(panel).not_to_be_visible()
        expect(page.locator("#lesson-heading")).to_be_focused()
        expect(page.locator(".learning-guide-target")).to_have_count(0)
        assert "lesson=1" in page.url
        page.goto(base + "/")
        with page.expect_download() as downloaded:
            page.get_by_role("button", name="Export progress", exact=True).click()
        progress = json.loads(Path(downloaded.value.path()).read_bytes())["progress"]
        saved = progress["lessons"]["1"]
        assert saved["notes"] == "My saved guide note"
        assert saved["checkpoints"] == [False] * 4
        assert saved["attempts"] == [] and saved["answers"] == {}
        assert saved["check"] is None and saved["last_run"] == ""
        assert "1" not in progress["learning_guide_positions"]
        browser.close()


def test_browser_guide_phone_large_text_fallback_and_route_next(server):
    from playwright.sync_api import expect, sync_playwright

    from agent_lab.lesson_guide import learning_guides

    base, _ = server
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(base + "/?lesson=1&path=application-developer")
        page.get_by_role("button", name="Appearance", exact=True).click()
        page.get_by_role("button", name="Dark", exact=True).click()
        page.get_by_label("Text size", exact=True).click()
        page.get_by_role("option", name="Extra large", exact=True).click()
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Open Learning Guide", exact=True).click()
        panel = page.get_by_role("region", name="Lesson 1 Learning Guide", exact=True)
        panel.get_by_role("button", name="Start guided tour", exact=True).click()
        for index, section in enumerate(learning_guides()[1].sections):
            if index:
                panel.get_by_role("button", name="Next section", exact=True).click()
            panel.get_by_text(f"Section {index + 1} of 7", exact=False).wait_for()
            expect(page.locator(section.target + ".learning-guide-target")).to_be_visible()
            assert_guide_target_fits(page)
            expect(panel.get_by_role("button", name="Previous section", exact=True)).to_be_in_viewport()
            bounds = panel.bounding_box()
            assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 391
            assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 845
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
        # A missing lazily rendered target must leave the written guidance usable.
        page.locator(".guide-practice-target").evaluate("e => e.remove()")
        panel.get_by_role("button", name="Show section", exact=True).click()
        panel.get_by_text("This target is unavailable.", exact=False).wait_for()
        panel.get_by_role("button", name="Next lesson →", exact=True).click()
        page.wait_for_url("**/?lesson=3&path=application-developer")
        expect(page.locator("#lesson-heading")).to_contain_text("3. Built-in tools")
        expect(page.locator("#lesson-heading")).to_be_focused()
        expect(page.get_by_role("button", name="Open Learning Guide", exact=True)).to_be_visible()
        expect(page.get_by_role("region", name="Lesson 3 Learning Guide", exact=True)).not_to_be_visible()
        browser.close()


def test_browser_guide_realigns_after_resize_code_tour_and_new_results(server):
    from playwright.sync_api import expect, sync_playwright

    base, _ = server
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.goto(base + "/?lesson=1")
        page.get_by_role("button", name="Open Learning Guide", exact=True).click()
        panel = page.get_by_role("region", name="Lesson 1 Learning Guide", exact=True)
        panel.get_by_role("button", name="Start guided tour", exact=True).click()
        for index in range(2):
            panel.get_by_role("button", name="Next section", exact=True).click()
            panel.get_by_text(f"Section {index + 2} of 7", exact=False).wait_for()
        expect(page.locator(".guide-example-target.learning-guide-target")).to_be_visible()
        assert_guide_target_fits(page)
        # Automatic alignment must settle instead of pulling back a student's own scrolling.
        page.wait_for_timeout(100)
        scroll = page.evaluate("() => { scrollBy(0, 40); return scrollY; }")
        page.wait_for_timeout(250)
        assert abs(page.evaluate("scrollY") - scroll) < 2
        panel.get_by_role("button", name="Show section", exact=True).click()
        assert_guide_target_fits(page)
        # The code tour replaces its code HTML while retaining the meaningful target.
        page.get_by_role("button", name="Start code tour", exact=True).click()
        expect(page.locator(".guide-example-target .tour-code")).to_be_visible()
        assert_guide_target_fits(page)
        page.set_viewport_size({"width": 390, "height": 844})
        assert_guide_target_fits(page)
        page.set_viewport_size({"width": 1366, "height": 768})
        assert_guide_target_fits(page)
        panel.get_by_role("button", name="Next section", exact=True).click()
        # This explicit student action runs the free fixture; the tour does not click Run.
        run = page.get_by_role("button", name="Run exercise", exact=True)
        expect(run).to_have_css("outline-style", "solid")
        expect(run).to_have_css("outline-color", "rgb(220, 38, 38)")
        page.keyboard.press("Tab")
        expect(run).to_have_css("outline-style", "solid")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        page.get_by_text("Completed", exact=True).wait_for()
        expect(run).to_have_class(re.compile(r".*learning-guide-target.*"))
        expect(run).to_have_css("outline-style", "solid")
        expect(run).to_have_css("outline-color", "rgb(220, 38, 38)")
        panel.get_by_role("button", name="Next section", exact=True).click()
        target = page.locator(".guide-evidence-target.learning-guide-target")
        expect(target).to_contain_text("Recorded test text")
        assert_guide_target_fits(page)
        panel.get_by_role("button", name="Close Learning Guide", exact=True).click()
        expect(page.locator("body")).not_to_have_class(re.compile(r".*learning-guide-active.*"))
        assert not page.locator(".guide-evidence-target").evaluate(
            "e => e.style.getPropertyValue('--learning-guide-target-height')"
        )
        browser.close()


@pytest.fixture(scope="module")
def guide_browser_context(server):
    """Reuse Chromium and its asset cache while visiting the complete curriculum."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        context = browser.new_context()
        yield context
        context.close()
        browser.close()


@pytest.mark.parametrize("phone", [False, True], ids=["desktop", "phone"])
def test_browser_query_scenarios_assessment_save_and_resume(server, guide_browser_context, phone):
    from playwright.sync_api import expect

    from agent_lab.ui_learning import REVIEW_ITEMS

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390 if phone else 1440, "height": 844 if phone else 1000})
    try:
        page = context.new_page()
        page.goto(base + "/?lesson=1")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Run the exercise").click()
        expect(page.get_by_label("Maximum turns", exact=True)).to_have_value("1")
        expect(page.get_by_label("Budget threshold (USD)", exact=True)).to_have_value("0.05")
        for option, passed in [("Success", True), ("SDK error", False), ("Missing final result", False)]:
            page.get_by_label("Recorded scenario", exact=True).click()
            page.get_by_role("option", name=option, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=15000)
            expect(page.get_by_role("button", name="Run exercise", exact=True)).to_be_enabled()
            expect(page.get_by_role("button", name="Cancel", exact=True)).to_be_disabled()
            expect(page.get_by_text("Check passed" if passed else "Needs review", exact=True)).to_be_visible()
            expect(page.locator(".guide-evidence-target").get_by_text({"Success": "success", "SDK error": "error", "Missing final result": "missing-result"}[option], exact=True).first).to_be_visible()
            expect(page.locator(".guide-evidence-target")).to_contain_text("Recorded test text")
        page.screenshot(path=str(data / f"query-scenarios-{'phone' if phone else 'desktop'}.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.get_by_role("tab", name="Learn").click()
        question = page.locator(".quiz-question").nth(2)
        question.get_by_role("radio").first.click()
        expect(question.locator(".feedback-ok")).to_be_visible()
        page.get_by_label("Your explanation and evidence", exact=True).fill("Text alone does not prove success; inspect the terminal result.")
        page.get_by_role("button", name="Save attempt", exact=True).click()
        page.reload()
        expect(page.locator(".quiz-question").nth(2).get_by_role("radio").first).to_be_checked()
        expect(page.get_by_label("Your explanation and evidence", exact=True)).to_have_value("Text alone does not prove success; inspect the terminal result.")
        expect(page.get_by_text("1 saved attempts", exact=False)).to_be_visible()
        for label in REVIEW_ITEMS:
            expect(page.get_by_role("checkbox", name=label, exact=True)).not_to_be_checked()
        page.goto(base + "/?lesson=51")
        page.get_by_role("tab", name="Run the exercise").click()
        expect(page.get_by_label("Agent prompt (live mode)", exact=True)).to_be_disabled()
        expect(page.get_by_label("Recorded scenario", exact=True)).not_to_be_visible()
    finally:
        context.close()


def test_browser_prompt_suggestions_evidence_and_controls(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=38")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_role("checkbox", name="Edit a suggestion before sending", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Suggestion switch", exact=True).click()
        page.get_by_role("option", name="Omitted option", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "prompt-suggestions-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_project_config_root_origins_and_takeover(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=39")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Configuration root", exact=True).click()
        page.get_by_role("option", name="Omitted", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Configuration experiment", exact=True).click()
        page.get_by_role("option", name="Exact Bash takeover", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Missing required evidence", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "project-config-root-phone.png"))
        assert not errors
    finally:
        context.close()


@pytest.mark.parametrize("lesson_id", range(2, 76))
def test_browser_remaining_learning_guides_frame_all_seven_targets(server, guide_browser_context, lesson_id):
    from playwright.sync_api import expect

    from agent_lab.lesson_guide import learning_guides

    base, data = server
    page = guide_browser_context.new_page()
    # Visit every lesson; also exercise the narrow layout across all course sections.
    phone = lesson_id % 3 == 0
    page.set_viewport_size({"width": 390 if phone else 1440, "height": 844 if phone else 1000})
    try:
        page.goto(base + f"/?lesson={lesson_id}")
        page.get_by_role("button", name="Open Learning Guide", exact=True).click()
        panel = page.get_by_role("region", name=f"Lesson {lesson_id} Learning Guide", exact=True)
        panel.get_by_role("button", name="Start guided tour", exact=True).click()
        for index, section in enumerate(learning_guides()[lesson_id].sections):
            if index:
                panel.get_by_role("button", name="Next section", exact=True).click()
            panel.get_by_text(f"Section {index + 1} of 7", exact=False).wait_for()
            target = page.locator(section.target + ".learning-guide-target")
            expect(target).to_be_visible(timeout=10000)
            expect(page.locator(".learning-guide-target")).to_have_count(1)
            assert_guide_target_fits(page)
            expect(panel.get_by_role("button", name="Previous section", exact=True)).to_be_in_viewport()
            if section.id in {"example", "source"}:
                expect(target.locator("code")).to_be_visible()
            assert panel.locator(".learning-guide-body").evaluate("e => e.scrollWidth <= e.clientWidth + 1")
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            if os.environ.get("LAB_GUIDE_SCREENSHOTS") == "true" and lesson_id in {2, 13, 33, 43, 57, 72, 75}:
                page.screenshot(path=str(data / f"guide-{lesson_id:02}-{section.id}.png"))
        next_button = panel.get_by_role("button", name="Next lesson \u2192", exact=True)
        if lesson_id == 75:
            expect(next_button).to_have_count(0)
        else:
            expect(next_button).to_be_visible()
        panel.get_by_role("button", name="Finish tour", exact=True).click()
        expect(panel).not_to_be_visible()
        expect(page.locator("#lesson-heading")).to_be_focused()
        expect(page.locator(".learning-guide-target")).to_have_count(0)
        assert f"lesson={lesson_id}" in page.url
    finally:
        page.close()


def test_browser_guide_positions_are_independent_across_lessons_and_finish(server, guide_browser_context):
    from playwright.sync_api import expect

    base, _ = server
    browser = guide_browser_context.browser
    assert browser is not None
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    try:
        page = context.new_page()
        for lesson_id, advances in ((2, 2), (75, 6)):
            page.goto(base + f"/?lesson={lesson_id}")
            page.get_by_label("Private notes", exact=True).fill(f"My lesson {lesson_id} notes")
            page.get_by_label("Private notes", exact=True).press("Tab")
            page.get_by_role("button", name="Open Learning Guide", exact=True).click()
            panel = page.get_by_role("region", name=f"Lesson {lesson_id} Learning Guide", exact=True)
            panel.get_by_role("button", name="Start guided tour", exact=True).click()
            for index in range(advances):
                panel.get_by_role("button", name="Next section", exact=True).click()
                panel.get_by_text(f"Section {index + 2} of 7", exact=False).wait_for()
            panel.get_by_role("button", name="Close Learning Guide", exact=True).click()
        # Reload the last course lesson: Finish clears only its saved tour position.
        page.reload()
        page.get_by_role("button", name="Open Learning Guide", exact=True).click()
        panel = page.get_by_role("region", name="Lesson 75 Learning Guide", exact=True)
        panel.get_by_role("button", name="Resume: Explain and practise", exact=True).click()
        assert_guide_target_fits(page)
        expect(page.get_by_label("Private notes", exact=True)).to_have_value("My lesson 75 notes")
        panel.get_by_role("button", name="Finish tour", exact=True).click()
        expect(page.locator("#lesson-heading")).to_be_focused()
        page.goto(base + "/?lesson=2")
        page.get_by_role("button", name="Open Learning Guide", exact=True).click()
        panel = page.get_by_role("region", name="Lesson 2 Learning Guide", exact=True)
        panel.get_by_role("button", name="Resume: Read one example", exact=True).click()
        assert_guide_target_fits(page)
        expect(page.get_by_label("Private notes", exact=True)).to_have_value("My lesson 2 notes")
    finally:
        context.close()


def _my_learning_seed():
    from agent_lab.learning import guide

    quiz = guide(5).quiz
    return {
        "lessons": {
            "1": {"checkpoints": [True] * 4, "notes": "Reviewed lesson one"},
            "3": {"notes": "A scoped workspace"},
            "5": {
                "notes": "Validation note\n<script>window.__workspace_xss=1</script>",
                "draft": "My unsubmitted explanation",
                "attempts": [{"text": f"Explanation attempt {index}", "hints": index % 3,
                              "at": "2026-10-29T12:00:00+00:00"} for index in range(7)],
                "answers": {"0": quiz[0].correct, "1": (quiz[1].correct + 1) % len(quiz[1].options)},
                "check": {"status": "passed", "detail": "Local evidence meets the criterion."},
                "last_run": "Saved local run summary",
            },
        },
        "last_lesson": 5,
        "learning_guide_positions": {"5": "example", "75": "practice"},
    }


def _import_my_learning(page, base, tmp_path, store):
    from agent_lab.progress import export_progress

    path = tmp_path / "my-learning-progress.json"
    path.write_bytes(export_progress(store))
    page.goto(base + "/my-learning")
    page.locator("input[type=file]").set_input_files(str(path))
    page.get_by_text("Replace your progress?", exact=True).wait_for()
    with page.expect_navigation():
        page.get_by_role("button", name="Replace progress", exact=True).click()


def _export_my_learning(page):
    import json

    with page.expect_download() as downloaded:
        page.get_by_role("button", name="Export progress", exact=True).click()
    return json.loads(Path(downloaded.value.path()).read_bytes())["progress"]


def test_browser_my_learning_first_visit_setup_and_lesson_navigation(server, guide_browser_context):
    from playwright.sync_api import expect

    base, _ = server
    browser = guide_browser_context.browser
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    try:
        page = context.new_page()
        page.goto(base + "/")
        page.get_by_role("link", name="Open My Learning", exact=True).click()
        expect(page.get_by_role("heading", name="My Learning", exact=True)).to_be_visible()
        expect(page.get_by_text("0 of 75 lessons manually reviewed", exact=True)).to_be_visible()
        initial = _export_my_learning(page)
        assert initial["lessons"] == {} and initial["last_lesson"] == 0
        start = page.get_by_role("button", name="Start lesson 1", exact=True)
        start.focus()
        page.keyboard.press("Tab")
        page.keyboard.press("Shift+Tab")
        expect(start).to_be_focused()
        expect(start).to_have_css("outline-style", "solid")
        expect(start).to_have_css("outline-color", "rgb(37, 99, 235)")
        page.get_by_role("button", name="Review setup", exact=True).click()
        page.wait_for_url("**/setup")
        expect(page.get_by_text("Prepare your Python learning workspace", exact=True)).to_be_visible()
        page.get_by_role("link", name="Open My Learning", exact=True).click()
        assert _export_my_learning(page) == initial
        page.get_by_role("button", name="Start lesson 1", exact=True).click()
        page.wait_for_url("**/?lesson=1")
        expect(page.locator("#lesson-heading")).to_contain_text("1. query()")
        page.get_by_role("banner").get_by_role("link", name="My Learning", exact=True).click()
        expect(page.get_by_role("button", name="Continue lesson 1", exact=True)).to_be_visible()
        expect(page.get_by_text("0 of 75 lessons manually reviewed", exact=True)).to_be_visible()
    finally:
        context.close()


def test_browser_my_learning_saved_views_resume_and_export_preserve_records(server, guide_browser_context, tmp_path):
    import json

    from playwright.sync_api import expect

    from agent_lab.progress import export_progress

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 1440, "height": 1000})
    try:
        page = context.new_page()
        store = _my_learning_seed()
        expected = json.loads(export_progress(store))["progress"]
        _import_my_learning(page, base, tmp_path, store)
        expect(page.get_by_text("1 of 75 lessons manually reviewed", exact=True)).to_be_visible()
        page.screenshot(path=str(data / "my-learning-desktop-overview.png"))
        page.get_by_role("button", name="Notes", exact=True).click()
        page.get_by_label("Find lessons or saved text", exact=True).fill("Validation note")
        expect(page.get_by_text("1 matching lesson", exact=True)).to_be_visible()
        expect(page.get_by_text("My unsubmitted explanation", exact=True)).to_be_visible()
        expect(page.get_by_text("Validation note", exact=False).last).to_contain_text("<script>")
        page.screenshot(path=str(data / "my-learning-desktop-notes.png"))
        assert page.evaluate("window.__workspace_xss") is None
        page.get_by_role("button", name="Quiz results", exact=True).click()
        expect(page.get_by_text("Review this answer", exact=True)).to_be_visible()
        expect(page.get_by_text("1 of 75 lessons manually reviewed", exact=True)).to_be_visible()
        page.get_by_role("button", name="Attempts", exact=True).click()
        expect(page.get_by_text("Explanation attempt 6", exact=True)).to_be_visible()
        expect(page.get_by_text("Explanation attempt 0", exact=True)).to_have_count(0)
        page.get_by_role("button", name="Show more attempts for lesson 5", exact=True).click()
        expect(page.get_by_text("Explanation attempt 0", exact=True)).to_be_visible()
        page.get_by_role("button", name="Lessons", exact=True).click()
        page.get_by_label("Find lessons or saved text", exact=True).fill("")
        page.get_by_label("Manual / exercise status", exact=True).click()
        page.get_by_role("option", name="Reviewed", exact=True).click()
        expect(page.get_by_text("1 matching lesson", exact=True)).to_be_visible()
        page.get_by_label("Manual / exercise status", exact=True).click()
        page.get_by_role("option", name="All statuses", exact=True).click()
        page.get_by_label("Learning path", exact=True).click()
        page.get_by_role("option", name="Application Developer", exact=True).click()
        page.wait_for_url("**/my-learning?path=application-developer")
        page.get_by_role("link", name="Review setup", exact=True).click()
        page.wait_for_url("**/setup?path=application-developer")
        page.get_by_role("link", name="Back to My Learning", exact=True).click()
        page.wait_for_url("**/my-learning?path=application-developer")
        page.reload()
        assert _export_my_learning(page) == expected
        page.get_by_role("button", name="Resume Learning Guide", exact=True).click()
        page.wait_for_url("**/?lesson=5&path=application-developer")
        panel = page.get_by_role("region", name="Lesson 5 Learning Guide", exact=True)
        expect(panel.get_by_text("Section 3 of 7", exact=False)).to_be_visible()
        assert_guide_target_fits(page)
        expect(page.get_by_label("Private notes", exact=True)).to_have_value(store["lessons"]["5"]["notes"])
        from agent_lab.ui_learning import REVIEW_ITEMS
        for label in REVIEW_ITEMS:
            expect(page.get_by_role("checkbox", name=label, exact=True)).not_to_be_checked()
        panel.get_by_role("button", name="Close Learning Guide", exact=True).click()
        page.get_by_role("banner").get_by_role("link", name="My Learning", exact=True).click()
        page.wait_for_url("**/my-learning?path=application-developer")
        assert _export_my_learning(page) == expected
    finally:
        context.close()


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_browser_my_learning_phone_large_text_empty_and_saved_states(server, guide_browser_context, tmp_path, dark):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 320, "height": 900})
    try:
        page = context.new_page()
        page.goto(base + "/my-learning")
        page.get_by_role("button", name="Appearance", exact=True).click()
        page.get_by_role("button", name="Dark" if dark else "Light", exact=True).click()
        page.get_by_label("Text size", exact=True).click()
        page.get_by_role("option", name="Extra large", exact=True).click()
        page.keyboard.press("Escape")
        page.keyboard.press("Escape")
        expect(page.locator(".q-menu:visible")).to_have_count(0)
        page.add_style_tag(content=".q-page-container { zoom: 1.5 !important; }")
        expect(page.get_by_role("heading", name="My Learning", exact=True)).to_be_visible()
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), page.evaluate("""() => [...document.querySelectorAll('.my-learning *')]
            .filter(e => e.getClientRects().length && e.getBoundingClientRect().right > innerWidth + 1)
            .slice(0, 12).map(e => ({tag:e.tagName, cls:e.className, right:e.getBoundingClientRect().right}))""")
        page.screenshot(path=str(data / f"my-learning-empty-{dark}.png"), full_page=True)
        page.screenshot(path=str(data / f"my-learning-empty-viewport-{dark}.png"))
        for view in ("Notes", "Quiz results", "Attempts"):
            page.get_by_role("button", name=view, exact=True).click()
            expect(page.get_by_text("No saved work matches these filters.", exact=True)).to_be_visible()
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), page.evaluate("""() => [...document.querySelectorAll('.my-learning *')]
            .filter(e => e.getClientRects().length && e.getBoundingClientRect().right > innerWidth + 1)
            .slice(0, 12).map(e => ({tag:e.tagName, cls:e.className, right:e.getBoundingClientRect().right}))""")
        store = _my_learning_seed() | {"theme": "dark" if dark else "light", "text_size": "xlarge"}
        store["lessons"]["5"]["notes"] += "\n" + "LongSavedText" * 80
        _import_my_learning(page, base, tmp_path, store)
        page.add_style_tag(content=".q-page-container { zoom: 1.5 !important; }")
        page.get_by_role("button", name="Notes", exact=True).click()
        page.get_by_label("Find lessons or saved text", exact=True).fill("Validation note")
        expect(page.get_by_text("1 matching lesson", exact=True)).to_be_visible()
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), page.evaluate("""() => [...document.querySelectorAll('.my-learning *')]
            .filter(e => e.getClientRects().length && e.getBoundingClientRect().right > innerWidth + 1)
            .slice(0, 12).map(e => ({tag:e.tagName, cls:e.className, right:e.getBoundingClientRect().right}))""")
        page.screenshot(path=str(data / f"my-learning-saved-{dark}.png"), full_page=True)
        page.screenshot(path=str(data / f"my-learning-saved-viewport-{dark}.png"))
        assert page.evaluate("window.__workspace_xss") is None
    finally:
        context.close()


def test_browser_my_learning_section_quiz_refresh_does_not_complete_lessons(server, guide_browser_context):
    from playwright.sync_api import expect

    from agent_lab.learning import course

    base, _ = server
    context = guide_browser_context.browser.new_context(viewport={"width": 1440, "height": 1000})
    try:
        page = context.new_page()
        page.goto(base + "/my-learning")
        page.get_by_role("button", name="Quiz results", exact=True).click()
        quiz = course().section_quizzes[0]
        page.get_by_role("button", name=f"Open {quiz.topic} section quiz", exact=True).click()
        dialog = page.get_by_role("dialog")
        dialog.locator(".quiz-question").first.get_by_role("radio").nth(quiz.questions[0].correct).click()
        dialog.locator(".feedback-ok").first.wait_for()
        dialog.get_by_role("button", name="Close", exact=True).click()
        expect(page.get_by_role("button", name=f"Open {quiz.topic} section quiz", exact=True)).to_be_focused()
        expect(page.get_by_text(f"{quiz.topic}: 1 correct / {len(quiz.questions)} questions; 1 answered", exact=True)).to_be_visible()
        expect(page.get_by_text("0 of 75 lessons manually reviewed", exact=True)).to_be_visible()
        progress = _export_my_learning(page)
        assert progress["lessons"] == {} and progress["last_lesson"] == 0
        assert progress["learning_guide_positions"] == {}
        assert progress["sections"][quiz.id]["0"] == quiz.questions[0].correct
    finally:
        context.close()


def test_browser_thinking_comparison_unknown_metrics_and_prompt_free_metadata(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 1440, "height": 1000})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=14")
        page.get_by_role("tab", name="Run the exercise").click()
        page.get_by_label("Comparison setting", exact=True).click()
        page.get_by_role("option", name="Change effort only", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=20000)
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible()
        lanes = page.locator(".thinking-lane")
        expect(lanes).to_have_count(2)
        expect(lanes.nth(0).get_by_text("Observed Stop effort: medium", exact=True)).to_be_visible()
        expect(lanes.nth(1).get_by_text("Observed Stop effort: high", exact=True)).to_be_visible()
        for lane in (lanes.nth(0), lanes.nth(1)):
            expect(lane.get_by_text("SDK latency (ms): Unknown", exact=True)).to_be_visible()
            expect(lane.get_by_text("Input tokens: Unknown", exact=True)).to_be_visible()
        page.locator(".thinking-comparison").evaluate("e => e.scrollIntoView({block:'start'})")
        page.evaluate("window.scrollBy(0, -120)")
        page.screenshot(path=str(data / "thinking-comparison-desktop.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        # Quasar updates its drawer/page padding after the browser resize event.
        # Check the settled phone layout, not the intermediate desktop transition.
        page.wait_for_function("""() => {
            const lanes = [...document.querySelectorAll('.thinking-lane')];
            return lanes.length === 2 &&
                lanes[1].getBoundingClientRect().top >= lanes[0].getBoundingClientRect().bottom &&
                document.documentElement.scrollWidth <= innerWidth + 1;
        }""")
        lanes.nth(0).evaluate("e => e.scrollIntoView({block:'center'})")
        page.screenshot(path=str(data / "thinking-comparison-phone.png"))
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Stop hook has unknown effort", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=20000)
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible()
        expect(page.locator(".thinking-lane").get_by_text("Observed Stop effort: Unknown", exact=True)).to_have_count(2)
        page.get_by_text("Model metadata (no prompt)", exact=True).click()
        page.get_by_role("button", name="Inspect model metadata", exact=True).click()
        expect(page.get_by_text("disabled", exact=True).first).to_be_visible()
        assert not errors
    finally:
        context.close()


def test_browser_usage_accounting_limits_and_separate_session_meter(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 1440, "height": 1000})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=15")
        page.get_by_role("tab", name="Run the exercise").click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=20000)
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible()
        accounting = page.locator(".usage-accounting")
        expect(accounting.get_by_text("Final input tokens: 10", exact=True)).to_be_visible()
        expect(accounting.get_by_text("Final output tokens: 4", exact=True)).to_be_visible()
        accounting.evaluate("e => e.scrollIntoView({block:'start'})")
        page.evaluate("window.scrollBy(0,-120)")
        page.screenshot(path=str(data / "usage-desktop.png"))
        for label, expected in (("Missing final token counts", "Final input tokens: Unknown"), ("Recorded budget threshold stop", "Terminal subtype: error_max_budget_usd")):
            page.get_by_label("Recorded scenario", exact=True).click()
            page.get_by_role("option", name=label, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(accounting.get_by_text(expected, exact=True)).to_be_visible(timeout=20000)
            expect(page.get_by_text("Needs review", exact=True)).to_be_visible()
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Passing example", exact=True).click()
        meter = page.locator(".usage-session")
        meter.get_by_role("button", name="Open usage session", exact=True).click()
        expect(meter.get_by_text("Mode: offline | Messages: 0/4 | Connection closed: False", exact=True)).to_be_visible(timeout=15000)
        for count in (1, 2):
            meter.get_by_role("button", name="Send meter message", exact=True).click()
            expect(meter.get_by_text(f"Mode: offline | Messages: {count}/4 | Connection closed: False", exact=True)).to_be_visible(timeout=15000)
        expect(meter.get_by_text("0.015", exact=True).first).to_be_visible()
        meter.get_by_role("button", name="Inspect session context", exact=True).click()
        expect(meter.get_by_text("recorded context fixture", exact=True)).to_be_visible()
        meter.get_by_role("button", name="Inspect session usage", exact=True).click()
        expect(meter.get_by_text("0.015", exact=True).first).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        meter.get_by_label("Meter message", exact=True).evaluate("e => e.scrollIntoView({block:'center'})")
        page.screenshot(path=str(data / "usage-session-phone.png"))
        meter.get_by_role("button", name="End usage session", exact=True).click()
        expect(meter.get_by_text("Mode: offline | Messages: 2/4 | Connection closed: True", exact=True)).to_be_visible()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible()
        assert not errors
    finally:
        context.close()


@pytest.mark.parametrize("lesson", range(2, 16))
def test_browser_foundation_experiments_controls_scenarios_and_saved_work(server, guide_browser_context, lesson):
    from playwright.sync_api import expect

    from agent_lab.ui_learning import REVIEW_ITEMS

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 1440, "height": 1000})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + f"/?lesson={lesson}")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Run the exercise").click()
        expect(page.locator(".foundation-controls")).to_be_visible()
        expect(page.get_by_label("Prompt", exact=True)).to_be_enabled()
        for index, (scenario, label) in enumerate([
            ("success", "Passing example"), ("missing-evidence", "Missing required evidence"), ("wrong-identity", "Mismatched identity"),
        ]):
            if index == 1:
                page.locator(".foundation-controls").screenshot(path=str(data / f"foundation-{lesson}-desktop-controls.png"))
                page.set_viewport_size({"width": 390, "height": 844})
            page.get_by_label("Recorded scenario", exact=True).click()
            page.get_by_role("option", name=label, exact=True).click()
            if lesson == 13:
                expect(page.get_by_label("Recorded scenario", exact=True)).to_have_value(label)
                page.wait_for_timeout(150)
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.locator(".guide-evidence-target").get_by_text(scenario, exact=True).first).to_be_visible(timeout=20000)
            expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=20000)
            expect(page.get_by_role("button", name="Run exercise", exact=True)).to_be_enabled()
            expect(page.get_by_text("Check passed" if scenario == "success" else "Needs review", exact=True)).to_be_visible()
        page.locator(".foundation-controls").screenshot(path=str(data / f"foundation-{lesson}-phone-controls.png"))
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.get_by_role("tab", name="Python source").click()
        page.get_by_text("How the offline lab checks this concept", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Learn").click()
        question = page.locator(".quiz-question").last
        question.get_by_role("radio").nth(guide(lesson).quiz[-1].correct).click()
        expect(question.locator(".feedback-ok")).to_be_visible()
        draft = f"Lesson {lesson}: correlate the actual operation and terminal evidence."
        page.get_by_label("Your explanation and evidence", exact=True).fill(draft)
        page.get_by_label("Your explanation and evidence", exact=True).blur()
        expect(page.get_by_label("Your explanation and evidence", exact=True)).to_have_value(draft)
        page.get_by_role("button", name="Save attempt", exact=True).click()
        expect(page.get_by_text("1 saved attempts", exact=False)).to_be_visible(timeout=20000)
        page.reload()
        expect(page.get_by_label("Your explanation and evidence", exact=True)).to_have_value(draft)
        expect(page.locator(".quiz-question").last.get_by_role("radio").nth(guide(lesson).quiz[-1].correct)).to_be_checked()
        for label in REVIEW_ITEMS:
            expect(page.get_by_role("checkbox", name=label, exact=True)).not_to_be_checked()
        assert not errors
    finally:
        context.close()


def test_browser_process_spawning_controls_and_evidence(server, guide_browser_context):
    from playwright.sync_api import expect

    base, _ = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        page.goto(base + "/?lesson=36")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Run the exercise").click()
        expect(page.get_by_label("Child action", exact=True)).to_be_visible()
        expect(page.get_by_label("Local machine simulation", exact=True)).to_be_visible()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=20000)
        page.get_by_label("Child action", exact=True).click()
        page.get_by_role("option", name="Timed out child", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=20000)
        page.get_by_role("tab", name="Python source").click()
        page.get_by_text("How the offline lab checks this concept", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    finally:
        context.close()


def test_browser_permission_gate_controls_and_evidence(server, guide_browser_context):
    from playwright.sync_api import expect

    base, _ = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        page.goto(base + "/?lesson=37")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Run the exercise").click()
        expect(page.get_by_label("Gate decision", exact=True)).to_be_visible()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=30000)
        page.get_by_label("Gate decision", exact=True).click()
        page.get_by_role("option", name="Malformed gate response", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=30000)
        page.get_by_role("tab", name="Python source").click()
        page.get_by_text("How the offline lab checks this concept", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    finally:
        context.close()


def test_browser_foundation_permission_dialog_denial_and_cancellation(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        page.goto(base + "/?lesson=4")
        page.get_by_role("tab", name="Run the exercise").click()
        page.get_by_label("Permission decision", exact=True).click()
        page.get_by_role("option", name="Ask me in a permission dialog", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        dialog = page.get_by_role("dialog")
        expect(dialog.get_by_text("Write draft.txt: allow, deny or redirect to approved.txt?", exact=True)).to_be_visible()
        dialog.get_by_role("radio", name="Deny", exact=True).click()
        dialog.get_by_role("button", name="Send answer", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(dialog).to_be_visible()
        dialog.get_by_role("button", name="Cancel run", exact=True).click()
        expect(page.get_by_text("Cancelled", exact=True)).to_be_visible()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible()
    finally:
        context.close()


def test_browser_skills_variants_keep_invocation_check_distinct(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        page.goto(base + "/?lesson=11")
        page.get_by_role("tab", name="Run the exercise").click()
        page.get_by_label("Skill source", exact=True).click()
        page.get_by_role("option", name="Local plugin", exact=True).click()
        for loading, passes in (("Discovery only", False), ("Host preload", False), ("Explicit invocation", True)):
            page.get_by_label("Skill loading", exact=True).click()
            page.get_by_role("option", name=loading, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=20000)
            expect(page.get_by_role("button", name="Run exercise", exact=True)).to_be_enabled()
            expect(page.get_by_text("Check passed" if passes else "Needs review", exact=True)).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        skill_filter = page.get_by_role("checkbox", name="Include the prepared skill in the SDK filter", exact=True)
        expect(skill_filter).to_be_checked()
        skill_filter.click()
        expect(skill_filter).not_to_be_checked()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=20000)
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible()
        page.locator(".foundation-controls").screenshot(path=str(data / "skills-phone-controls.png"))
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator(".foundation-controls").screenshot(path=str(data / "skills-desktop-controls.png"))
    finally:
        context.close()


def test_browser_manual_stream_queue_controls_end_and_cancel(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=12")
        page.get_by_role("tab", name="Run the exercise").click()
        manual = page.get_by_role("checkbox", name="Keep session open for manual messages", exact=True)
        manual.click()
        expect(manual).to_be_checked()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        session = page.locator(".stream-session-controls")
        expect(session.get_by_role("button", name="Queue message", exact=True)).to_be_enabled(timeout=15000)
        expect(session.get_by_text("Successful results 1", exact=False)).to_be_visible(timeout=15000)
        session.get_by_role("button", name="Apply runtime model", exact=True).click()
        expect(session.get_by_text("Acknowledged model: haiku", exact=False)).to_be_visible()
        session.get_by_label("Runtime permission mode", exact=True).click()
        page.get_by_role("option", name="Plan", exact=True).click()
        session.get_by_role("button", name="Apply permission mode", exact=True).click()
        expect(session.get_by_text("Acknowledged permission mode: plan", exact=False)).to_be_visible()
        session.get_by_label("Message to queue", exact=True).fill("Explain the difference between queued and completed.")
        session.get_by_role("button", name="Queue message", exact=True).click()
        expect(session.get_by_text("Submitted 2", exact=False)).to_be_visible()
        session.get_by_role("button", name="End input", exact=True).click()
        expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible()
        expect(session.get_by_text("Connection closed", exact=False)).to_be_visible()
        expect(session.get_by_role("button", name="Queue message", exact=True)).to_be_disabled()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        session.evaluate("e => e.scrollIntoView({block:'start'})")
        page.evaluate("window.scrollBy(0, -120)")
        page.screenshot(path=str(data / "stream-session-phone-upper.png"))
        session.get_by_label("Runtime permission mode", exact=True).evaluate("e => e.scrollIntoView({block:'center'})")
        page.screenshot(path=str(data / "stream-session-phone-lower.png"))
        page.set_viewport_size({"width": 1440, "height": 1000})
        session.screenshot(path=str(data / "stream-session-desktop.png"))
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(session.get_by_role("button", name="Queue message", exact=True)).to_be_enabled(timeout=15000)
        page.get_by_role("button", name="Cancel", exact=True).click()
        expect(page.get_by_text("Cancelled", exact=True)).to_be_visible()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible()
        expect(session.get_by_role("button", name="Queue message", exact=True)).to_be_disabled()
        assert not errors
    finally:
        context.close()


def test_browser_mcp_workshop_real_stock_disable_reconnect_and_end(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=13")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Run the exercise").click()
        workshop = page.locator(".mcp-workshop")
        workshop.get_by_role("button", name="Open MCP workshop", exact=True).click()
        expect(workshop.get_by_text("Last probe connected: True", exact=False)).to_be_visible(timeout=15000)
        expect(workshop.get_by_role("cell", name="12", exact=True)).to_be_visible()
        workshop.get_by_role("button", name="Disable MCP server", exact=True).click()
        expect(workshop.get_by_text("Enabled: False", exact=False)).to_be_visible()
        workshop.get_by_role("button", name="Reserve inventory", exact=True).click()
        expect(workshop.get_by_text("The inventory server is disabled; no transport or tool was started.", exact=True)).to_be_visible()
        expect(workshop.get_by_role("cell", name="12", exact=True)).to_be_visible()
        workshop.get_by_role("button", name="Enable MCP server", exact=True).click()
        expect(workshop.get_by_text("Enabled: True", exact=False)).to_be_visible()
        workshop.get_by_role("button", name="Reserve inventory", exact=True).click()
        expect(workshop.get_by_role("cell", name="10", exact=True)).to_be_visible(timeout=15000)
        workshop.get_by_role("button", name="Reconnect MCP server", exact=True).click()
        expect(workshop.get_by_text("A fresh connection and handshake succeeded; transport closed.", exact=True)).to_be_visible()
        workshop.get_by_role("button", name="Reset workshop inventory", exact=True).click()
        expect(workshop.get_by_role("cell", name="12", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        workshop.evaluate("e => e.scrollIntoView({block:'start'})")
        page.evaluate("window.scrollBy(0, -120)")
        page.screenshot(path=str(data / "mcp-workshop-phone-upper.png"))
        workshop.get_by_role("button", name="End MCP workshop", exact=True).evaluate("e => e.scrollIntoView({block:'center'})")
        page.screenshot(path=str(data / "mcp-workshop-phone-lower.png"))
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.wait_for_function("""() => {
            const target = document.querySelector('.mcp-workshop');
            const drawer = document.querySelector('.q-drawer');
            return target && (!drawer || target.getBoundingClientRect().left >= drawer.getBoundingClientRect().right - 1);
        }""")
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "mcp-workshop-desktop.png"))
        workshop.get_by_role("button", name="End MCP workshop", exact=True).click()
        expect(workshop.get_by_text("Workshop closed: True", exact=False)).to_be_visible()
        expect(workshop.get_by_role("button", name="Reserve inventory", exact=True)).to_be_disabled()
        assert not errors
    finally:
        context.close()


def test_browser_checkpoint_rewind_controls_and_evidence(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=17")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_text("Checkpoint lesson: a disposable SDK edit.", exact=True)).to_be_visible()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Acknowledged rewind without restoration", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Passing example", exact=True).click()
        page.get_by_label("After the edit", exact=True).click()
        page.get_by_role("option", name="Inspect only (does not pass restoration check)", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible()
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "checkpoint-phone.png"))
        assert not errors
    finally:
        context.close()

def test_browser_sandbox_policy_controls_and_sources(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=18")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        for target in ("Outside: synthetic neighbor", "Protected: synthetic config file"):
            page.get_by_label("Owned Read target", exact=True).click()
            page.get_by_role("option", name=target, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=15000)
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible()
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Missing host policy decision", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "sandbox-phone.png"))
        assert not errors
    finally:
        context.close()

def test_browser_session_catalog_operations_and_pagination(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=19")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Page size", exact=True).fill("1")
        page.get_by_label("Page offset", exact=True).fill("20")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible()
        page.get_by_label("Page offset", exact=True).fill("0")
        for operation in ("Rename and tag", "Fork the owned transcript", "Delete this disposable transcript"):
            page.get_by_label("Owned catalog operation", exact=True).click()
            page.get_by_role("option", name=operation, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=15000)
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible()
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Missing SDK catalog observation", exact=True).click()
        expect(page.get_by_label("Recorded scenario", exact=True)).to_have_value("Missing SDK catalog observation")
        page.wait_for_timeout(150)
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "session-catalog-phone.png"))
        assert not errors
    finally:
        context.close()

def test_browser_deep_hooks_variants_and_audit_controls(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=20")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        for behavior in ("Deny before execution", "Rewrite Read to alternate fixture", "Observe missing-file failure", "Contain a synthetic callback error"):
            page.get_by_label("Hook experiment", exact=True).click()
            page.get_by_role("option", name=behavior, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=15000)
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible()
        page.get_by_label("Teaching pre-hook matcher", exact=True).click()
        page.get_by_role("option", name="Write|Edit (does not match Read)", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Completed", exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible()
        audit_toggle = page.get_by_role("checkbox", name="Enable success audit", exact=True)
        audit_toggle.click()
        expect(audit_toggle).not_to_be_checked()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "deep-hooks-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_slash_command_templates_and_discovery_control(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=21")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Command template", exact=True).click()
        page.get_by_role("option", name="Two quiz questions", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Filesystem settings source", exact=True).click()
        page.get_by_role("option", name="No filesystem settings (discovery control)", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "slash-command-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_project_memory_modes_and_owned_rules(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=22")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Owned project rule", exact=True).click()
        page.get_by_role("option", name="Beta marker", exact=True).click()
        page.get_by_label("System prompt", exact=True).click()
        page.get_by_role("option", name="Custom prompt (control)", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Project settings", exact=True).click()
        page.get_by_role("option", name="No project settings", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "project-memory-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_plugin_commands_skill_and_loading_control(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=23")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        for extension in ("Quiz command", "Python example Skill"):
            page.get_by_label("Plugin extension", exact=True).click()
            page.get_by_role("option", name=extension, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Plugin extension", exact=True).click()
        page.get_by_role("option", name="Explain command", exact=True).click()
        enabled = page.get_by_role("checkbox", name="Load the owned local plugin", exact=True)
        enabled.click()
        expect(enabled).not_to_be_checked()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "plugins-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_harness_validation_and_approval_controls(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=24")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        approval = page.get_by_role("checkbox", name="Approve host execution after validation", exact=True)
        approval.click()
        expect(approval).not_to_be_checked()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        for proposal in ("Duplicate file owner", "Dependency cycle", "Outside owned scope"):
            page.get_by_label("Fixed plan proposal", exact=True).click()
            page.get_by_role("option", name=proposal, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Worker execution ledger mismatch", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "harness-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_compaction_bound_and_summary_controls(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=25")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Tool result limit", exact=True).click()
        page.get_by_role("option", name="200 characters", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        summary = page.get_by_role("checkbox", name="Retain compact host progress summary", exact=True)
        summary.click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "compaction-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_control_methods_switch_and_interrupt_controls(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=26")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Second-turn model", exact=True).click()
        page.get_by_role("option", name="Claude Sonnet 5.5", exact=True).click()
        page.get_by_label("Second-turn permission mode", exact=True).click()
        page.get_by_role("option", name="Default", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Control experiment", exact=True).click()
        page.get_by_role("option", name="Interrupt a long turn", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Control acknowledgement absent", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "control-methods-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_background_watcher_endings_and_review(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=27")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Host watcher ending", exact=True).click()
        page.get_by_role("option", name="Release and await", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Watcher cleanup absent", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("missing-cleanup", exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "background-watcher-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_retry_recovery_controls_and_review(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=28")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        for outcome in ("Permanent rejection", "Transient errors exhaust retry limit"):
            page.get_by_label("Fixed refund outcome", exact=True).click()
            page.get_by_role("option", name=outcome, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Idempotency ledger applied twice", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "retry-recovery-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_image_input_colors_and_mime_review(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=29")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Owned image color", exact=True).click()
        page.get_by_role("option", name="Blue square", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="MIME type differs from PNG bytes", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "image-input-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_todo_sequences_and_rejected_ledger(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=30")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        for sequence in ("Skip pending to completed", "Two tasks in progress", "Reopen completed task"):
            page.get_by_label("TodoWrite sequence", exact=True).click()
            page.get_by_role("option", name=sequence, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Committed ledger differs from accepted transitions", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "todo-tracking-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_question_answer_variants_and_missing_callback(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=31")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Simulated host answer", exact=True).click()
        page.get_by_role("option", name="Detailed", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Answer callback absent", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "ask-user-question-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_plan_mode_approval_and_rejection(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=32")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_role("checkbox", name="Approve validated plan in host control", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Fixed plan proposal", exact=True).click()
        page.get_by_role("option", name="Duplicate file owner", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Unexpected worker execution", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "plan-mode-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_mcp_elicitation_actions_and_mismatch(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=33")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        for action in ("Decline booking", "Cancel request"):
            page.get_by_label("Simulated MCP form response", exact=True).click()
            page.get_by_role("option", name=action, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Host response action differs", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "mcp-elicitation-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_output_style_variants_and_changed_file(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=34")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Owned output style", exact=True).click()
        page.get_by_role("option", name="Brief marker", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("SDK setting source", exact=True).click()
        page.get_by_role("option", name="Project disabled", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Owned style file changed", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("changed-style", exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "output-styles-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_session_store_actions_and_evidence(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=35")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_text("How the offline lab checks this concept", exact=True).click()
        page.locator(".foundation-source-excerpt").first.click()
        expect(page.locator("audio")).to_have_count(3)
        audio_source = page.locator("audio").first.get_attribute("src")
        assert audio_source and page.request.get(base + audio_source).status == 200
        page.locator("audio").first.evaluate("element => element.play()")
        page.wait_for_function("document.querySelector('audio')?.currentTime > 0.05")
        page.locator("audio").first.evaluate("element => element.pause()")
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Storage experiment", exact=True).click()
        page.get_by_role("option", name="Interrupt before replace", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Storage experiment", exact=True).click()
        page.get_by_role("option", name="Resume SDK session", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Storage experiment", exact=True).click()
        page.get_by_role("option", name="Resume from SQLite store", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Mirror flush", exact=True).click()
        page.get_by_role("option", name="Batched", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Mirror fault", exact=True).click()
        page.get_by_role("option", name="Delay load", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Mirror fault", exact=True).click()
        page.get_by_role("option", name="None", exact=True).click()
        page.get_by_label("Storage experiment", exact=True).click()
        page.get_by_role("option", name="Commit host transcript", exact=True).click()
        mirror_toggle = page.get_by_role("checkbox", name="Enable SDK session mirror", exact=True)
        mirror_toggle.click()
        expect(mirror_toggle).not_to_be_checked()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        mirror_toggle.click()
        page.get_by_label("Mirror fault", exact=True).click()
        page.get_by_role("option", name="Reject append", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Mirror fault", exact=True).click()
        page.get_by_role("option", name="None", exact=True).click()
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Missing required evidence", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "session-store-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_resume_drops_turn_prepared_and_negative(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=40")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        expect(page.get_by_role("checkbox", name="Try one recovery fork after refusal")).to_be_checked()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Guard refusal evidence missing", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "resume-drops-turn-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_python_client_lifecycle_prepared_and_negative(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=41")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Terminal result missing", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "python-client-lifecycle-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_web_tools_actions_and_negative(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=42")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        for action in ("Search and fetch", "Fetch one page", "Compare page treatment",
                       "Host URL guard", "Research lanes"):
            page.get_by_label("Web experiment", exact=True).click()
            page.get_by_role("option", name=action, exact=True).click()
            expect(page.get_by_role("button", name="Run exercise", exact=True)).to_be_enabled(timeout=15000)
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=15000)
        page.get_by_label("Web experiment", exact=True).click()
        page.get_by_role("option", name="Fetch one page", exact=True).click()
        page.get_by_label("Fixed fetch page", exact=True).click()
        page.get_by_role("option", name="Missing page", exact=True).click()
        expect(page.get_by_role("button", name="Run exercise", exact=True)).to_be_enabled(timeout=15000)
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=15000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "web-tools-phone.png"))
        assert not errors
    finally:
        context.close()




def test_browser_cloud_actions_and_negative(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=45")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-45-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-45-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        page.get_by_text("How the offline lab checks this concept", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.locator(".foundation-source-excerpt").first.click()
        expect(page.locator("audio")).to_have_count(3)
        audio_source = page.locator("audio").first.get_attribute("src")
        assert audio_source and page.request.get(base + audio_source).status == 200
        page.locator("audio").first.evaluate("element => element.play()")
        page.wait_for_function("document.querySelector('audio')?.currentTime > 0.05")
        page.locator("audio").first.evaluate("element => element.pause()")
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        for action in ("Catalog and startup checks", "Five provider formats", "Credential comparison",
                       "Model mapping", "Denied and explicit recovery"):
            page.get_by_label("Cloud experiment", exact=True).click()
            page.get_by_role("option", name=action, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=25000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Cloud wire receipt missing", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=25000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "cloud-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_cache_actions_and_mobile_evidence(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=46")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-46-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-46-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        page.get_by_text("How the offline lab checks this concept", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.locator(".foundation-source-excerpt").first.click()
        expect(page.locator("audio")).to_have_count(3)
        audio_source = page.locator("audio").first.get_attribute("src")
        assert audio_source and page.request.get(base + audio_source).status == 200
        page.locator("audio").first.evaluate("element => element.play()")
        page.wait_for_function("document.querySelector('audio')?.currentTime > 0.05")
        page.locator("audio").first.evaluate("element => element.pause()")
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        for action in ("Cache anatomy", "TTL switch", "Prefix breaker", "Model switch policy"):
            page.get_by_label("Cache experiment", exact=True).click()
            page.get_by_role("option", name=action, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=25000)
            expect(page.get_by_role("columnheader", name="Write 1h")).to_be_visible()
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Cache usage missing", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=25000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "cache-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_orchestra_patterns_and_mobile_evidence(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=47")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-47-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-47-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        page.get_by_text("How the offline lab checks this concept", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        expect(page.locator("audio")).to_have_count(3)
        audio_source = page.locator("audio").first.get_attribute("src")
        assert audio_source and page.request.get(base + audio_source).status == 200
        page.locator("audio").first.evaluate("element => element.play()")
        page.wait_for_function("document.querySelector('audio')?.currentTime > 0.05")
        page.locator("audio").first.evaluate("element => element.pause()")
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        for pattern in ("Orchestrator delegation", "Three-level hierarchy", "Verified pipeline",
                        "Regional fan-out", "Writer and critic"):
            page.get_by_label("Orchestration pattern", exact=True).click()
            page.get_by_role("option", name=pattern, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=25000)
            expect(page.get_by_role("columnheader", name="Host verdict")).to_be_visible()
        page.get_by_label("Orchestration pattern", exact=True).click()
        page.get_by_role("option", name="Regional fan-out", exact=True).click()
        page.get_by_label("Host concurrency", exact=True).click()
        page.get_by_role("option", name="One worker", exact=True).click()
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Cancel north worker", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=25000)
        expect(page.get_by_role("cell", name="cancelled", exact=True).first).to_be_visible()
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "orchestra-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_hardening_lanes_and_mobile_evidence(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=48")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-48-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-48-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        page.get_by_text("How the offline lab checks this concept", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        expect(page.locator("audio")).to_have_count(3)
        audio_source = page.locator("audio").first.get_attribute("src")
        assert audio_source and page.request.get(base + audio_source).status == 200
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        for pattern in ("Path permissions", "Tool and environment lockdown",
                        "Known secret rewrite", "Untrusted ticket"):
            page.get_by_label("Security probe", exact=True).click()
            page.get_by_role("option", name=pattern, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_role("button", name="Run exercise", exact=True)).to_be_enabled(timeout=30000)
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=25000)
            expect(page.get_by_role("columnheader", name="Host decision")).to_be_visible()
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Known canary leaked", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("leaked", exact=True)).to_be_visible(timeout=25000)
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=25000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "hardening-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_headless_processes_worker_and_mobile_evidence(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=49")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-49-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-49-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        page.get_by_text("How the offline lab checks this concept", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        expect(page.locator("audio")).to_have_count(3)
        audio_source = page.locator("audio").first.get_attribute("src")
        assert audio_source and page.request.get(base + audio_source).status == 200
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        for action, action_code in (("CLI and SDK", "headless"),
                                    ("Clean and buggy CI", "ci"),
                                    ("Process failure limits", "limits"),
                                    ("Local worker drain", "deploy")):
            page.get_by_label("Headless action", exact=True).click()
            page.get_by_role("option", name=action, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text(action_code, exact=True)).to_be_visible(timeout=30000)
            expect(page.get_by_role("button", name="Run exercise", exact=True)).to_be_enabled(timeout=30000)
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=25000)
            if action == "Local worker drain":
                expect(page.get_by_text("Local worker: health 200", exact=False)).to_be_visible()
            else:
                expect(page.get_by_role("columnheader", name="Policy code")).to_be_visible()
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Mismatched identity", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=25000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "headless-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_telemetry_actions_and_negative(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=44")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-44-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-44-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_text("How the offline lab checks this concept", exact=True).click()
        page.locator(".foundation-source-excerpt").first.click()
        expect(page.locator("audio")).to_have_count(3)
        audio_source = page.locator("audio").first.get_attribute("src")
        assert audio_source and page.request.get(base + audio_source).status == 200
        page.locator("audio").first.evaluate("element => element.play()")
        page.wait_for_function("document.querySelector('audio')?.currentTime > 0.05")
        page.locator("audio").first.evaluate("element => element.pause()")
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        for action in ("Signal views", "Privacy comparison", "Parent trace",
                       "Denied tool comparison", "Exporter temporality", "Collector authentication"):
            page.get_by_label("Telemetry experiment", exact=True).click()
            page.get_by_role("option", name=action, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=25000)
        page.get_by_label("Signal view", exact=True).click()
        page.get_by_role("option", name="Metrics", exact=True).click()
        expect(page.get_by_text("Metrics: 2 decoded records", exact=True).first).to_be_visible()
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Telemetry export missing", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=25000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "telemetry-phone.png"))
        assert not errors
    finally:
        context.close()

def test_browser_remote_mcp_actions_and_negative(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=43")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-43-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-43-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_text("How the offline lab checks this concept", exact=True).click()
        page.locator(".foundation-source-excerpt").first.click()
        expect(page.locator("audio")).to_have_count(3)
        audio_source = page.locator("audio").first.get_attribute("src")
        assert audio_source and page.request.get(base + audio_source).status == 200
        page.locator("audio").first.evaluate("element => element.play()")
        page.wait_for_function("document.querySelector('audio')?.currentTime > 0.05")
        page.locator("audio").first.evaluate("element => element.pause()")
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        expect(page.get_by_label("Prompt", exact=True)).to_have_attribute("readonly", "")
        for action in ("Machine credential challenge", "Token reuse and renewal",
                       "HTTP and SSE", "Tool inventory", "Resource inventory and read",
                       "Host resource read", "Agent step"):
            page.get_by_label("Remote MCP experiment", exact=True).click()
            page.get_by_role("option", name=action, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=25000)
        for step in ("Read resource", "Rotate credential"):
            page.get_by_label("Agent step", exact=True).click()
            page.get_by_role("option", name=step, exact=True).click()
            page.get_by_role("button", name="Run exercise", exact=True).click()
            expect(page.get_by_text("Check passed", exact=True)).to_be_visible(timeout=25000)
        page.get_by_label("Recorded scenario", exact=True).click()
        page.get_by_role("option", name="Remote MCP evidence missing", exact=True).click()
        page.get_by_role("button", name="Run exercise", exact=True).click()
        expect(page.get_by_text("Needs review", exact=True)).to_be_visible(timeout=25000)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "remote-mcp-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_lesson50_desk_lifecycle(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/?lesson=50")
            expect(page.locator(".quiz-question")).to_have_count(7)
            page.get_by_role("tab", name="Python source", exact=True).click()
            expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
            expect(page.locator("audio")).to_have_count(3)
            page.get_by_role("tab", name="Run the exercise", exact=True).click()
            desk = page.locator(".desk-lab")
            expect(desk.get_by_text("Synthetic support desk", exact=True)).to_be_visible()
            expect(page.get_by_text("Response and results", exact=True)).to_be_hidden()
            desk.get_by_role("button", name="Send support request").click()
            expect(desk.get_by_text("Passed", exact=True)).to_be_visible(timeout=15000)
            desk.get_by_label("Intent", exact=True).click()
            page.get_by_role("option", name="Ticket", exact=True).click()
            desk.get_by_role("button", name="Send support request").click()
            expect(desk.get_by_text("Tickets: 1", exact=True)).to_be_visible(timeout=15000)
            desk.get_by_label("Intent", exact=True).click()
            page.get_by_role("option", name="Refund", exact=True).click()
            desk.get_by_role("button", name="Send support request").click()
            expect(desk.get_by_role("button", name="Deny", exact=True)).to_be_visible(timeout=15000)
            desk.get_by_role("button", name="Deny", exact=True).click()
            expect(desk.get_by_text("Refunds: 0", exact=True)).to_be_visible(timeout=15000)
            desk.get_by_role("button", name="Close to CRM", exact=True).click()
            expect(desk.get_by_text("CRM closed", exact=True)).to_be_visible(timeout=15000)
            desk.get_by_role("button", name="Local evaluations", exact=True).click()
            expect(desk.get_by_text("Local evaluations passed", exact=True)).to_be_visible(timeout=15000)
            page.reload()
            page.get_by_role("tab", name="Run the exercise", exact=True).click()
            expect(page.locator(".desk-lab").get_by_text("Tickets: 1", exact=True)).to_be_visible(timeout=15000)
            page.wait_for_timeout(500)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.screenshot(path=str(data / "desk-lesson50-phone.png"))
            assert not errors
    finally:
        context.close()


def test_browser_lesson51_offline_suite_and_replay(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=51")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-51-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-51-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        expect(page.locator("audio")).to_have_count(3)
        source = page.locator("audio").first.get_attribute("src")
        assert source and page.request.get(base + source).status == 200
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        lab = page.locator(".offline-lab")
        expect(lab).to_be_visible()
        expect(page.get_by_text("Response and results", exact=True)).to_be_hidden()
        lab.get_by_role("button", name="Run offline host suite").click()
        expect(lab.get_by_text("Assertions: 16/16 passed; 0 failed", exact=True)).to_be_visible(timeout=25000)
        expect(lab.get_by_text("Complete-suite check: passed", exact=True)).to_be_visible()
        lab.get_by_text("Mutation challenge: change only the denial policy", exact=True).click()
        lab.get_by_role("button", name="Run offline host suite").click()
        expect(lab.get_by_text("Assertions: 15/16 passed; 1 failed", exact=True)).to_be_visible(timeout=25000)
        expect(lab.get_by_text("Complete-suite check: needs review", exact=True)).to_be_visible()
        lab.get_by_text("Mutation challenge: change only the denial policy", exact=True).click()
        lab.get_by_label("Synthetic replay").click()
        page.get_by_role("option", name="Budget", exact=True).click()
        lab.get_by_role("button", name="Replay synthetic stream").click()
        expect(lab.get_by_text("Host status: budget", exact=False)).to_be_visible(timeout=25000)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "offline-lesson51-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_lesson52_evals_and_calibration(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=52")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-52-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-52-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        lab = page.locator(".evals-lab")
        expect(lab).to_be_visible()
        expect(page.get_by_text("Response and results", exact=True)).to_be_hidden()
        lab.get_by_role("button", name="Run synthetic comparison").click()
        expect(lab.get_by_text("Synthetic check passed", exact=True)).to_be_visible(timeout=25000)
        expect(lab.get_by_text("Comparison: pass", exact=False)).to_be_visible()
        lab.get_by_role("button", name="Calibrate heuristic").click()
        expect(lab.get_by_text("Heuristic calibration:", exact=False)).to_be_visible(timeout=25000)
        lab.get_by_label("Candidate variant").click()
        page.get_by_role("option", name="Cold tone", exact=True).click()
        lab.get_by_role("button", name="Run synthetic comparison").click()
        expect(lab.get_by_text("Comparison: fail", exact=False)).to_be_visible(timeout=25000)
        lab.get_by_role("button", name="Inspect baseline").click()
        expect(lab.get_by_text("Selected baseline: synthetic/heuristic", exact=False)).to_be_visible(timeout=25000)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "evals-lesson52-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_lesson53_debugging_replay_and_recovery(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=53")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-53-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-53-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        lab = page.locator(".debugging-lab")
        expect(lab).to_be_visible()
        lab.get_by_label("Fault scenario").click()
        page.get_by_role("option", name="Denied", exact=True).click()
        lab.get_by_role("button", name="Run prepared replay").click()
        expect(lab.get_by_text("Saved diagnostic passed", exact=True)).to_be_visible(timeout=25000)
        expect(lab.get_by_text("First useful finding: row", exact=False)).to_be_visible()
        run_id = lab.get_by_text("Saved bundle:", exact=False).inner_text().split()[2]
        lab.get_by_label("Compare saved run UUID (optional)").fill(run_id)
        lab.get_by_label("Fault scenario").click()
        page.get_by_role("option", name="Success", exact=True).click()
        lab.get_by_role("button", name="Run prepared replay").click()
        expect(lab.get_by_text("Saved diagnostic passed", exact=True)).to_be_visible(timeout=25000)
        expect(lab.get_by_text("one variable: True", exact=False)).to_be_visible()
        lab.get_by_role("button", name="Recover saved bundle").click()
        expect(lab.get_by_text("Recovered the persisted redacted bundle", exact=True)).to_be_visible(timeout=25000)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "debugging-lesson53-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_lesson54_catalog_contract_and_comparison(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=54")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-54-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-54-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        lab = page.locator(".tool-design-lab")
        expect(lab).to_be_visible()
        lab.get_by_role("button", name="Call selected tool").click()
        expect(lab.get_by_text("Direct catalog_search: OK", exact=True)).to_be_visible(timeout=15000)
        expect(lab.get_by_text("Handler executed: True", exact=False)).to_be_visible()
        lab.get_by_label("Direct JSON arguments").fill('{"category":"camping","maxPriceCents":"3000"}')
        lab.get_by_role("button", name="Call selected tool").click()
        expect(lab.get_by_text("Direct catalog_search: INVALID_INPUT", exact=True)).to_be_visible(timeout=15000)
        lab.get_by_role("button", name="Compare profiles").click()
        expect(lab.get_by_text("Comparison complete", exact=True)).to_be_visible(timeout=20000)
        expect(lab.get_by_text("Automatic check: passed", exact=True)).to_be_visible()
        expect(lab.get_by_text("prepared / vague / concise", exact=True)).to_be_visible()
        expect(lab.get_by_text("prepared / focused / concise", exact=True)).to_be_visible()
        lab.get_by_label("Format", exact=True).click()
        page.get_by_role("option", name="Detailed", exact=True).click()
        expect(lab.get_by_text("Inputs changed; run again for current evidence", exact=True)).to_be_visible()
        lab.get_by_role("button", name="Compare profiles").click()
        expect(lab.get_by_text("prepared / focused / detailed", exact=True)).to_be_visible(timeout=20000)
        lab.get_by_label("Mode", exact=True).click()
        page.get_by_role("option", name="Live, paid", exact=True).click()
        lab.get_by_role("button", name="Run selected consumer").click()
        expect(lab.get_by_text("Fresh paid consent and the reserved comparison budget are required", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "tool-design-lesson54-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_lesson55_offline_upgrade_simulation(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=55")
        expect(page.get_by_text("Offline simulation · no model calls", exact=True).first).to_be_visible()
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-55-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-55-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        lab = page.locator(".upgrading-lab")
        expect(lab).to_be_visible()
        expect(lab.get_by_text("Inventory consistent: True", exact=False)).to_be_visible(timeout=15000)
        lab.get_by_role("button", name="Run compatibility gates").click()
        expect(lab.get_by_text("Compatible fixture eligible", exact=True)).to_be_visible(timeout=15000)
        expect(lab.get_by_text("Automatic diagnostic: passed", exact=True)).to_be_visible()
        lab.get_by_role("button", name="Start simulated canary").click()
        expect(lab.get_by_text("Simulated state: canary", exact=True)).to_be_visible(timeout=15000)
        lab.get_by_role("button", name="Promote simulation").click()
        expect(lab.get_by_text("Simulated state: promoted", exact=True)).to_be_visible(timeout=15000)
        lab.get_by_role("button", name="Roll back simulation").click()
        expect(lab.get_by_text("Simulated state: rolled-back", exact=True)).to_be_visible(timeout=15000)
        lab.get_by_label("Synthetic candidate").click()
        page.get_by_role("option", name="Renamed Result", exact=True).click()
        expect(lab.get_by_text("Candidate changed; run fresh gates", exact=False)).to_be_visible()
        expect(lab.get_by_role("button", name="Start simulated canary")).to_be_disabled()
        lab.get_by_role("button", name="Run compatibility gates").click()
        expect(lab.get_by_text("Incompatible fixture blocked", exact=False)).to_be_visible(timeout=15000)
        expect(lab.get_by_text("Automatic diagnostic: passed", exact=True)).to_be_visible()
        expect(lab.get_by_role("button", name="Start simulated canary")).to_be_disabled()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "upgrading-lesson55-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_lesson56_team_replay_and_native_guard(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=56")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-56-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-56-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        lab = page.locator(".teams-lab")
        expect(lab).to_be_visible()
        expect(lab.get_by_role("button", name="Next walkthrough step")).to_be_enabled(timeout=15000)
        lab.get_by_role("button", name="Next walkthrough step").click()
        lab.get_by_role("button", name="Expand \"Ordered receipts and exact evidence\"").click()
        expect(lab.get_by_text("dependency-incomplete", exact=False).first).to_be_visible(timeout=15000)
        lab.get_by_role("button", name="Run full walkthrough").click()
        expect(lab.get_by_text("Simulated team complete", exact=True)).to_be_visible(timeout=15000)
        expect(lab.get_by_text("automatic check: passed", exact=False)).to_be_visible()
        expect(lab.get_by_text("Messages: evidence-1 acknowledged", exact=True)).to_be_visible()
        lab.get_by_label("Message body").fill("different")
        expect(lab.get_by_text("Inputs changed; replay", exact=False)).to_be_visible()
        lab.get_by_role("button", name="Reset team").click()
        expect(lab.get_by_text("Team reset", exact=False)).to_be_visible()
        expect(lab.get_by_role("button", name="Run native observation")).to_be_disabled()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "teams-lesson56-phone.png"))
        assert not errors
    finally:
        context.close()


def test_browser_lesson57_owned_worktrees(server, guide_browser_context):
    from playwright.sync_api import expect

    base, data = server
    context = guide_browser_context.browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lesson=57")
        expect(page.locator(".quiz-question")).to_have_count(7)
        page.get_by_role("tab", name="Visual guide", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-57-concept-map.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Lab walkthrough", exact=True).click()
        expect(page.locator('img[src="/assets/lesson-57-lab-walkthrough.svg"]')).to_be_visible()
        page.get_by_role("tab", name="Python source", exact=True).click()
        expect(page.locator(".foundation-source-excerpt")).to_have_count(3)
        page.get_by_role("tab", name="Run the exercise", exact=True).click()
        lab = page.locator(".worktrees-lab")
        expect(lab).to_be_visible()
        lab.get_by_role("button", name="Run worktree lab").click()
        expect(lab.get_by_text("Owned report verified", exact=True)).to_be_visible(timeout=30000)
        expect(lab.get_by_text("· prepared · independent · completed · passed", exact=False)).to_be_visible()
        expect(lab.get_by_text("Combined tests: 2 · clean removals: 2 · observed worktrees: 1", exact=True)).to_be_visible()
        lab.get_by_label("Scenario").click()
        page.get_by_role("option", name="Deliberate conflict", exact=True).click()
        expect(lab.get_by_text("Configuration changed; prior check invalidated", exact=False)).to_be_visible()
        lab.get_by_role("button", name="Run worktree lab").click()
        expect(lab.get_by_text("Owned report verified", exact=True)).to_be_visible(timeout=30000)
        expect(lab.get_by_text("· prepared · conflict · conflict · needs-review", exact=False)).to_be_visible()
        expect(lab.get_by_text("Conflict: ['greeting.mjs']", exact=False)).to_be_visible()
        lab.get_by_role("button", name="Recover retained report").click()
        expect(lab.get_by_text("Retained evidence recovered; no new check awarded", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(data / "worktrees-lesson57-phone.png"))
        assert not errors
    finally:
        context.close()
