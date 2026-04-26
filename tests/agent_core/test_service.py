from __future__ import annotations

import asyncio
import os
from pathlib import Path

from agent_core import (
    AdapterRegistry,
    DomainPackRegistry,
    LaunchIntent,
    LaunchMention,
    MemoryPlane,
)
from agent_core.service import AgentOSService


class FakePack:
    def describe(self):
        return {
            "pack_id": "fake_pack",
            "domain": "fake",
            "version": "0.1.0",
            "owner_repo": "fake-repo",
            "runtime": "cloud",
            "description": "fake",
        }

    def health(self):
        return {"status": "ok", "checks": {"ready": True}}

    def capabilities(self):
        return []

    async def run(self, request):
        return {
            "run": {
                "run_id": "run-1",
                "domain": "fake",
                "capability": "demo",
                "status": "queued",
            },
            "artifacts": [],
            "review_actions": [],
        }

    async def list_runs(self):
        return [
            {
                "run_id": "run-1",
                "domain": "fake",
                "capability": "demo",
                "status": "queued",
                "summary": "demo",
                "created_at": "2026-04-18T12:00:00+00:00",
            }
        ]

    async def list_artifacts(self, run_id: str):
        return [
            {
                "artifact_id": f"{run_id}:artifact-1",
                "run_id": run_id,
                "kind": "report",
                "uri": f"/tmp/{run_id}.json",
                "title": "fake report",
                "metadata": {},
            }
        ]

    async def review_actions(self, run_id: str):
        return []

    async def list_manual_review_queue(self):
        return [
            {
                "review_id": "review-1",
                "run_id": "run-1",
                "site_slug": "site-a",
                "lane": "lane-a",
                "status": "needs_review",
            }
        ]

    async def list_workers(self):
        return [{"worker_id": "worker-1", "lane": "lane-a", "status": "idle"}]

    async def list_site_health(self):
        return [{"site_slug": "site-a", "lane": "lane-a", "recommended_action": "continue"}]

    async def list_repair_cases(self):
        return [{"case_id": "case-1", "site_slug": "site-a", "lane": "lane-a", "failure_fingerprint": "fp", "trigger_reason": "demo", "status": "open"}]

    async def retry_run(self, run_id: str, *, site_scope=None, note=None):
        return {"run_id": "retry-run-1", "note": note or "", "site_scope": site_scope or []}

    async def submit_manual_review_decision(self, review_id: str, *, decision: str, notes=None):
        return {"review_id": review_id, "decision": decision, "notes": notes or ""}

    def eval_suite(self):
        return []


class FakeDueDiligencePack(FakePack):
    def describe(self):
        return {
            "pack_id": "due_diligence",
            "domain": "due_diligence",
            "version": "0.1.0",
            "owner_repo": "due-diligence-core",
            "runtime": "cloud",
            "description": "fake due diligence pack",
            "capabilities": self.capabilities(),
        }

    def capabilities(self):
        return [
            {
                "capability_id": "company_due_diligence",
                "name": "Company Due Diligence",
                "description": "Run a due-diligence workflow.",
            }
        ]

    async def run(self, request):
        return {
            "run": {
                "run_id": "run-1",
                "domain": "due_diligence",
                "capability": "company_due_diligence",
                "status": "queued",
                "summary": "due diligence run",
            },
            "artifacts": [
                {
                    "artifact_id": "run-1:artifact-1",
                    "run_id": "run-1",
                    "kind": "report",
                    "uri": "/tmp/run-1.json",
                    "title": "due diligence report",
                    "metadata": {},
                }
            ],
            "review_actions": [],
        }


class FakeAdapter:
    def describe(self):
        return {
            "adapter_id": "fake_adapter",
            "channel": "demo",
            "owner_repo": "fake-repo",
            "description": "fake adapter",
        }

    async def ingest(self, event):
        return {"session_id": "session-1", "canonical_id": "user:1", "channel": "demo"}

    async def deliver(self, run, policy):
        return {"delivered": True}


