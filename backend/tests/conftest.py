import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    # Tests never depend on the developer's credential/configuration file.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, app_env="test", database_url=f"sqlite:///{tmp_path}/test.db")


@pytest.fixture
def application(settings):
    return create_app(settings)


@pytest.fixture
def client(application):
    with TestClient(application) as test_client:
        yield test_client
