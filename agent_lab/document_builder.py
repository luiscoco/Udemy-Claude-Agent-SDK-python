"""Build branded Word documents from a strict, validated Python specification."""

import datetime
import json
import re
from pathlib import Path
from typing import Annotated, Literal

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Heading(StrictModel):
    type: Literal["heading"]
    level: Literal[1, 2]
    text: str = Field(min_length=1, max_length=120)


class Paragraph(StrictModel):
    type: Literal["paragraph"]
    text: str = Field(min_length=1, max_length=1500)


class Items(StrictModel):
    type: Literal["bullets", "numbered"]
    items: list[Annotated[str, Field(min_length=1, max_length=400)]] = Field(
        min_length=1, max_length=20
    )


class Table(StrictModel):
    type: Literal["table"]
    columns: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        min_length=1, max_length=6
    )
    rows: list[list[Annotated[str, Field(max_length=500)]]] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def rectangular(self) -> "Table":
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("Every table row must have one cell per column.")
        return self


class Callout(StrictModel):
    type: Literal["callout"]
    tone: Literal["info", "warning"]
    text: str = Field(min_length=1, max_length=600)


Block = Annotated[Heading | Paragraph | Items | Table | Callout, Field(discriminator="type")]


class DocumentSpec(StrictModel):
    kind: Literal["general", "incident-report"]
    title: str = Field(min_length=1, max_length=90)
    subtitle: str = Field(default="", max_length=120)
    author: str = Field(min_length=1, max_length=80)
    date: datetime.date
    classification: Literal["Public", "Internal", "Confidential"]
    blocks: list[Block] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def incident_sections(self) -> "DocumentSpec":
        if self.kind != "incident-report":
            return self
        required = ["Summary", "Impact", "Timeline", "Root cause", "Action items"]
        headings = [
            block.text for block in self.blocks if isinstance(block, Heading) and block.level == 1
        ]
        positions = [headings.index(name) if name in headings else -1 for name in required]
        if -1 in positions or positions != sorted(positions):
            raise ValueError(
                "Incident headings must include Summary, Impact, Timeline, Root cause and Action items in order."
            )
        if not isinstance(self.blocks[0], Callout) or self.blocks[0].tone != "info":
            raise ValueError(
                "An incident report starts with an info callout stating severity and status."
            )
        active = ""
        timeline = actions = False
        for block in self.blocks:
            if isinstance(block, Heading) and block.level == 1:
                active = block.text
            if isinstance(block, Table):
                if active == "Timeline" and block.columns == ["Time (UTC)", "Event"]:
                    timeline = True
                if active == "Action items" and {"Owner", "Due"} <= set(block.columns):
                    actions = True
        if not timeline or not actions:
            raise ValueError("Incident reports require the Timeline and Action items tables.")
        return self


def inline(paragraph, text: str) -> None:
    for index, part in enumerate(re.split(r"\*\*(.*?)\*\*", text)):
        paragraph.add_run(part).bold = bool(index % 2)


def build_document(spec: DocumentSpec, destination: Path) -> Path:
    document = Document()
    section = document.sections[0]
    section.top_margin = section.bottom_margin = Inches(0.75)
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    for name in ["Title", "Heading 1", "Heading 2"]:
        document.styles[name].font.color.rgb = RGBColor.from_string("7C3AED")
    document.add_heading(spec.title, 0)
    if spec.subtitle:
        document.add_paragraph(spec.subtitle, "Subtitle")
    document.add_paragraph(f"{spec.author} · {spec.date.isoformat()} · {spec.classification}")
    for block in spec.blocks:
        if isinstance(block, Heading):
            document.add_heading(block.text, block.level)
        elif isinstance(block, Paragraph):
            inline(document.add_paragraph(), block.text)
        elif isinstance(block, Items):
            for item in block.items:
                inline(
                    document.add_paragraph(
                        style="List Bullet" if block.type == "bullets" else "List Number"
                    ),
                    item,
                )
        elif isinstance(block, Table):
            table = document.add_table(rows=1, cols=len(block.columns))
            table.style = "Light Shading Accent 1"
            for cell, value in zip(table.rows[0].cells, block.columns, strict=True):
                cell.text = value
            for row in block.rows:
                for cell, value in zip(table.add_row().cells, row, strict=True):
                    cell.text = value
        else:
            paragraph = document.add_paragraph()
            inline(paragraph, block.text)
            for run in paragraph.runs:
                run.font.color.rgb = RGBColor.from_string(
                    "B45309" if block.tone == "warning" else "0F766E"
                )
    section.footer.paragraphs[0].text = f"Atmira · {spec.classification}"
    document.core_properties.title = spec.title
    document.core_properties.author = spec.author
    destination.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(destination))
    return destination


def main() -> None:
    import argparse

    from agent_lab.policy import inside

    parser = argparse.ArgumentParser()
    parser.add_argument("spec")
    parser.add_argument("output")
    arguments = parser.parse_args()
    try:
        source = inside(Path.cwd(), arguments.spec)
        target = inside(Path.cwd(), arguments.output)
        if not target.is_relative_to(Path.cwd() / "out") or target.suffix != ".docx":
            raise ValueError("Output must be a .docx inside out/.")
        if source.stat().st_size > 250000:
            raise ValueError("Specification is too large.")
        specification = DocumentSpec.model_validate(json.loads(source.read_text(encoding="utf-8")))
        build_document(specification, target)
        print(f"Built {target}")
    except (ValueError, OSError) as exc:
        print(f"SPEC ERROR: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
