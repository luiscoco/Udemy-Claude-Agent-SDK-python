"""Per-lesson "how this exercise is built" diagrams, derived from the exercise's own code.

Each diagram is generated from the source the lesson actually runs, so it cannot drift
out of date: the exercise function, the parts of the system it uses, the evidence it
returns and what the automatic check tests.
"""

import ast
import inspect
import re
from dataclasses import dataclass

from agent_lab import exercises
from agent_lab.curriculum import LESSONS
from agent_lab.learning import guide


@dataclass(frozen=True)
class Component:
    pattern: str  # regular expression matched against the exercise source
    label: str
    kind: str  # sdk, fixture, host, process, external, data


COMPONENTS = [
    # Official SDK code
    Component(r"\bClaudeSDKClient\b", "ClaudeSDKClient", "sdk"),
    Component(r"(?<![.\w])query\(", "SDK query()", "sdk"),
    Component(r"\bClaudeAgentOptions\(", "ClaudeAgentOptions", "sdk"),
    Component(r"\bAgentDefinition\b", "AgentDefinition", "sdk"),
    Component(r"\bAssistantMessage\b|\bResultMessage\b", "SDK message types", "sdk"),
    Component(r"list_sessions|get_session_messages", "SDK session functions", "sdk"),
    Component(r"create_sdk_mcp_server|@sdk\.tool", "SDK MCP tool", "sdk"),
    Component(r"create_connected_server_and_client_session", "In-memory MCP session", "sdk"),
    Component(r"\binspect_remote\b", "Remote MCP client", "sdk"),
    # Fixtures
    Component(r"\bScriptedCLI\b", "Scripted CLI fixture", "fixture"),
    # Host code
    Component(r"\blesson_hooks\b|\bcall_hook\b", "Hook callbacks", "host"),
    Component(r"\bpermission_callback\b", "can_use_tool callback", "host"),
    Component(r"\bdecide\(|\binside\(", "Path policy", "host"),
    Component(r"\bredact\(", "Redaction", "host"),
    Component(r"\bApproval\(", "Exact-action approval", "host"),
    Component(r"\bPlan\b", "Plan validation", "host"),
    Component(r"\bexecute_plan\b", "Plan workers", "host"),
    Component(r"\bCalculation\b|\bSummary\b|\bRefund\b|\bQuestions\b", "Pydantic models", "host"),
    Component(r"\bRunRequest\.model_validate", "Request validation", "host"),
    Component(r"setting_sources_for|isolated_env", "Settings isolation", "host"),
    Component(r"\bBudget\(", "Budget ledger", "host"),
    Component(r"asyncio\.timeout", "Deadline", "host"),
    Component(r"asyncio\.create_task|asyncio\.gather", "Async tasks", "host"),
    Component(r"\bBoard\(", "Message board", "host"),
    Component(r"TracerProvider", "OpenTelemetry spans", "host"),
    Component(r"\bcreate_app\b", "FastAPI app", "host"),
    Component(r"\bSettings\(", "Lab settings", "host"),
    # Separate processes, servers and transports
    Component(r"create_subprocess_exec", "Child process", "process"),
    Component(r"\bworktree\b", "Git worktrees", "process"),
    Component(r"\bstdio_client\b", "MCP server over stdio", "external"),
    Component(r"\bEmbeddedServer\b", "Local HTTP server", "external"),
    Component(r"websockets", "WebSocket client", "external"),
    Component(r"browser_mcp", "Browser MCP service", "external"),
    # Files and data
    Component(r"\bOrders\(", "SQLite orders", "data"),
    Component(r"\bJournal\(", "Journal file", "data"),
    Component(r"\bDocument\(", "Word document", "data"),
    Component(r"tomllib", "pyproject and uv.lock", "data"),
    Component(r"\bretrieve\(", "Policy retrieval", "data"),
    Component(r"rglob|\.claude|SKILL\.md|CLAUDE\.md", "Project .claude files", "data"),
    Component(r"plugin\.json", "Plugin manifest", "data"),
    Component(r"base64", "Image content block", "data"),
    Component(r"\bcsv\.", "CSV data", "data"),
    Component(r"os\.getenv", "Environment variables", "data"),
    Component(r"temporary\.replace", "Atomic file write", "data"),
]
HOST_LOGIC = Component("", "Host Python logic", "host")

STYLES = {
    "sdk": "fill:#ede9fe,stroke:#7c3aed,color:#1f1d2e",
    "fixture": "fill:#fef3c7,stroke:#d97706,color:#1f1d2e",
    "host": "fill:#e0f2fe,stroke:#0284c7,color:#1f1d2e",
    "process": "fill:#fce7f3,stroke:#db2777,color:#1f1d2e",
    "external": "fill:#dcfce7,stroke:#16a34a,color:#1f1d2e",
    "data": "fill:#f1f5f9,stroke:#64748b,color:#1f1d2e",
    "edge": "fill:#ffffff,stroke:#7c3aed,color:#1f1d2e",
}
LEGEND = {
    "sdk": "Official SDK code",
    "fixture": "Scripted fixture",
    "host": "Host code in agent_lab",
    "process": "Separate process",
    "external": "Server or transport",
    "data": "Files and data",
}


def exercise_code(name: str) -> str:
    """The exercise, the module-level helpers it calls, and scripts it runs in a child."""
    function = exercises.EXERCISES[name]
    source = inspect.getsource(function)
    tree = ast.parse(source)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    helpers = [
        inspect.getsource(value)
        for helper in sorted(called)
        if inspect.isfunction(value := getattr(exercises, helper, None))
        and value is not function
        and value.__module__ == exercises.__name__
    ]
    scripts = [
        value
        for name in sorted(names)
        if isinstance(value := getattr(exercises, name, None), str) and "\n" in value
    ]
    return "\n".join([source, *helpers, *scripts])


def components(lesson_id: int) -> list[Component]:
    code = exercise_code(LESSONS[lesson_id].exercise)
    found = [item for item in COMPONENTS if re.search(item.pattern, code)]
    return found or [HOST_LOGIC]


def text(value: str) -> str:
    """Mermaid labels are quoted; quotes and brackets would break the syntax."""
    return re.sub(r"[\"<>{}|`]", "", value)


def exercise_diagram(lesson_id: int) -> str:
    lesson, item = LESSONS[lesson_id], guide(lesson_id)
    function = exercises.EXERCISES[lesson.exercise].__name__
    lines = [
        "flowchart LR",
        '  run(["Run the exercise"])',
        f'  ex["{text(function)}()<br/>agent_lab/exercises.py"]',
        "  run --> ex",
    ]
    for number, part in enumerate(components(lesson_id)):
        lines += [f'  c{number}["{text(part.label)}"]', f"  ex --> c{number}"]
        lines.append(f"  class c{number} {part.kind}")
    keys = ", ".join(dict.fromkeys(check.key for check in item.evidence_checks))
    lines += [
        f'  ev["Evidence<br/>{text(keys)}"]',
        "  ex --> ev",
        '  check{"Automatic check"}',
        "  ev --> check",
        "  class run,ex,ev,check edge",
    ]
    lines += [f"  classDef {kind} {style}" for kind, style in STYLES.items()]
    return "\n".join(lines)


def legend(lesson_id: int) -> dict[str, str]:
    used = {part.kind for part in components(lesson_id)}
    return {kind: label for kind, label in LEGEND.items() if kind in used}
