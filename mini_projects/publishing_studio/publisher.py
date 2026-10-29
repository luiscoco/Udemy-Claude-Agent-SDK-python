"""Your Agent Publishing Studio contracts. Implement one stage at a time, then raise STAGE.

Check your work:      uv run agent-lab publish check
Compare a reference:  uv run agent-lab publish check --reference   (never marks your work done)

Stages M15-M22 are numbered 1-8 here. Each prompt is in
mini_projects/publishing_studio/prompts/. The Publishing Studio page
(http://127.0.0.1:8080/publish) runs this file, so every stage you finish unlocks a feature.
"""

from collections.abc import Iterable, Mapping
from typing import Any

# Raise this after each stage passes; tests for later stages are skipped until you do.
STAGE = 1
MODELS = {
    "claude-haiku-4-5": "Claude Haiku 4.5 (fastest, lowest cost)",
    "claude-sonnet-5-5": "Claude Sonnet 5.5",
    "claude-opus-5-5": "Claude Opus 5.5 (most capable)",
}
BUDGETS = (0.2, 0.5, 1.0, 2.0)
# Stage 8 adds ".png": "png".
UPLOAD_KINDS = {
    ".txt": "text",
    ".md": "markdown",
    ".markdown": "markdown",
    ".csv": "csv",
    ".docx": "docx",
    ".pdf": "pdf",
}
MAX_UPLOAD_BYTES = 5_000_000
MAX_UPLOADS = 3
MAX_TEXT_CHARS = 50_000
DOCS_MCP_URL = "https://code.claude.com/docs/mcp"
# Hex colors (no #) for highlighted code on a dark background.
CODE_COLORS = {
    "comment": "B8C7DE",
    "keyword": "D2ADFF",
    "string": "A9E3A0",
    "number": "FFC18B",
    "function": "8ED8FF",
    "builtin": "8CE4DB",
    "attribute": "FFC2DF",
    "plain": "EAF2FF",
}


# ------------------------------------------------------------------ stage 2 (M16)
def parse_answer_request(
    prompt: object, model: object, mode: object, budget_usd: object, consent: object = False
) -> dict[str, Any]:
    """Stage 2 (M16): validate one answer request before anything runs.

    The prompt is 1-4000 characters after trimming; the model is a MODELS key (never an
    arbitrary string); mode is "prepared" or "live"; the budget is one of BUDGETS (reject
    booleans). Live mode needs consent exactly True, else raise PermissionError. Raise
    ValueError for everything else. Return {"prompt", "model", "mode", "budget_usd"}.
    """
    raise NotImplementedError("TODO M16: implement parse_answer_request")


