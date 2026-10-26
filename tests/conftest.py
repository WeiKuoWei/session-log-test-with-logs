import shutil

import pytest

from helpers import MATERIALS, REPO
from intake.settings import Paths, Settings, load_schema
from intake.store import Store


@pytest.fixture
def workspace(tmp_path):
    """A throwaway copy of the inputs, policy and mock replies, for CLI-level tests."""
    shutil.copytree(MATERIALS, tmp_path / "materials" / "requests")
    shutil.copytree(REPO / "mock_replies", tmp_path / "mock_replies")
    shutil.copy(MATERIALS.parent / "office-policy.md", tmp_path / "materials" / "office-policy.md")
    shutil.copytree(REPO / "expected", tmp_path / "expected")
    shutil.copytree(REPO / "tests" / "fixtures" / "paraphrase",
                    tmp_path / "tests" / "fixtures" / "paraphrase")
    return Paths(root=tmp_path)


@pytest.fixture
def schema():
    return load_schema()


@pytest.fixture
def settings():
    return Settings(provider="mock", model="test-model", max_tokens=1500, workers=2,
                    timeout_seconds=5, max_retries=0)


@pytest.fixture
def paths(tmp_path):
    return Paths(root=tmp_path)


@pytest.fixture
def store(paths):
    return Store(paths)


@pytest.fixture
def inbox(paths):
    paths.input_dir.mkdir(parents=True)
    return paths.input_dir
