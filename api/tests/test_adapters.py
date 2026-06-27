import pytest

from app.ingest.adapters.greenhouse import GreenhouseAdapter
from app.ingest.adapters.lever import LeverAdapter
from app.ingest.adapters.ashby import AshbyAdapter


@pytest.mark.asyncio
async def test_greenhouse_adapter(greenhouse_response, mock_client):
    client, response = mock_client
    response.json.return_value = greenhouse_response

    adapter = GreenhouseAdapter()
    jobs = await adapter.fetch("stripe", client)

    assert len(jobs) == 2
    assert jobs[0].source_job_id == "123456"
    assert jobs[0].title == "Software Engineer, Backend (Req #9999)"
    assert jobs[0].apply_url == "https://boards.greenhouse.io/stripe/jobs/123456"
    assert jobs[0].department == "Engineering"
    assert "<strong>backend engineer</strong>" in (jobs[0].description_html or "")
    assert jobs[1].location == "San Francisco, CA"


@pytest.mark.asyncio
async def test_lever_adapter(lever_response, mock_client):
    client, response = mock_client
    response.json.return_value = lever_response

    adapter = LeverAdapter()
    jobs = await adapter.fetch("sample", client)

    assert len(jobs) == 2
    assert jobs[0].source_job_id == "abc-def-123"
    assert jobs[0].title == "Frontend Engineer"
    assert jobs[0].employment_type == "Full-time"
    assert jobs[0].department == "Engineering"
    assert jobs[0].posted_at == "1705312800000"


@pytest.mark.asyncio
async def test_ashby_adapter(ashby_response, mock_client):
    client, response = mock_client
    response.json.return_value = ashby_response

    adapter = AshbyAdapter()
    jobs = await adapter.fetch("sample", client)

    assert len(jobs) == 2
    assert jobs[0].source_job_id == "ashby-001"
    assert jobs[0].remote is True
    assert jobs[0].employment_type == "FullTime"
    assert jobs[1].remote is False


@pytest.mark.asyncio
async def test_greenhouse_raises_on_error(mock_client):
    import httpx
    client, response = mock_client
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=None, response=None
    )

    adapter = GreenhouseAdapter()
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.fetch("bad-slug", client)