def test_agent_os_service_aggregates_control_plane_views(tmp_path) -> None:
    service = AgentOSService(
        domain_packs=DomainPackRegistry(),
        adapters=AdapterRegistry(),
        state_root=tmp_path,
    )
    service.register_pack("fake_pack", FakePack())
    service.register_adapter("fake_adapter", FakeAdapter())

    overview = asyncio.run(service.get_overview())
    work_items = asyncio.run(service.list_work_items())
    adapter_health = asyncio.run(service.list_adapter_health())

    assert overview["packs"][0]["pack_id"] == "fake_pack"
    assert overview["adapters"][0]["adapter_id"] == "fake_adapter"
    assert overview["runs_summary"]["total"] == 1
    assert overview["work_items_summary"]["total"] >= 2
    assert work_items[0]["pack_id"] == "fake_pack"
    assert adapter_health[0]["adapter_id"] == "fake_adapter"


def test_agent_os_service_records_memory_into_targets(tmp_path) -> None:
    service = AgentOSService(state_root=tmp_path)

    raw_record = asyncio.run(
        service.record_memory(
            source="wechat",
            content="raw note",
            plane=MemoryPlane.RAW,
        )
    )
    reviewed_record = asyncio.run(
        service.record_memory(
            source="review",
            content="reviewed note",
            plane=MemoryPlane.REVIEWED,
        )
    )
    records = asyncio.run(service.list_memory_records(limit=10))

    assert raw_record.target == "mempalace://raw"
    assert reviewed_record.target == "obsidian://reviewed"
    assert [record.content for record in records] == ["reviewed note", "raw note"]


def test_agent_os_service_ingests_adapter_event_and_records_raw_memory(tmp_path) -> None:
    service = AgentOSService(
        domain_packs=DomainPackRegistry(),
        adapters=AdapterRegistry(),
        state_root=tmp_path,
    )
    service.register_adapter("fake_adapter", FakeAdapter())

    session = asyncio.run(
        service.ingest_event(
            "fake_adapter",
            {
                "event_id": "evt-1",
                "channel": "demo",
                "channel_user_id": "user-1",
                "text": "voice transcript",
            },
        )
    )
    records = asyncio.run(service.list_memory_records(limit=10))

    assert session["session_id"] == "session-1"
    assert records[0].content == "voice transcript"


def test_agent_os_service_lists_run_artifacts_by_domain(tmp_path) -> None:
    service = AgentOSService(
        domain_packs=DomainPackRegistry(),
        adapters=AdapterRegistry(),
        state_root=tmp_path,
    )
    service.register_pack("fake_pack", FakePack())

    artifacts = asyncio.run(service.list_artifacts("run-1", domain="fake"))

    assert artifacts[0]["artifact_id"] == "run-1:artifact-1"
    assert artifacts[0]["metadata"]["pack_id"] == "fake_pack"


def test_agent_os_service_executes_due_diligence_actions(tmp_path) -> None:
    service = AgentOSService(
        domain_packs=DomainPackRegistry(),
        adapters=AdapterRegistry(),
        state_root=tmp_path,
    )
    service.register_pack("due_diligence", FakePack())

    decision = asyncio.run(
        service.execute_action(
            "pack:due_diligence:review:decision:review-1:approved",
            {"decision": "approved", "notes": "ok"},
        )
    )
    retry_run = asyncio.run(
        service.execute_action(
            "pack:due_diligence:run:retry:run-1",
            {"site_scope": ["site-a"], "note": "retry"},
        )
    )

    assert decision["result"]["decision"] == "approved"
    assert retry_run["result"]["run_id"] == "retry-run-1"


