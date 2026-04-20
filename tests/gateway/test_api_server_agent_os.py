from __future__ import annotations

import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter, cors_middleware, security_headers_middleware


class FakeAgentOSService:
    async def launch(self, payload):
        return {
            "launch_id": "launch-1",
            "pack_id": "signals",
            "task": {
                "task_id": "task-1",
                "capability": "signals.review",
                "work_mode": "local",
                "origin_surface": "home",
                "interaction_surface": "electron_home",
                "runtime_profile": "dev_local_acp_bridge",
                "runtime_target": "local_runtime",
                "model_plane": "cloud_provider",
                "execution_plane": "local_executor",
                "run_ids": ["run-1"],
                "last_run_id": "run-1",
            },
            "run": {
                "run_id": "run-1",
                "capability": "review",
                "domain": "financial_analysis",
                "work_mode": "local",
                "origin_surface": "home",
                "interaction_surface": "electron_home",
                "runtime_profile": "dev_local_acp_bridge",
                "runtime_target": "local_runtime",
                "model_plane": "cloud_provider",
                "execution_plane": "local_executor",
            },
            "work_items": [],
            "compiled_input": {"mode": "review"},
        }

    async def list_tasks(self, *, limit=50):
        return [
            {
                "task_id": "task-1",
                "capability": "signals.review",
                "work_mode": "local",
                "origin_surface": "home",
                "interaction_surface": "electron_home",
                "runtime_profile": "dev_local_acp_bridge",
                "runtime_target": "local_runtime",
                "model_plane": "cloud_provider",
                "execution_plane": "local_executor",
                "run_ids": ["run-1"],
                "last_run_id": "run-1",
            }
        ][:limit]

    async def get_task(self, task_id: str):
        if task_id != "task-1":
            raise KeyError(task_id)
        return {
            "task_id": "task-1",
            "capability": "signals.review",
            "work_mode": "local",
            "origin_surface": "home",
            "interaction_surface": "electron_home",
            "runtime_profile": "dev_local_acp_bridge",
            "runtime_target": "local_runtime",
            "model_plane": "cloud_provider",
            "execution_plane": "local_executor",
            "run_ids": ["run-1"],
            "last_run_id": "run-1",
        }

    async def get_overview(self):
        return {
            "packs": [],
            "adapters": [],
            "packHealth": [],
            "adapterHealth": [],
            "mode_summary": {
                "tasks": {"local": 1, "cloud_sandbox": 0, "weclaw_dispatch": 0},
                "runs": {"local": 1, "cloud_sandbox": 0, "weclaw_dispatch": 0},
                "work_items": {"local": 0, "cloud_sandbox": 0, "weclaw_dispatch": 0},
            },
            "runs_summary": {"total": 0},
            "work_items_summary": {"total": 0},
            "recent_failures": [],
            "memoryTargets": {"raw": "mempalace://raw", "reviewed": "obsidian://reviewed"},
        }

    async def list_work_items(self):
        return [{"work_item_id": "work-1", "pack_id": "due_diligence", "kind": "manual_review"}]

    async def list_adapter_health(self):
        return [{"adapter_id": "weclaw", "channel": "wechat", "status": "ok"}]

    async def get_pack_dashboard(self, pack_id: str):
        if pack_id == "signals":
            return {"pack_id": "signals", "title": "Signals", "recent_runs": []}
        raise KeyError(pack_id)

    async def execute_action(self, action_id: str, payload):
        if action_id != "pack:signals:run:review":
            raise KeyError(action_id)
        return {"action_id": action_id, "status": "ok", "result": payload}


def _make_adapter() -> APIServerAdapter:
    return APIServerAdapter(PlatformConfig(enabled=True))


def _create_app(adapter: APIServerAdapter) -> web.Application:
    app = web.Application(
        middlewares=[mw for mw in (cors_middleware, security_headers_middleware) if mw is not None]
    )
    app["api_server_adapter"] = adapter
    app.router.add_get("/agent-os/overview", adapter._handle_agent_os_overview)
    app.router.add_post("/agent-os/launches", adapter._handle_agent_os_launch)
    app.router.add_get("/agent-os/tasks", adapter._handle_agent_os_tasks)
    app.router.add_get("/agent-os/tasks/{task_id}", adapter._handle_agent_os_task)
    app.router.add_get("/agent-os/work-items", adapter._handle_agent_os_work_items)
    app.router.add_get("/agent-os/adapters/health", adapter._handle_agent_os_adapter_health)
    app.router.add_get("/agent-os/packs/{pack_id}/dashboard", adapter._handle_agent_os_pack_dashboard)
    app.router.add_post("/agent-os/actions/{action_id}", adapter._handle_agent_os_action)
    return app


@pytest.mark.asyncio
async def test_agent_os_control_plane_endpoints(monkeypatch):
    adapter = _make_adapter()
    monkeypatch.setattr(adapter, "_ensure_agent_os_service", lambda: FakeAgentOSService())
    app = _create_app(adapter)

    async with TestClient(TestServer(app)) as cli:
        overview = await cli.get("/agent-os/overview")
        assert overview.status == 200
        assert (await overview.json())["mode_summary"]["tasks"]["local"] == 1

        launch = await cli.post(
            "/agent-os/launches",
            json={
                "source": "electron_cowork",
                "raw_text": "run review",
                "work_mode": "local",
                "launch_surface": "home",
                "workspace_target": "/tmp/workspace",
                "mentions": [{"kind": "pack", "value": "signals.review"}],
            },
        )
        assert launch.status == 202
        launch_payload = await launch.json()
        assert launch_payload["task"]["task_id"] == "task-1"
        assert launch_payload["task"]["work_mode"] == "local"

        tasks = await cli.get("/agent-os/tasks")
        assert tasks.status == 200
        assert (await tasks.json())[0]["task_id"] == "task-1"

        task = await cli.get("/agent-os/tasks/task-1")
        assert task.status == 200
        assert (await task.json())["run_ids"] == ["run-1"]

        work_items = await cli.get("/agent-os/work-items")
        assert work_items.status == 200
        assert (await work_items.json())[0]["work_item_id"] == "work-1"

        adapter_health = await cli.get("/agent-os/adapters/health")
        assert adapter_health.status == 200
        assert (await adapter_health.json())[0]["adapter_id"] == "weclaw"

        dashboard = await cli.get("/agent-os/packs/signals/dashboard")
        assert dashboard.status == 200
        assert (await dashboard.json())["pack_id"] == "signals"

        action = await cli.post(
            "/agent-os/actions/pack:signals:run:review",
            json={"input": {"mode": "review"}},
        )
        assert action.status == 200
        assert (await action.json())["action_id"] == "pack:signals:run:review"


@pytest.mark.asyncio
async def test_agent_os_control_plane_returns_404_for_unknown_records(monkeypatch):
    adapter = _make_adapter()
    monkeypatch.setattr(adapter, "_ensure_agent_os_service", lambda: FakeAgentOSService())
    app = _create_app(adapter)

    async with TestClient(TestServer(app)) as cli:
        task = await cli.get("/agent-os/tasks/unknown-task")
        assert task.status == 404

        dashboard = await cli.get("/agent-os/packs/unknown/dashboard")
        assert dashboard.status == 404

        action = await cli.post("/agent-os/actions/pack:signals:run:unknown", json={})
        assert action.status == 404
