from __future__ import annotations

import threading

from actions.intent_router import IntentRouter
from actions import stock_market, youtube_video
from core import jarvis_llm
from core.jarvis_llm import _llm_unavailable_reply, _offline_identity_scope_reply


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


def test_first_olympus_identity_prompt_is_a_safe_offline_baseline() -> None:
    prompt = (
        "You are JARVIS MARK XL assisting a student preparing a morning study "
        "plan. State your role, name one real capability, and name one "
        "capability you must not claim without evidence."
    )

    routed = IntentRouter().route(prompt)
    reply = _offline_identity_scope_reply(prompt)

    assert routed.matched is False
    assert routed.requires_ai is True
    assert "I am JARVIS MARK XL" in reply
    assert "must not claim" in reply
    assert "confirmed tool result" in reply


def test_unavailable_model_is_reported_as_a_connection_issue_not_a_refusal() -> None:
    reply = _llm_unavailable_reply("Connection refused at http://localhost:11434")

    assert "I could not reach the configured AI provider" in reply
    assert "Ollama" in reply
    assert reply != "I cannot do that."


def test_unrelated_prompt_does_not_use_identity_baseline() -> None:
    assert _offline_identity_scope_reply("Write a study plan for chemistry.") == ""


def test_first_olympus_prompt_reaches_visible_assistant_response(monkeypatch) -> None:
    class FakeUi:
        muted = False

        def __init__(self):
            self.messages: list[str] = []
            self.states: list[str] = []

        def set_state(self, state: str) -> None:
            self.states.append(state)

        def write_log(self, message: str) -> None:
            self.messages.append(message)

        def write_log_instant(self, message: str) -> None:
            self.messages.append(message)

    class FakeAssistant:
        def __init__(self):
            self._generation = 0
            self._prefetch_thread = None
            self._conversation: list[dict] = []
            self._conv_lock = threading.Lock()
            self.ui = FakeUi()
            self.spoken: list[str] = []

        def _auto_switch_language(self, _text: str) -> None:
            return None

        def speak(self, text: str) -> None:
            self.spoken.append(text)

    saved: list[tuple[str, str]] = []
    monkeypatch.setattr(
        jarvis_llm,
        "store_conversation",
        lambda prompt, answer: saved.append((prompt, answer)),
    )
    assistant = FakeAssistant()
    prompt = (
        "You are JARVIS MARK XL assisting a student preparing a morning study "
        "plan. State your role, name one real capability, and name one "
        "capability you must not claim without evidence."
    )

    jarvis_llm._process_message(assistant, prompt)

    assert assistant.spoken and assistant.spoken[0].startswith("I am JARVIS MARK XL")
    assert any(message.startswith("Jarvis: I am JARVIS MARK XL") for message in assistant.ui.messages)
    assert assistant._conversation[-1]["content"].startswith("I am JARVIS MARK XL")
    assert assistant.ui.states[-1] == "LISTENING"