def test_agent_os_service_compiles_launch_mentions_into_pack_task_and_presets(tmp_path) -> None:
    service = AgentOSService(
        domain_packs=DomainPackRegistry(),
        adapters=AdapterRegistry(),
        state_root=tmp_path,
    )
    service.register_pack("due_diligence", FakeDueDiligencePack())

    compiled = asyncio.run(
        service.compile_launch_intent(
            LaunchIntent(
                source="electron_cowork",
                raw_text="scan this company",
                work_mode="local",
                launch_surface="home",
                workspace_target="/tmp/workspace",
                mentions=[
                    LaunchMention(kind="pack", value="due_diligence.company_due_diligence"),
                    LaunchMention(kind="skill", value="corp-risk"),
                    LaunchMention(kind="plugin", value="qywx-files"),
                ],
                session_context={"session_id": "session:zhangqilong", "user_id": "zhangqilong"},
            )
        )
    )

    assert compiled["pack_id"] == "due_diligence"
    assert compiled["task"].capability == "due_diligence.company_due_diligence"
    assert compiled["task"].work_mode.value == "local"
    assert compiled["task"].origin_surface == "home"
    assert compiled["task"].interaction_surface.value == "electron_home"
    assert compiled["task"].runtime_profile.value == "dev_local_acp_bridge"
    assert compiled["task"].runtime_target.value == "local_runtime"
    assert compiled["task"].model_plane.value == "cloud_provider"
    assert compiled["task"].execution_plane.value == "local_executor"
    assert compiled["task"].local_runtime_seat.value == "acp_bridge"
    assert compiled["workspace_target"] == "/tmp/workspace"
    assert compiled["task"].metadata["skill_mentions"] == ["corp-risk"]
    assert compiled["task"].metadata["plugin_mentions"] == ["qywx-files"]
    assert compiled["task"].metadata["local_runtime_seat"] == "acp_bridge"
    assert compiled["request"].input["query"] == "scan this company"


def test_launch_intent_defaults_cloud_sandbox_to_cloud_managed_runtime() -> None:
    intent = LaunchIntent.model_validate(
        {
            "source": "electron_cowork",
            "raw_text": "run this in the cloud",
            "work_mode": "cloud_sandbox",
        }
    )

    assert intent.runtime_profile.value == "cloud_managed_runtime"
    assert intent.runtime_target.value == "cloud_runtime"
    assert intent.local_runtime_seat.value == "unavailable"


def test_agent_os_service_launch_creates_task_and_links_generated_run(tmp_path) -> None:
    service = AgentOSService(
        domain_packs=DomainPackRegistry(),
        adapters=AdapterRegistry(),
        state_root=tmp_path,
    )
    service.register_pack("due_diligence", FakeDueDiligencePack())

    receipt = asyncio.run(
        service.launch(
            {
                "source": "weclaw",
                "raw_text": "run due diligence",
                "mentions": [{"kind": "pack", "value": "due_diligence.company_due_diligence"}],
                "session_context": {
                    "session_id": "session:wechat-zhangqilong",
                    "canonical_id": "user:zhangqilong",
                    "channel": "wechat",
                    "user_id": "zhangqilong",
                },
            }
        )
    )
    tasks = asyncio.run(service.list_tasks())
    fetched_task = asyncio.run(service.get_task(receipt["task"]["task_id"]))

    assert receipt["pack_id"] == "due_diligence"
    assert receipt["task"]["work_mode"] == "weclaw_dispatch"
    assert receipt["task"]["origin_surface"] == "weclaw"
    assert receipt["task"]["interaction_surface"] == "weclaw"
    assert receipt["task"]["runtime_profile"] == "dev_local_acp_bridge"
    assert receipt["task"]["runtime_target"] == "local_runtime"
    assert receipt["task"]["model_plane"] == "cloud_provider"
    assert receipt["task"]["execution_plane"] == "local_executor"
    assert receipt["task"]["local_runtime_seat"] == "acp_bridge"
    assert receipt["run"]["run_id"] == "run-1"
    assert receipt["run"]["work_mode"] == "weclaw_dispatch"
    assert receipt["run"]["origin_surface"] == "weclaw"
    assert receipt["run"]["interaction_surface"] == "weclaw"
    assert receipt["run"]["runtime_profile"] == "dev_local_acp_bridge"
    assert receipt["run"]["runtime_target"] == "local_runtime"
    assert receipt["run"]["model_plane"] == "cloud_provider"
    assert receipt["run"]["execution_plane"] == "local_executor"
    assert receipt["run"]["local_runtime_seat"] == "acp_bridge"
    assert receipt["task"]["run_ids"] == ["run-1"]
    assert receipt["task"]["last_run_id"] == "run-1"
    assert receipt["work_items"][0]["run_id"] == "run-1"
    assert receipt["work_items"][0]["work_mode"] == "weclaw_dispatch"
    assert receipt["work_items"][0]["runtime_target"] == "local_runtime"
    assert receipt["work_items"][0]["interaction_surface"] == "weclaw"
    assert receipt["work_items"][0]["local_runtime_seat"] == "acp_bridge"
    assert tasks[0]["task_id"] == receipt["task"]["task_id"]
    assert fetched_task["run_ids"] == ["run-1"]


