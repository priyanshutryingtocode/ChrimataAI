from __future__ import annotations

import pytest

import helpers


@pytest.fixture()
def client(tmp_path):
    test_client, _ = helpers.make_test_client(tmp_path)
    yield test_client
    helpers.release_test_client()
