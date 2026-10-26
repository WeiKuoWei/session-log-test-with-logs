import pytest

from intake.settings import Paths, Settings, load_schema
from intake.store import Store


@pytest.fixture
def schema():
    return load_schema()


@pytest.fixture
def settings():
    return Settings(provider="mock", model="test-model", max_tokens=1500, workers=2,
                    timeout_seconds=5, max_retries=0, policy_version="policy-1")


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
