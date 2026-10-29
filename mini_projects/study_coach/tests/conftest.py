import os

import pytest

from agent_lab.study_coach import load_coach, stage_of


@pytest.fixture(scope="session")
def coach():
    """COACH_IMPLEMENTATION=reference checks the reference; the default is your coach.py."""
    implementation = os.environ.get("COACH_IMPLEMENTATION", "learner")
    assert implementation in {"learner", "reference"}, implementation
    return load_coach(implementation)


@pytest.fixture(autouse=True)
def stage_gate(request, coach):
    marker = request.node.get_closest_marker("stage")
    if marker and stage_of(coach) < marker.args[0]:
        pytest.skip(f"Stage {marker.args[0]}: implement it, then set STAGE = {marker.args[0]}.")


def pytest_configure(config):
    config.addinivalue_line("markers", "stage(n): runs once coach.STAGE reaches n")
