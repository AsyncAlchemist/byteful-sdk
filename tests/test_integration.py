"""Live integration tests that hit api.byteful.com.

Skipped unless both ``BYTEFUL_API_PUBLIC_KEY`` and ``BYTEFUL_API_PRIVATE_KEY``
are set. Run explicitly with ``uv run pytest -m integration``.

These tests are READ-ONLY by design — no checkout, no edits, no deletes —
so they're safe to run against a production account.
"""

from __future__ import annotations

import os

import pytest

from byteful import BytefulClient

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def keys() -> tuple[str, str]:
    pub = os.environ.get("BYTEFUL_API_PUBLIC_KEY")
    priv = os.environ.get("BYTEFUL_API_PRIVATE_KEY")
    if not pub or not priv:
        pytest.skip("BYTEFUL_API_PUBLIC_KEY / _PRIVATE_KEY not set")
    return pub, priv


@pytest.fixture(scope="module")
def client(keys: tuple[str, str]) -> BytefulClient:
    pub, priv = keys
    with BytefulClient(api_public_key=pub, api_private_key=priv) as c:
        yield c


def test_customer_retrieve_live(client: BytefulClient) -> None:
    me = client.customer_retrieve()
    assert me.customer_id is not None


def test_country_search_live(client: BytefulClient) -> None:
    page = client.country_search(per_page=5)
    assert page.item_count <= 5
    if page.data:
        assert page.data[0].country_id


def test_proxy_search_first_page_live(client: BytefulClient) -> None:
    page = client.proxy_search(per_page=5, page=1)
    assert page.page == 1
    assert page.per_page == 5
