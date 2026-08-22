from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
for path in (str(BACKEND_DIR), str(ROOT_DIR / "scripts")):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(autouse=True)
def disable_live_llm():
    from app.core.config import settings

    original = settings.llm_api_key
    settings.llm_api_key = ""
    yield
    settings.llm_api_key = original


@pytest.fixture()
def client(tmp_path):
    import helpers

    test_client, _ = helpers.make_test_client(tmp_path)
    yield test_client
    helpers.release_test_client()
