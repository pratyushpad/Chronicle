import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# app.db builds its engine from DATABASE_URL at import time; tests never
# connect, so any well-formed DSN lets router modules import in CI.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test")

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def greenhouse_response():
    return json.loads((FIXTURES / "greenhouse_stripe.json").read_text())


@pytest.fixture
def lever_response():
    return json.loads((FIXTURES / "lever_sample.json").read_text())


@pytest.fixture
def ashby_response():
    return json.loads((FIXTURES / "ashby_sample.json").read_text())


@pytest.fixture
def mock_client():
    client = AsyncMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    client.get.return_value = response
    return client, response
