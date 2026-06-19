"""Tests for the cached ``proxies()`` pool on ``BytefulClient``."""

from __future__ import annotations

import pytest
import responses

from byteful import BytefulClient, ProxyList, ProxyStatus


BASE = "https://api.byteful.com/1.0"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> BytefulClient:
    monkeypatch.setenv("BYTEFUL_API_PUBLIC_KEY", "pub")
    monkeypatch.setenv("BYTEFUL_API_PRIVATE_KEY", "priv")
    return BytefulClient(rate_limiter=None)


def _page(items: list[dict], page: int, per_page: int, total: int) -> dict:
    return {
        "data": items,
        "page": page,
        "per_page": per_page,
        "total_count": total,
        "item_count": len(items),
        "message": "ok",
    }


@responses.activate
def test_proxies_walks_every_page(client: BytefulClient) -> None:
    # 3 proxies split over 2 pages (per_page=2 → page 1 has 2, page 2 has 1)
    responses.add(
        responses.GET,
        f"{BASE}/public/user/proxy/search",
        json=_page(
            [
                {"proxy_id": "a", "proxy_status": "in_use"},
                {"proxy_id": "b", "proxy_status": "in_use"},
            ],
            page=1, per_page=2, total=3,
        ),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/public/user/proxy/search",
        json=_page(
            [{"proxy_id": "c", "proxy_status": "available"}],
            page=2, per_page=2, total=3,
        ),
        status=200,
    )

    pool = client.proxies(per_page=2)
    assert isinstance(pool, ProxyList)
    assert len(pool) == 3
    assert [p.proxy_id for p in pool] == ["a", "b", "c"]
    assert pool.total_count == 3


@responses.activate
def test_proxies_is_cached_across_calls(client: BytefulClient) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/public/user/proxy/search",
        json=_page([{"proxy_id": "a"}], page=1, per_page=500, total=1),
        status=200,
    )

    pool1 = client.proxies()
    pool2 = client.proxies()
    assert pool1 is pool2
    assert len(responses.calls) == 1


@responses.activate
def test_proxies_refresh_forces_refetch(client: BytefulClient) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/public/user/proxy/search",
        json=_page([{"proxy_id": "a"}], page=1, per_page=500, total=1),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/public/user/proxy/search",
        json=_page([{"proxy_id": "b"}], page=1, per_page=500, total=1),
        status=200,
    )

    pool1 = client.proxies()
    pool2 = client.proxies(refresh=True)
    assert pool1 is not pool2
    assert pool2[0].proxy_id == "b"
    assert len(responses.calls) == 2


@responses.activate
def test_invalidate_proxy_cache_drops_pool(client: BytefulClient) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/public/user/proxy/search",
        json=_page([{"proxy_id": "a"}], page=1, per_page=500, total=1),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/public/user/proxy/search",
        json=_page([{"proxy_id": "b"}], page=1, per_page=500, total=1),
        status=200,
    )

    client.proxies()
    client.invalidate_proxy_cache()
    pool2 = client.proxies()
    assert pool2[0].proxy_id == "b"


def test_proxy_list_filter() -> None:
    from byteful import Proxy, ProxyList

    proxies = [
        Proxy.from_api({"proxy_id": "a", "country_id": "us", "proxy_type": "isp",
                        "proxy_status": "in_use", "proxy_user_ids": ["x"]}),
        Proxy.from_api({"proxy_id": "b", "country_id": "de", "proxy_type": "isp",
                        "proxy_status": "in_use", "proxy_user_ids": ["x"]}),
        Proxy.from_api({"proxy_id": "c", "country_id": "us", "proxy_type": "residential",
                        "proxy_status": "available", "proxy_user_ids": ["y"]}),
    ]
    pl = ProxyList(proxies=proxies, total_count=3)

    us = pl.filter(country_id="us")
    assert [p.proxy_id for p in us] == ["a", "c"]

    us_isp = pl.filter(country_id="us", proxy_type="isp")
    assert [p.proxy_id for p in us_isp] == ["a"]

    by_user = pl.filter(proxy_user_id="y")
    assert [p.proxy_id for p in by_user] == ["c"]

    in_use = pl.filter(proxy_status=ProxyStatus.IN_USE)
    assert [p.proxy_id for p in in_use] == ["a", "b"]


def test_proxy_list_random() -> None:
    import random
    from byteful import Proxy, ProxyList

    proxies = [Proxy.from_api({"proxy_id": str(i)}) for i in range(5)]
    pl = ProxyList(proxies=proxies, total_count=5)
    rng = random.Random(42)
    pick = pl.random(rng=rng)
    assert pick.proxy_id in {"0", "1", "2", "3", "4"}

    empty = ProxyList(proxies=[], total_count=0)
    with pytest.raises(IndexError):
        empty.random()
