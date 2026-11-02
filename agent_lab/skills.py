"""Owned skill fixtures and progressive-disclosure experiments for lesson 11.

The parser intentionally handles only simple frontmatter in these prepared files.
It is not a general YAML parser. Offline invocation uses a recorded SDK tool pair;
reading a file here is never represented as an observed live Skill call.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import ClaudeAgentOptions

from agent_lab.foundation_models import SkillsInputs
from agent_lab.models import RunRequest
from agent_lab.policy import decide

if TYPE_CHECKING:
    from agent_lab.foundations import Evidence

NAME = "lesson-summary"
PLUGIN = "lesson-skills"
SKILL_TEXT = (
    "---\nname: lesson-summary\n"
    "description: Summarize a Python lesson with one example.\n---\n"
    "Read notes.txt. Return a concise summary and a Python example.\n"
    "If you need the checklist, read resources/checklist.md relative to this skill.\n"
)
SUPPORT_TEXT = "# Review checklist\n\nCheck the example syntax and explain one limitation.\n"


def owned_path(root: Path, relative: str) -> Path:
    """Resolve prepared paths inside the owned root, including symlink resolution."""
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("The skill fixture must remain inside its owned workspace.")
    return target


def skill_directory(source: str) -> str:
    return (
        ".claude/skills/lesson-summary"
        if source == "project"
        else "teaching-skills/skills/lesson-summary"
    )


def prepare_skills(root: Path) -> None:
    for source in ("project", "plugin"):
        directory = skill_directory(source)
        for filename, text in (("SKILL.md", SKILL_TEXT), ("resources/checklist.md", SUPPORT_TEXT)):
            target = owned_path(root, directory + "/" + filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    manifest = owned_path(root, "teaching-skills/.claude-plugin/plugin.json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"name": PLUGIN, "version": "1.0.0"}), encoding="utf-8")


def parse_skill(text: str) -> dict[str, Any]:
    """Separate simple, single-line frontmatter from the instruction body."""
    lines = text.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise ValueError("A prepared skill needs delimited frontmatter.")
    end = lines.index("---", 1)
    metadata = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if (
            not separator
            or key not in {"name", "description"}
            or key in metadata
            or not value.strip()
        ):
            raise ValueError("Use unique name and description fields with simple values.")
        metadata[key] = value.strip()
    if set(metadata) != {"name", "description"} or not "\n".join(lines[end + 1 :]).strip():
        raise ValueError("A skill needs name, description and instructions.")
    return {"metadata": metadata, "body": "\n".join(lines[end + 1 :]) + "\n"}


def skill_name(selected: dict[str, Any]) -> str:
    return NAME if selected["discovery"] == "project" else f"{PLUGIN}:{NAME}"


def configure_skills(
    options: ClaudeAgentOptions, root: Path, request: RunRequest
) -> dict[str, Any]:
    """Configure real SDK discovery/filtering; preload is an explicit host adaptation."""
    selected = SkillsInputs.model_validate(request.lesson_options).model_dump()
    prepare_skills(root)
    directory = skill_directory(selected["discovery"])
    parsed = parse_skill(owned_path(root, directory + "/SKILL.md").read_text(encoding="utf-8"))
    # Always explicit: SDK skills defaults may otherwise include personal user settings.
    options.setting_sources = ["project"] if selected["discovery"] == "project" else []
    options.plugins = (
        [{"type": "local", "path": str(owned_path(root, "teaching-skills"))}]
        if selected["discovery"] == "plugin"
        else []
    )
    visible = selected["visible"] and selected["loading"] != "preload"
    options.skills = [skill_name(selected)] if visible else []
    options.tools = ["Read", "Skill"]
    appendix = "Use concise Python examples. Access only this lesson's prepared files."
    if selected["loading"] == "preload":
        appendix += "\nHost-preloaded instructions (no Skill invocation):\n" + parsed["body"]
        if selected["load_support"]:
            appendix += owned_path(root, directory + "/resources/checklist.md").read_text(
                encoding="utf-8"
            )
    options.system_prompt = {"type": "preset", "preset": "claude_code", "append": appendix}
    return {
        "skills": options.skills,
        "plugins": options.plugins,
        "skill_loading": {
            "strategy": selected["loading"],
            "source": selected["discovery"],
            "host_inventory": parsed["metadata"],
            "host_preloaded_body": selected["loading"] == "preload",
            "note": "Host inventory is not runtime discovery. skills=[] is a context filter, not a filesystem sandbox.",
        },
    }


def skill_prompt(request: RunRequest) -> str:
    selected = SkillsInputs.model_validate(request.lesson_options).model_dump()
    prompt = request.prompt
    if selected["loading"] == "invoke":
        prompt = (
            f"Invoke the {skill_name(selected)} skill using the Skill tool, then answer: {prompt}"
        )
    if selected["load_support"]:
        prompt += "\nRead the selected skill's resources/checklist.md if available."
    return prompt


def skill_policy(
    root: Path, selected: dict[str, Any], name: str, arguments: dict[str, Any]
) -> tuple[bool, str]:
    if name == "Skill":
        allowed = (
            selected["visible"]
            and selected["loading"] != "preload"
            and arguments.get("skill") == skill_name(selected)
        )
        return bool(allowed), "Only the visible, prepared lesson skill may be invoked."
    if name == "Read":
        raw = arguments.get("file_path")
        if isinstance(raw, str):
            try:
                target = Path(raw)
                if not target.is_absolute():
                    target = root / target
                relative = target.resolve().relative_to(root.resolve()).as_posix()
                allowed_paths = {
                    skill_directory(source) + "/" + filename
                    for source in ("project", "plugin")
                    for filename in ("SKILL.md", "resources/checklist.md")
                }
                # Filtering hides the listing, not these non-secret files.
                if relative in allowed_paths and owned_path(root, relative).is_file():
                    return True, "Read an exact prepared, non-secret skill file."
            except (ValueError, OSError):
                return False, "Read only prepared workspace files."
        return decide(root, name, arguments)
    return False, "Only Read and the selected Skill are available."


async def local_skills(evidence: "Evidence", request: RunRequest) -> dict[str, Any]:
    """Actually parse/load files, and label the separately recorded SDK invocation."""
    from agent_lab.foundations import record_call

    selected = evidence.selected
    directory = skill_directory(selected["discovery"])
    parsed = parse_skill(
        owned_path(evidence.root, directory + "/SKILL.md").read_text(encoding="utf-8")
    )
    timeline: list[dict[str, Any]] = [{"stage": "host-inspection", "metadata": parsed["metadata"]}]
    result: dict[str, Any] = {
        "timeline": timeline,
        "model_context": "Not measured offline; these are host file-loading observations.",
        "generated_files_verified": False,
    }
    if selected["loading"] == "preload":
        timeline.append({"stage": "host-preload", "body": parsed["body"]})
    elif selected["loading"] == "invoke":
        arguments = {"skill": skill_name(selected)}
        record_call(evidence, "Skill", arguments, "fixture-skill-1")
        allowed, reason = skill_policy(evidence.root, selected, "Skill", arguments)
        evidence.results.append(
            {"id": "fixture-skill-1", "is_error": not allowed, "run_id": evidence.run_id}
        )
        timeline.append({"stage": "recorded-sdk-invocation", "allowed": allowed, "reason": reason})
        if allowed:
            timeline.append({"stage": "host-load", "body": parsed["body"]})
    if selected["load_support"] and any(
        row["stage"] in {"host-load", "host-preload"} for row in timeline
    ):
        timeline.append(
            {
                "stage": "host-support-load",
                "content": owned_path(
                    evidence.root, directory + "/resources/checklist.md"
                ).read_text(encoding="utf-8"),
            }
        )
    return result
