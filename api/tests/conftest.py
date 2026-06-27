import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

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