def test_agent_os_service_launches_local_runtime_without_pack_into_internal_ledger(tmp_path) -> None:
    service = AgentOSService(
        domain_packs=DomainPackRegistry(),
        adapters=AdapterRegistry(),
        state_root=tmp_path,
    )

    receipt = asyncio.run(
        service.launch(
            {
                "source": "electron_cowork",
                "raw_text": "@skill browse inspect the workspace",
                "mentions": [{"kind": "skill", "value": "browse"}],
                "work_mode": "local",
                "launch_surface": "home",
                "workspace_target": "/tmp/local-workspace",
                "local_runtime_seat": "local_runtime_api",
                "runtime_profile": "packaged_local_runtime",
                "session_context": {
                    "session_id": "session:desktop-zhangqilong",
                    "channel": "desktop",
                    "user_id": "zhangqilong",
                },
            }
        )
    )
    runs = asyncio.run(service.list_runs())

    assert receipt["pack_id"] == "local_runtime"
    assert receipt["task"]["capability"] == "local_runtime.browse"
    assert receipt["task"]["runtime_profile"] == "packaged_local_runtime"
    assert receipt["task"]["runtime_target"] == "local_runtime"
    assert receipt["task"]["local_runtime_seat"] == "local_runtime_api"
    assert receipt["task"]["metadata"]["workspace_target"] == "/tmp/local-workspace"
    assert receipt["run"]["domain"] == "local_runtime"
    assert receipt["run"]["local_runtime_seat"] == "local_runtime_api"
    assert any(run["domain"] == "local_runtime" for run in runs)


def test_agent_os_service_launches_cloud_runtime_without_pack_into_internal_ledger(tmp_path) -> None:
    service = AgentOSService(
        domain_packs=DomainPackRegistry(),
        adapters=AdapterRegistry(),
        state_root=tmp_path,
        cloud_runtime_base_url="http://cloud-runtime.local",
    )

    async def fake_post_cloud_runtime_launch(payload):
        assert payload["egress_profile"] == "vps_direct"
        assert payload["client_scope_id"].startswith("client-")
        return {
            "accepted": True,
            "status": "running",
            "remote_session_id": "remote-123",
            "workspace_root": "/srv/cloud/client-a",
            "summary": "Cloud runtime accepted",
        }

    service._post_cloud_runtime_launch = fake_post_cloud_runtime_launch  # type: ignore[method-assign]

    receipt = asyncio.run(
        service.launch(
            {
                "source": "electron_cowork",
                "raw_text": "在云端执行这项任务",
                "work_mode": "cloud_sandbox",
                "launch_surface": "home",
                "workspace_target": "sandbox://client-a",
                "session_context": {
                    "session_id": "session:desktop-zhangqilong",
                    "channel": "desktop",
                    "user_id": "zhangqilong",
                },
            }
        )
    )
    runs = asyncio.run(service.list_runs())

    assert receipt["pack_id"] == "cloud_runtime"
    assert receipt["task"]["capability"] == "cloud_runtime.cloud_sandbox"
    assert receipt["task"]["runtime_profile"] == "cloud_managed_runtime"
    assert receipt["task"]["runtime_target"] == "cloud_runtime"
    assert receipt["task"]["execution_plane"] == "cloud_executor"
    assert receipt["task"]["local_runtime_seat"] == "unavailable"
    assert receipt["run"]["domain"] == "cloud_runtime"
    assert receipt["run"]["runtime_profile"] == "cloud_managed_runtime"
    assert receipt["run"]["runtime_target"] == "cloud_runtime"
    assert receipt["run"]["local_runtime_seat"] == "unavailable"
    assert receipt["run"]["metadata"]["remote_session_id"] == "remote-123"
    assert receipt["run"]["metadata"]["egress_profile"] == "vps_direct"
    assert any(run["domain"] == "cloud_runtime" for run in runs)


