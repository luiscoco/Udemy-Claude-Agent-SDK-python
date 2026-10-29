import os

import pytest

from agent_lab.evaluation_studio import load_studio, stage_of


@pytest.fixture(scope="session")
def studio():
    """STUDIO_IMPLEMENTATION=reference checks the reference; the default is your studio.py."""
    implementation = os.environ.get("STUDIO_IMPLEMENTATION", "learner")
    assert implementation in {"learner", "reference"}, implementation
    return load_studio(implementation)


@pytest.fixture(autouse=True)
def stage_gate(request, studio):
    marker = request.node.get_closest_marker("stage")
    if marker and stage_of(studio) < marker.args[0]:
        pytest.skip(f"Stage {marker.args[0]}: implement it, then set STAGE = {marker.args[0]}.")


def pytest_configure(config):
    config.addinivalue_line("markers", "stage(n): runs once studio.STAGE reaches n")
