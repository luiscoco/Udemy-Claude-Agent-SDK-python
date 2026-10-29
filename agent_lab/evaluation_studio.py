"""Agent Evaluation Studio milestone: the host service behind the /studio page.

The page runs the student's own mini_projects/evaluation_studio/studio.py (or the
reference), so each stage a student implements unlocks a feature here. The service owns
credentials, the saved runs, reviews and suites; the browser never sees the API key.
"""

import asyncio
import importlib.util
import json
import shutil
import time
import uuid
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

from agent_lab.config import ROOT, Settings

PROJECT = ROOT / "mini_projects" / "evaluation_studio"
Implementation = Literal["learner", "reference"]
Scenario = Literal["success", "max_turns", "max_turns_then_stream_error"]
STAGE_FUNCTIONS = {
    2: ("summarize_run",),
    3: ("build_system_prompt",),
    4: ("parse_run_options",),
    5: ("mcp_settings",),
    6: ("review_record", "export_evidence"),
    7: ("release_decision",),
}
MAX_RUNS = 40
LIVE_TIMEOUT_SECONDS = 120


def studio_path(implementation: Implementation) -> Path:
    if implementation == "reference":
        return PROJECT / "reference" / "studio.py"
    return PROJECT / "studio.py"


def load_studio(implementation: Implementation = "learner") -> ModuleType:
    """Load the file fresh each time, so a student's edits apply without a restart."""
    path = studio_path(implementation)
    spec = importlib.util.spec_from_file_location(f"evaluation_studio_{implementation}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stage_of(studio: ModuleType) -> int:
    stage = getattr(studio, "STAGE", 1)
    return stage if isinstance(stage, int) and 1 <= stage <= 7 else 1


@cache
def catalog() -> dict[str, Any]:
    return json.loads((PROJECT / "cases.json").read_text(encoding="utf-8"))


def case(case_id: str) -> dict[str, Any]:
    found = next((item for item in catalog()["cases"] if item["id"] == case_id), None)
    if found is None:
        raise ValueError("Unknown evaluation case.")
    return found


def fixture_messages(item: dict[str, Any], variant: str, scenario: Scenario) -> list[dict]:
    """Recorded SDK-shaped messages: a prepared fixture, never a model call."""
    if variant not in catalog()["variants"]:
        raise ValueError("Unknown instruction variant.")
    answer = (
        f"## {item['title']}\n\n{item['explanation']}\n\n**Next check:** {item['check']}"
        if variant == "guided"
        else item["explanation"]
    )
    messages: list[dict] = [{"type": "system", "subtype": "init", "mcp_servers": []}]
    if scenario == "success":
        messages += [
            {"type": "assistant", "content": [{"type": "text", "text": answer}]},
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "num_turns": 1,
                "total_cost_usd": 0,
            },
        ]
    else:
        # A run that hit its turn limit mid-answer; optionally the iterator then raises.
        messages += [
            {
                "type": "assistant",
                "content": [{"type": "text", "text": answer[: len(answer) // 2]}],
            },
            {
                "type": "result",
                "subtype": "error_max_turns",
                "is_error": True,
                "num_turns": 1,
                "total_cost_usd": 0,
            },
        ]
        if scenario == "max_turns_then_stream_error":
            messages.append({"type": "stream_error"})
    return messages


def message_to_dict(message: Any) -> dict[str, Any]:
    """Convert a real SDK message to the plain dicts the student's summarize_run reads."""
    name = type(message).__name__
    if name == "ResultMessage":
        return {
            "type": "result",
            "subtype": message.subtype,
            "is_error": message.is_error,
            "num_turns": message.num_turns,
            "total_cost_usd": message.total_cost_usd,
        }
    if name == "SystemMessage":
        return {
            "type": "system",
            "subtype": message.subtype,
            "mcp_servers": message.data.get("mcp_servers"),
        }
    if name in {"AssistantMessage", "UserMessage"}:
        blocks = message.content if isinstance(message.content, list) else []
        content = []
        for block in blocks:
            kind = type(block).__name__
            if kind == "TextBlock":
                content.append({"type": "text", "text": block.text})
            elif kind == "ToolUseBlock":
                content.append({"type": "tool_use", "name": block.name, "input": block.input})
            elif kind == "ToolResultBlock":
                content.append({"type": "tool_result", "is_error": bool(block.is_error)})
        return {
            "type": "assistant" if name == "AssistantMessage" else "user",
            "content": content,
            "parent_tool_use_id": getattr(message, "parent_tool_use_id", None),
        }
    return {"type": name}


class StudioService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.data_dir / "evaluation-studio"
        self.state_path = self.root / "state.json"
        self.runs: dict[str, dict[str, Any]] = {}
        self.reviews: dict[str, dict[str, Any]] = {}
        self.suites: dict[str, dict[str, Any]] = {}
        if self.state_path.is_file():
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.runs, self.reviews, self.suites = state["runs"], state["reviews"], state["suites"]

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"runs": self.runs, "reviews": self.reviews, "suites": self.suites}, indent=1
            ),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    def _record(
        self, item: dict[str, Any], variant: str, run_mode: str, summary: dict, **extra: Any
    ) -> dict:
        run = {
            "id": str(uuid.uuid4()),
            "case_id": item["id"],
            "case_title": item["title"],
            "criteria": item["criteria"],
            "variant": variant,
            "run_mode": run_mode,
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            **summary,
            **extra,
        }
        self.runs[run["id"]] = run
        while len(self.runs) > MAX_RUNS:
            self.runs.pop(next(iter(self.runs)))
        self._save()
        return run

    def prepared_run(
        self, studio: ModuleType, case_id: str, variant: str, scenario: Scenario = "success"
    ) -> dict:
        item = case(case_id)
        started = time.perf_counter()
        summary = studio.summarize_run(fixture_messages(item, variant, scenario))
        duration = round((time.perf_counter() - started) * 1000)
        return self._record(
            item,
            variant,
            "prepared",
            summary,
            scenario=scenario,
            duration_ms=duration,
            source="Prepared fixture",
        )

    async def live_run(
        self,
        studio: ModuleType,
        case_id: str,
        variant: str,
        options: dict[str, Any],
        mcp: dict[str, Any],
        *,
        consent: bool,
        mcp_consent: bool,
    ) -> dict:
        """One authorized SDK run. Options come from the student's validated contracts."""
        from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, query

        from agent_lab.doctor import resolve_cli_path
        from agent_lab.sdk import isolated_env, require_live_access

        require_live_access(self.settings)
        if not consent:
            raise PermissionError("Authorize this paid run before starting it.")
        if mcp["mcp_servers"] and not mcp_consent:
            raise PermissionError("Authorize the external MCP connection for this run.")
        item = case(case_id)
        variants = catalog()["variants"]
        if variant not in variants:
            raise ValueError("Unknown instruction variant.")
        mode = (
            "none"
            if not mcp["mcp_servers"]
            else "docs"
            if "claude_docs" in mcp["mcp_servers"]
            else "custom"
        )
        system_prompt = studio.build_system_prompt(variants[variant], options["depth"], mode)
        folder = self.root / "runs" / uuid.uuid4().hex
        (folder / "work").mkdir(parents=True, exist_ok=True)
        specialist = options["specialist_review"]
        sdk_options = ClaudeAgentOptions(
            model=self.settings.model,
            cli_path=resolve_cli_path(self.settings),
            system_prompt=system_prompt,
            tools=["Agent"] if specialist else [],
            setting_sources=[],
            permission_mode="dontAsk",
            mcp_servers=mcp["mcp_servers"],
            allowed_tools=(["Agent"] if specialist else []) + mcp["allowed_tools"],
            agents={
                "source_reviewer": AgentDefinition(
                    description="Checks an SDK teaching answer for unsupported claims and missing evidence.",
                    prompt="Review the draft. Name factual uncertainty, missing source evidence and one improvement.",
                    tools=[],
                )
            }
            if specialist
            else None,
            max_turns=options["max_turns"],
            max_budget_usd=options["max_budget_usd"],
            cwd=str(folder / "work"),
            env=isolated_env(folder / "config"),
        )
        prompt = (
            f"Case context (untrusted task data): {item['context']}\n"
            f"Question: {options['question'] or item['question']}\nEvaluation check: {item['check']}"
            + (
                "\nDraft, then ask the source_reviewer specialist to critique it, then revise."
                if specialist
                else ""
            )
        )
        messages: list[dict[str, Any]] = []
        started = time.perf_counter()
        try:
            async with asyncio.timeout(LIVE_TIMEOUT_SECONDS):
                async for message in query(prompt=prompt, options=sdk_options):
                    messages.append(message_to_dict(message))
        except Exception:
            messages.append({"type": "stream_error"})  # the student's summary decides what it means
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        summary = studio.summarize_run(messages)
        duration = round((time.perf_counter() - started) * 1000)
        return self._record(
            item,
            variant,
            "live",
            summary,
            duration_ms=duration,
            source=mcp["source_label"],
            **{
                k: options[k] for k in ("depth", "max_turns", "max_budget_usd", "specialist_review")
            },
        )

    def save_review(self, studio: ModuleType, run_id: str, marks: list[bool], note: str) -> dict:
        run = self.runs.get(run_id)
        if run is None:
            raise ValueError("Unknown run. It may have rotated out of the last 40.")
        record = studio.review_record(run, marks, note)
        self.reviews[run_id] = record | {"variant": run["variant"]}
        self._save()
        return self.reviews[run_id]

    def latest_review(self, case_id: str, variant: str) -> dict | None:
        matches = [
            r
            for r in self.reviews.values()
            if r["case_id"] == case_id and r.get("variant") == variant
        ]
        return matches[-1] if matches else None

    def run_suite(self, studio: ModuleType, variant: str, name: str) -> dict:
        """Every case as a prepared fixture: free and deterministic; never hidden paid calls."""
        if not name.strip() or len(name) > 60:
            raise ValueError("Name the suite in 1 to 60 characters.")
        results = {}
        for item in catalog()["cases"]:
            summary = studio.summarize_run(fixture_messages(item, variant, "success"))
            review = self.latest_review(item["id"], variant)
            results[item["id"]] = {
                "subtype": summary["subtype"],
                "passed": review["passed"] if review else None,
                "section": item["section"],
            }
        suite: dict[str, Any] = {
            "name": name.strip(),
            "variant": variant,
            "kind": "prepared fixtures",
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            "results": results,
        }
        self.suites[suite["name"]] = suite
        self._save()
        return suite