def test_agent_os_service_from_env_registers_weclaw_adapter_from_api_addr(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("WECLAW_API_URL", raising=False)
    monkeypatch.setenv("WECLAW_API_ADDR", "127.0.0.1:18011")
    monkeypatch.delenv("LONGCLAW_RUNTIME_PROFILE", raising=False)

    service = AgentOSService.from_env()

    assert service.adapters.has("weclaw") is True
    descriptor = service.adapters.list_descriptors("wechat")[0]
    assert descriptor.adapter_id == "weclaw"


def test_agent_os_service_from_env_registers_weclaw_adapter_from_config(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("WECLAW_API_URL", raising=False)
    monkeypatch.delenv("WECLAW_API_ADDR", raising=False)
    monkeypatch.delenv("LONGCLAW_RUNTIME_PROFILE", raising=False)
    config_dir = Path(tmp_path) / ".weclaw"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text('{"api_addr":"127.0.0.1:18011"}', encoding="utf-8")

    service = AgentOSService.from_env()

    assert service.adapters.has("weclaw") is True


def test_agent_os_service_routes_launch_without_pack_via_routing_hint(tmp_path) -> None:
    service = AgentOSService(
        domain_packs=DomainPackRegistry(),
        adapters=AdapterRegistry(),
        state_root=tmp_path,
    )
    service.register_pack("due_diligence", FakeDueDiligencePack())

    compiled = asyncio.run(
        service.compile_launch_intent(
            {
                "source": "electron_cowork",
                "raw_text": "scan this company",
                "metadata": {
                    "routing_hint": {
                        "default_pack_id": "due_diligence",
                    }
                },
                "session_context": {
                    "channel": "desktop",
                    "user_id": "zhangqilong",
                },
            }
        )
    )

    assert compiled["pack_id"] == "due_diligence"
    assert compiled["task"].capability == "due_diligence.company_due_diligence"


def test_agent_os_service_routes_launch_without_pack_via_env_default(tmp_path) -> None:
    service = AgentOSService(
        domain_packs=DomainPackRegistry(),
        adapters=AdapterRegistry(),
        state_root=tmp_path,
    )
    service.register_pack("due_diligence", FakeDueDiligencePack())

    previous_pack = os.environ.get("LONGCLAW_DEFAULT_LAUNCH_PACK")
    try:
        os.environ["LONGCLAW_DEFAULT_LAUNCH_PACK"] = "due_diligence"
        receipt = asyncio.run(
            service.launch(
                {
                    "source": "electron_cowork",
                    "raw_text": "run company diligence",
                    "session_context": {
                        "channel": "desktop",
                        "user_id": "zhangqilong",
                    },
                }
            )
        )
    finally:
        if previous_pack is None:
            os.environ.pop("LONGCLAW_DEFAULT_LAUNCH_PACK", None)
        else:
            os.environ["LONGCLAW_DEFAULT_LAUNCH_PACK"] = previous_pack

    assert receipt["pack_id"] == "due_diligence"
    assert receipt["task"]["capability"] == "due_diligence.company_due_diligence"


def test_agent_os_service_overview_summarizes_three_modes(tmp_path) -> None:
    service = AgentOSService(
        domain_packs=DomainPackRegistry(),
        adapters=AdapterRegistry(),
        state_root=tmp_path,
    )
    service.register_pack("due_diligence", FakeDueDiligencePack())

    asyncio.run(
        service.launch(
            {
                "source": "electron_cowork",
                "raw_text": "@pack due_diligence.company_due_diligence run local diligence",
                "work_mode": "local",
                "launch_surface": "home",
                "workspace_target": "/tmp/local-workspace",
                "mentions": [{"kind": "pack", "value": "due_diligence.company_due_diligence"}],
                "session_context": {
                    "session_id": "session:desktop-zhangqilong",
                    "canonical_id": "user:zhangqilong",
                    "channel": "desktop",
                    "user_id": "zhangqilong",
                },
            }
        )
    )

    overview = asyncio.run(service.get_overview())

    assert overview["mode_summary"]["tasks"]["local"] == 1
    assert overview["mode_summary"]["runs"]["local"] == 1
    assert overview["mode_summary"]["work_items"]["local"] >= 1