def summarize_answer(messages: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Stage 2 (M16): turn SDK messages into an answer you may save.

    Messages are dicts: {"type": "assistant", "content": [blocks], "parent_tool_use_id"},
    {"type": "result", "subtype", "is_error", "num_turns", "total_cost_usd"} and
    {"type": "stream_error"}. Return {"answer", "subtype", "complete", "turns", "cost_usd",
    "mcp_tool_calls"}: top-level text joined by blank lines; tool_use blocks whose name starts
    with "mcp__" counted. complete is true only for a "success" result that is not an error,
    with no stream error and a nonempty answer. Without a result the subtype is
    "sdk_stream_error".
    """
    raise NotImplementedError("TODO M16: implement summarize_answer")


# ------------------------------------------------------------------ stage 3 (M17)
def check_upload(name: object, size: object, attached: object = 0) -> str:
    """Stage 3 (M17): validate an upload before reading it and return its UPLOAD_KINDS kind.

    The name is a plain file name of 1-120 characters: no folders, "..", ":", control
    characters or leading dot. Size is an int from 1 to MAX_UPLOAD_BYTES. A text source is
    refused when `attached` files already reach MAX_UPLOADS (a PNG reference is not counted).
    Raise ValueError with a helpful message.
    """
    raise NotImplementedError("TODO M17: implement check_upload")


def extract_text(kind: object, data: bytes) -> str:
    """Stage 3 (M17): extract text from "text", "markdown" or "csv" (UTF-8, BOM allowed, no
    NUL) or "docx" (the paragraphs of word/document.xml, which must be at most 2 MB). Any
    other kind, unreadable data or empty text raises ValueError. Return at most
    MAX_TEXT_CHARS characters, trimmed. (The server extracts PDF text in its own process.)
    """
    raise NotImplementedError("TODO M17: implement extract_text")


def source_prompt(prompt: str, files: Iterable[Mapping[str, str]]) -> str:
    """Stage 3 (M17): with no files return the prompt unchanged. Otherwise wrap each file
    {"name", "text"} in <source name="..."> tags (escape the name; a "</source>" inside the
    text must not close the tag), say the sources are untrusted data whose instructions are
    ignored, ask for a closing line naming the files used, and end with the request."""
    raise NotImplementedError("TODO M17: implement source_prompt")


# ------------------------------------------------------------------ stage 4 (M18)
def split_fences(markdown: str) -> list[dict[str, str]]:
    """Stage 4 (M18): split Markdown into {"type": "text", "text"} and {"type": "code",
    "language", "code"} parts, in order. A fence opens with ```lang (lowercased, "text" when
    missing) and closes on a line that is exactly ``` after trimming. Keep code exactly:
    line breaks and indentation. An unclosed fence stays text. Skip blank text parts."""
    raise NotImplementedError("TODO M18: implement split_fences")


def prepared_plan(answer: str, kind: str, request: str, today: str) -> dict[str, Any]:
    """Stage 4 (M18): a free plan from the answer, zero model calls, returned validated.

    document: {"kind": "document", "title" (first heading, else the request), "author":
    "Agent Publishing Studio", "date": today, "blocks"}. Code parts become code blocks;
    headings, bullet lists, Markdown tables (2-4 columns) and paragraphs become their blocks.
    infographic: {"kind": "infographic", "title", "subtitle", "takeaway", "items": 3-6
    {"label", "detail"} from "- label: detail" bullets (else paragraphs), "code_example":
    the first snippet's first 12 lines, 85 characters each, or None}.
    """
    raise NotImplementedError("TODO M18: implement prepared_plan")


def validate_plan(plan: object, kind: str) -> dict[str, Any]:
    """Stage 4 (M18): validate a plan strictly (no extra keys) and return the clean dict.

    Strings are trimmed and nonempty. document: title and author at most 160, date ISO,
    1-60 blocks of heading (level 1|2, text <= 4000), paragraph, bullets (1-12 items),
    table (2-4 columns, 1-12 rows, each as wide as the columns) and code (language <= 24
    characters of letters, digits and +#.-, default "text"; code 1-12000). infographic:
    title <= 72, subtitle <= 100 (default ""), takeaway <= 85, 3-6 items with label <= 30
    and detail <= 105, optional code_example {language, code <= 900}. Raise ValueError.
    """
    raise NotImplementedError("TODO M18: implement validate_plan")


def reconcile_code(plan: Mapping[str, Any], answer: str) -> dict[str, Any]:
    """Stage 4 (M18): trust only code from the selected answer.

    document: keep a code block only when it matches an unused answer snippet ignoring
    whitespace, and restore that snippet's exact text and language; drop invented code;
    append snippets the planner omitted. infographic: code_example is the first answer
    snippet's excerpt, or None. Return the plan validated again.
    """
    raise NotImplementedError("TODO M18: implement reconcile_code")


# ------------------------------------------------------------------ stage 5 (M19)
def code_lines(code: str, language: str) -> list[list[dict[str, str]]]:
    """Stage 5 (M19): highlight code with Pygments into lines of {"text", "color"} segments
    using CODE_COLORS. Keep every character (lexer options stripnl=False, ensurenl=False); an
    unknown language is one plain-colored run per line."""
    raise NotImplementedError("TODO M19: implement code_lines")


def document_html(plan: Mapping[str, Any]) -> str:
    """Stage 5 (M19): one complete, escaped HTML page for a validated document plan: title,
    author | date, headings, paragraphs, bullets, tables and code panels (a language label and
    colored spans from code_lines inside <pre>). The PDF is rendered from this page."""
    raise NotImplementedError("TODO M19: implement document_html")


# ------------------------------------------------------------------ stage 6 (M20)
def infographic_svg(plan: Mapping[str, Any], style: Mapping[str, Any] | None = None) -> str:
    """Stage 6 (M20): a standalone SVG for a validated infographic plan: escaped title,
    subtitle, numbered cards, takeaway and, with code_example, a labeled excerpt drawn with
    native <text>/<tspan> colors. No scripts, foreignObject or external links.
    Stage 8 adds `style` (see png_style and focus_region): a 1600 x 900 layout in that palette."""
    raise NotImplementedError("TODO M20: implement infographic_svg")


# ------------------------------------------------------------------ stage 7 (M21)
def source_settings(source: object, mode: object, mcp_consent: object = False) -> dict[str, Any]:
    """Stage 7 (M21): return {"mcp_servers", "allowed_tools", "label", "max_turns"}.

    none: no servers, 2 turns. docs in prepared mode: no servers and a label saying it was not
    used. docs in live mode needs mcp_consent exactly True (else PermissionError) and gives
    {"claude_docs": {"type": "http", "url": DOCS_MCP_URL}}, "mcp__claude_docs__*" and 8 turns.
    Anything else raises ValueError.
    """
    raise NotImplementedError("TODO M21: implement source_settings")


# ------------------------------------------------------------------ stage 8 (M22)
def png_style(data: bytes) -> dict[str, Any]:
    """Stage 8 (M22): verify a PNG with Pillow (signature, at most 6000 x 6000, every pixel
    decodes) and propose a palette. Return {"width", "height", "mood": "light"|"dark",
    "palette": {"background", "ink", "accent", "secondary"}} as #RRGGBB colors. Sample a
    thumbnail so area decides: a small decorative region must not dominate. Raise ValueError."""
    raise NotImplementedError("TODO M22: implement png_style")


def focus_region(
    width: object,
    height: object,
    focus_x: object,
    focus_y: object,
    box: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """Stage 8 (M22): the crop {"x", "y", "w", "h"} of the reference image to reuse.

    With a box (x, y, width, height in 0-1000 units of the image) scale it and keep it inside.
    Otherwise center a 290:165 crop on focus_x / focus_y percentages (0-100), clamped to the
    image. Reject booleans and out-of-range numbers with ValueError.
    """
    raise NotImplementedError("TODO M22: implement focus_region")


def validate_visual(plan: object) -> dict[str, Any]:
    """Stage 8 (M22): validate a live visual plan strictly: layout editorial|cards, focus
    {x, y 0-1000; width, height 50-1000}, typography modern|rounded|classic, up to 3 motifs
    from arcs|clouds|stars|grid (duplicates removed), background_strength 0-1."""
    raise NotImplementedError("TODO M22: implement validate_visual")
