import json
import re

import pytest

from agent_lab.config import ROOT
from agent_lab.curriculum import LESSONS


def test_every_lesson_has_a_python_entry_point_and_consistent_tutorial():
    index = json.loads((ROOT / "curriculum.json").read_text(encoding="utf-8"))
    assert len(index) == len(LESSONS) == 75
    for row in index:
        module = ROOT.joinpath(*row["module"].split(".")).with_suffix(".py")
        assert module.is_file()
        document = (ROOT / row["document"]).read_text(encoding="utf-8")
        assert f"# Lesson {row['id']}: {row['title']}" in document
        assert f"uv run agent-lab lesson {row['id']}" in document
        assert not re.search(r"```(?:ts|typescript|js|javascript)\b", document)
        for destination in re.findall(r"\]\(([^)]+)\)", document):
            if destination.startswith(("http:", "https:", "#")):
                continue
            assert (ROOT / destination).is_file(), (row["document"], destination)


def test_document_builder_runs_in_python_only_checkout(tmp_path, monkeypatch):
    from scripts import build_curriculum

    index = (ROOT / "curriculum.json").read_text(encoding="utf-8")
    (tmp_path / "curriculum.json").write_text(index, encoding="utf-8")
    monkeypatch.setattr(build_curriculum, "ROOT", tmp_path)
    build_curriculum.main()
    assert not (tmp_path / ".migration").exists()
    assert len(list(tmp_path.glob("Tab*.md"))) == 75
    assert len(list((tmp_path / "agent_lab/lessons").glob("lesson_*.py"))) == 75


@pytest.mark.parametrize("invalid_document", ["../outside.md", "Tab1-../outside.md", "Tab1-lesson.ts"])
def test_document_builder_rejects_unsafe_index_before_writing(tmp_path, monkeypatch, invalid_document):
    from scripts import build_curriculum

    index = json.loads((ROOT / "curriculum.json").read_text(encoding="utf-8"))
    index[0]["document"] = invalid_document
    (tmp_path / "curriculum.json").write_text(json.dumps(index), encoding="utf-8")
    monkeypatch.setattr(build_curriculum, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="Invalid lesson document"):
        build_curriculum.main()
    assert not (tmp_path / "agent_lab").exists()
