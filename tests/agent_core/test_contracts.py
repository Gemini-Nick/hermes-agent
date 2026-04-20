from __future__ import annotations

import pytest

from agent_core import (
    AdapterRegistry,
    DeliveryPolicy,
    DomainCapability,
    DomainPackRegistry,
    DomainRunRequest,
    ExecutionPlane,
    InboundEvent,
    InteractionSurface,
    LaunchIntent,
    LaunchMention,
    ModelPlane,
    RuntimeProfile,
    RuntimeTarget,
    WorkMode,
)


class DummyPack:
    def describe(self):
        return {
            "pack_id": "signals",
            "domain": "financial_analysis",
            "version": "0.1.0",
            "owner_repo": "Signals",
            "runtime": "cloud",
            "description": "Signals domain pack",
        }

    def health(self):
        return {"status": "ok", "checks": {"imports": True}}

    def capabilities(self):
        return [
            DomainCapability(
                capability_id="intraday",
                name="Intraday Monitor",
                description="Run the intraday signals workflow.",
            )
        ]

    async def run(self, request):
        return {
            "run": {
                "run_id": "run-1",
                "domain": "financial_analysis",
                "capability": "intraday",
            }
        }

    async def list_artifacts(self, run_id: str):
        return []

    async def review_actions(self, run_id: str):
        return []

    def eval_suite(self):
        return []


class DummyAdapter:
    def describe(self):
        return {
            "adapter_id": "weclaw",
            "channel": "wechat",
            "owner_repo": "weclaw",
            "description": "WeChat adapter",
        }

    async def ingest(self, event):
        return {
            "session_id": "session-1",
            "canonical_id": "wechat:user-1",
            "channel": "wechat",
        }

    async def deliver(self, run, policy):
        return {"delivered": True}


def test_domain_pack_registry_normalizes_descriptor() -> None:
    registry = DomainPackRegistry()
    registry.register("signals", DummyPack())

    assert registry.has("signals") is True
    assert registry.get("signals").describe()["owner_repo"] == "Signals"
    assert registry.list_descriptors()[0].pack_id == "signals"


def test_domain_pack_registry_rejects_duplicate_ids() -> None:
    registry = DomainPackRegistry()
    registry.register("signals", DummyPack())

    with pytest.raises(ValueError, match="already registered"):
        registry.register("signals", DummyPack())


def test_adapter_registry_indexes_channel() -> None:
    registry = AdapterRegistry()
    registry.register("weclaw", DummyAdapter())

    assert registry.has("weclaw") is True
    assert len(registry.by_channel("wechat")) == 1
    assert registry.list_descriptors("wechat")[0].adapter_id == "weclaw"


def test_delivery_policy_and_requests_use_agent_os_defaults() -> None:
    policy = DeliveryPolicy(preferred_channels=["wechat"], fallback_channels=["desktop"])
    request = DomainRunRequest(capability="intraday", delivery_policy=policy)
    inbound = InboundEvent(
        event_id="evt-1",
        channel="wechat",
        channel_user_id="user-1",
        delivery_policy=policy,
    )

    assert request.delivery_policy.preferred_channels == ["wechat"]
    assert inbound.delivery_policy.desktop_fallback is True


def test_launch_intent_preserves_mentions_and_delivery_preferences() -> None:
    intent = LaunchIntent(
        source="electron_cowork",
        raw_text="run review",
        mentions=[
            LaunchMention(kind="pack", value="signals.review"),
            LaunchMention(kind="skill", value="market-radar"),
        ],
        delivery_preference=DeliveryPolicy(preferred_channels=["wechat"]),
        session_context={"session_id": "session:zhangqilong", "user_id": "zhangqilong"},
    )

    assert intent.mentions[0].value == "signals.review"
    assert intent.delivery_preference.preferred_channels == ["wechat"]
    assert intent.session_context["session_id"] == "session:zhangqilong"


def test_three_mode_contract_fields_round_trip_from_metadata() -> None:
    intent = LaunchIntent(
        source="weclaw",
        raw_text="@pack signals.review run review",
        metadata={
            "work_mode": "weclaw_dispatch",
            "launch_surface": "weclaw",
            "workspace_target": "ctx-1",
            "runtime_profile": "dev_local_acp_bridge",
        },
        session_context={"session_id": "session:user-1", "user_id": "user-1"},
    )
    request = DomainRunRequest(
        capability="review",
        task={
            "task_id": "task-1",
            "capability": "signals.review",
            "metadata": {
                "work_mode": "weclaw_dispatch",
                "origin_surface": "weclaw",
                "execution_plane": "weclaw_dispatch",
                "runtime_profile": "dev_local_acp_bridge",
            },
        },
    )

    assert intent.work_mode == WorkMode.WECLAW_DISPATCH
    assert intent.launch_surface == "weclaw"
    assert intent.interaction_surface == InteractionSurface.WECLAW
    assert intent.runtime_profile == RuntimeProfile.DEV_LOCAL_ACP_BRIDGE
    assert intent.runtime_target == RuntimeTarget.LOCAL_RUNTIME
    assert intent.model_plane == ModelPlane.CLOUD_PROVIDER
    assert intent.local_runtime_seat.value == "acp_bridge"
    assert intent.workspace_target == "ctx-1"
    assert request.task.work_mode == WorkMode.WECLAW_DISPATCH
    assert request.task.origin_surface == "weclaw"
    assert request.task.interaction_surface == InteractionSurface.WECLAW
    assert request.task.runtime_profile == RuntimeProfile.DEV_LOCAL_ACP_BRIDGE
    assert request.task.runtime_target == RuntimeTarget.LOCAL_RUNTIME
    assert request.task.model_plane == ModelPlane.CLOUD_PROVIDER
    assert request.task.execution_plane == ExecutionPlane.LOCAL_EXECUTOR
    assert request.task.local_runtime_seat.value == "acp_bridge"
