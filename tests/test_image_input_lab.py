import base64
import struct
import zlib
from pathlib import Path

import pytest

from agent_lab.image_input_lab import (
    COLORS,
    MIME,
    QUESTION,
    SIZE,
    image_turn,
    local_image_input,
    make_png,
    validated_image,
)
from agent_lab.models import LessonError, RunRequest, lesson_request


@pytest.mark.parametrize("color", ["red", "blue"])
def test_generated_png_contains_selected_pixels(tmp_path: Path, color: str) -> None:
    data = make_png(color)
    path = tmp_path / "square.png"
    path.write_bytes(data)
    assert validated_image(path)[0] == data
    marker = data.index(b"IDAT")
    length = struct.unpack(">I", data[marker - 4:marker])[0]
    pixels = zlib.decompress(data[marker + 4:marker + 4 + length])
    assert pixels[:4] == b"\x00" + bytes(COLORS[color])
    assert len(pixels) == SIZE * (1 + SIZE * 3)


async def test_typed_message_contains_exact_png_and_question() -> None:
    data = make_png("red")
    sent = []
    messages = [message async for message in image_turn(data, sent)]
    assert len(messages) == len(sent) == 1
    content = messages[0]["message"]["content"]
    assert content[0]["source"]["media_type"] == MIME
    assert base64.b64decode(content[0]["source"]["data"], validate=True) == data
    assert content[1] == {"type": "text", "text": QUESTION}


@pytest.mark.parametrize("color", ["red", "blue"])
async def test_offline_image_variants_pass(tmp_path: Path, color: str) -> None:
    report = (await local_image_input(tmp_path, RunRequest(lesson_options={"color": color})))["experiment"]
    assert report["experiment_passed"] is True
    assert report["observed_answer"] == color.upper()
    assert report["owned_file_unchanged"] is True


@pytest.mark.parametrize("scenario", ["missing-evidence", "wrong-identity", "wrong-mime", "changed-file", "missing-yield", "wrong-answer"])
async def test_offline_image_negative_scenarios_need_review(tmp_path: Path, scenario: str) -> None:
    report = (await local_image_input(tmp_path, RunRequest(scenario=scenario)))["experiment"]
    assert report["experiment_passed"] is False
    assert report["expected_check"] == "needs-review"


def test_invalid_image_and_request_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "square.png"
    path.write_bytes(b"not a PNG")
    with pytest.raises(LessonError):
        validated_image(path)
    with pytest.raises(ValueError):
        lesson_request(29, {"lesson_options": {"color": "green"}})
    with pytest.raises(LessonError):
        lesson_request(29, {"mode": "live", "scenario": "wrong-mime"})
