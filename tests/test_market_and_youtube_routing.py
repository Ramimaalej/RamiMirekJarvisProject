from __future__ import annotations

from actions.intent_router import IntentRouter
from actions import stock_market, youtube_video


def test_xauusd_price_request_routes_with_symbol() -> None:
    result = IntentRouter().route("what xauusd price rn")

    assert result.matched is True
    assert result.intent_name == "stock_market"
    assert result.handler_name == "stock_market"
    assert result.handler_params == {"symbol": "XAUUSD"}


def test_youtube_playlist_request_never_routes_to_app_launcher() -> None:
    result = IntentRouter().route("open a Tunisian playlist on YouTube")

    assert result.matched is True
    assert result.intent_name == "youtube_video"
    assert result.handler_name == "youtube_video"
    assert result.handler_params == {
        "action": "open_search",
        "query": "tunisian playlist",
    }


def test_xauusd_uses_live_spot_endpoint(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "price": 2389.25,
                "currency": "USD",
                "updatedAt": "2026-08-27T11:18:50Z",
            }

    def fake_get(url: str, **_kwargs):
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr(stock_market.requests, "get", fake_get)
    result = stock_market.get_stock_price({"symbol": "XAUUSD"})

    assert captured["url"] == "https://api.gold-api.com/price/XAU"
    assert "MARKET DATA (XAU/USD): 2,389.25 USD per troy ounce" in result


def test_youtube_open_search_opens_a_search_url(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(youtube_video, "_open_url", opened.append)

    result = youtube_video.youtube_video({
        "action": "open_search",
        "query": "tunisian playlist",
    })

    assert opened == [
        "https://www.youtube.com/results?search_query=tunisian+playlist"
    ]
    assert "Opened YouTube search for 'tunisian playlist'" in result
