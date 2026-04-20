from __future__ import annotations

import asyncio

from agent_core.integrations import ChanlessAdapter, WeclawAdapter


async def _fake_sender(path, payload):
    return {"path": path, "payload": dict(payload), "status": "ok"}


def test_weclaw_adapter_routes_delivery_to_send_endpoint() -> None:
    adapter = WeclawAdapter(
        base_url="http://127.0.0.1:18011",
        default_to="filehelper",
        sender=_fake_sender,
    )

    result = asyncio.run(
        adapter.deliver(
            {
                "run_id": "run-1",
                "domain": "fake",
                "capability": "demo",
                "status": "succeeded",
                "summary": "hello",
                "metadata": {},
            },
            {"preferred_channels": ["wechat"]},
        )
    )

    assert result["delivered"] is True
    assert result["response"]["path"] == "/api/send"
    assert result["response"]["payload"]["to"] == "filehelper"


def test_chanless_adapter_uses_notifier_for_desktop_fallback() -> None:
    notifications = []

    def notifier(title: str, message: str) -> None:
        notifications.append((title, message))

    adapter = ChanlessAdapter(notifier=notifier)

    result = asyncio.run(
        adapter.deliver(
            {
                "run_id": "run-1",
                "domain": "fake",
                "capability": "demo",
                "status": "succeeded",
                "summary": "desktop message",
                "metadata": {},
            },
            {"desktop_fallback": True},
        )
    )

    assert result["delivered"] is True
    assert notifications == [("Longclaw Agent OS", "desktop message")]


def test_adapters_share_canonical_session_when_metadata_requests_it() -> None:
    weclaw = WeclawAdapter(
        base_url="http://127.0.0.1:18011",
        sender=_fake_sender,
    )
    chanless = ChanlessAdapter()

    wechat_session = asyncio.run(
        weclaw.ingest(
            {
                "event_id": "evt-wechat",
                "channel": "wechat",
                "channel_user_id": "wechat-user",
                "text": "hello",
                "metadata": {
                    "canonical_user_id": "zhangqilong",
                },
            }
        )
    )
    voice_session = asyncio.run(
        chanless.ingest(
            {
                "event_id": "evt-voice",
                "channel": "voice",
                "channel_user_id": "local-voice",
                "text": "hello",
                "metadata": {
                    "canonical_user_id": "zhangqilong",
                },
            }
        )
    )

    assert wechat_session["session_id"] == "session:zhangqilong"
    assert voice_session["session_id"] == "session:zhangqilong"
