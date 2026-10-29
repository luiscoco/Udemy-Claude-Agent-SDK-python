import os

import pytest

from agent_lab.publishing_studio import load_publisher, stage_of


@pytest.fixture(scope="session")
def publisher():
    """PUBLISHER_IMPLEMENTATION=reference checks the reference; the default is your publisher.py."""
    implementation = os.environ.get("PUBLISHER_IMPLEMENTATION", "learner")
    assert implementation in {"learner", "reference"}, implementation
    return load_publisher(implementation)


@pytest.fixture(autouse=True)
def stage_gate(request, publisher):
    marker = request.node.get_closest_marker("stage")
    if marker and stage_of(publisher) < marker.args[0]:
        pytest.skip(f"Stage {marker.args[0]}: implement it, then set STAGE = {marker.args[0]}.")


def pytest_configure(config):
    config.addinivalue_line("markers", "stage(n): runs once publisher.STAGE reaches n")
