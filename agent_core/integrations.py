from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

import httpx

from .contracts import (
    DeliveryPolicy,
    InboundEvent,
    Run,
    Session,
    SessionStatus,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_user_id(event: InboundEvent) -> str:
    value = event.metadata.get("canonical_user_id")
    if value:
        return str(value)
    return event.channel_user_id


def _canonical_session_id(event: InboundEvent) -> str:
    explicit = event.metadata.get("canonical_session_id")
    if explicit:
        return str(explicit)

    session_key = event.session_hint or _canonical_user_id(event)
    if session_key.startswith("session:"):
        return session_key
    return f"session:{session_key}"


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(item) for item in value]
    return value


def _read_dotenv(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class WeclawAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        default_to: Optional[str] = None,
        timeout: float = 10.0,
        sender: Optional[Callable[[str, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_to = default_to
        self.timeout = timeout
        self._sender = sender

    def describe(self) -> Dict[str, Any]:
        return {
            "adapter_id": "weclaw",
            "channel": "wechat",
            "owner_repo": "weclaw",
            "description": "WeChat bridge adapter using weclaw HTTP APIs for delivery and task dispatch.",
            "metadata": {
                "base_url": self.base_url,
                "default_to": self.default_to,
                "windowed_proactive": True,
            },
        }

    async def ingest(self, event: InboundEvent | Mapping[str, Any]) -> Dict[str, Any]:
        inbound = InboundEvent.model_validate(event)
        canonical_user = _canonical_user_id(inbound)
        session_id = _canonical_session_id(inbound)
        return Session(
            session_id=session_id,
            canonical_id=f"user:{canonical_user}",
            channel="wechat",
            user_id=canonical_user,
            status=SessionStatus.ACTIVE,
            metadata={
                "channel_user_id": inbound.channel_user_id,
                "session_hint": inbound.session_hint,
                "canonical_session_id": session_id,
                "attachments": inbound.attachments,
                "adapter": "weclaw",
            },
        ).model_dump(mode="json")

    async def deliver(
        self,
        run: Run | Mapping[str, Any],
        policy: DeliveryPolicy | Mapping[str, Any],
    ) -> Mapping[str, Any]:
        run_obj = Run.model_validate(run)
        policy_obj = DeliveryPolicy.model_validate(policy)
        target = (
            run_obj.metadata.get("reply_to")
            or run_obj.metadata.get("channel_user_id")
            or policy_obj.live_reply_channel
            or self.default_to
        )
        if not target:
            return {"delivered": False, "reason": "missing_target"}

        dispatch_mode = str(run_obj.metadata.get("dispatch_mode", "send"))
        if dispatch_mode == "task":
            path = "/api/task-dispatch"
            payload = {
                "to": target,
                "text": str(run_obj.metadata.get("reply_text") or run_obj.summary),
                "task_id": run_obj.task_id or run_obj.run_id,
            }
        else:
            path = "/api/send"
            payload = {
                "to": target,
                "text": str(run_obj.metadata.get("reply_text") or run_obj.summary),
            }
            media_url = run_obj.metadata.get("media_url")
            if media_url:
                payload["media_url"] = str(media_url)

        result = await self._post(path, payload)
        return {
            "delivered": True,
            "adapter": "weclaw",
            "target": target,
            "endpoint": f"{self.base_url}{path}",
            "response": dict(result),
        }

    async def _post(self, path: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if self._sender is not None:
            return await self._sender(path, payload)

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                json=dict(payload),
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}


class ChanlessAdapter:
    def __init__(
        self,
        *,
        notifier: Optional[Callable[[str, str], Any]] = None,
    ) -> None:
        self._notifier = notifier or self._osascript_notify

    def describe(self) -> Dict[str, Any]:
        return {
            "adapter_id": "chanless",
            "channel": "voice",
            "owner_repo": "Chanless",
            "description": "Voice ingress and desktop notification fallback adapter for the Chanless runtime.",
            "metadata": {
                "desktop_fallback": True,
                "ingress_mode": "local_voice",
            },
        }

    async def ingest(self, event: InboundEvent | Mapping[str, Any]) -> Dict[str, Any]:
        inbound = InboundEvent.model_validate(event)
        canonical_user = _canonical_user_id(inbound)
        session_id = _canonical_session_id(inbound)
        return Session(
            session_id=session_id,
            canonical_id=f"user:{canonical_user}",
            channel="voice",
            user_id=canonical_user,
            status=SessionStatus.ACTIVE,
            metadata={
                "channel_user_id": inbound.channel_user_id,
                "session_hint": inbound.session_hint,
                "canonical_session_id": session_id,
                "attachments": inbound.attachments,
                "transcript": inbound.text,
                "adapter": "chanless",
            },
        ).model_dump(mode="json")

    async def deliver(
        self,
        run: Run | Mapping[str, Any],
        policy: DeliveryPolicy | Mapping[str, Any],
    ) -> Mapping[str, Any]:
        run_obj = Run.model_validate(run)
        policy_obj = DeliveryPolicy.model_validate(policy)
        if not policy_obj.desktop_fallback:
            return {"delivered": False, "reason": "desktop_fallback_disabled"}

        title = str(run_obj.metadata.get("title") or "Longclaw Agent OS")
        message = str(run_obj.metadata.get("reply_text") or run_obj.summary)
        result = self._notifier(title, message)
        if hasattr(result, "__await__"):
            await result
        return {
            "delivered": True,
            "adapter": "chanless",
            "title": title,
        }

    @staticmethod
    def _osascript_notify(title: str, message: str) -> None:
        safe_title = title.replace('"', '\\"')
        safe_message = message.replace('"', '\\"')
        script = f'display notification "{safe_message}" with title "{safe_title}"'
        subprocess.run(["osascript", "-e", script], check=False)


class RemoteDueDiligencePack:
    def __init__(self, *, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def describe(self) -> Dict[str, Any]:
        return {
            "pack_id": "due_diligence",
            "domain": "due_diligence",
            "version": "0.1.0",
            "owner_repo": "due-diligence-core",
            "runtime": "cloud",
            "description": "Remote due-diligence flagship pack proxied over the due-diligence-core HTTP API.",
            "metadata": {"base_url": self.base_url, "transport": "http"},
            "capabilities": self.capabilities(),
        }

    def capabilities(self) -> List[Dict[str, Any]]:
        return [
            {
                "capability_id": "company_due_diligence",
                "name": "Company Due Diligence",
                "description": "Run a multi-site due-diligence workflow.",
                "input_schema": {
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "credit_code": {"type": "string"},
                        "task_type": {"type": "string", "default": "company"},
                        "site_scope": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        ]

    async def health(self) -> Dict[str, Any]:
        payload = await self._get("/healthz")
        status = "ok" if payload.get("api_ready") else "degraded"
        return {"status": status, "checks": payload}

    async def list_runs(self) -> List[Dict[str, Any]]:
        runs = await self._get("/runs")
        return [self._normalize_run(run) for run in runs]

    async def run(self, request: Mapping[str, Any]) -> Dict[str, Any]:
        payload = dict(request)
        input_payload = dict(payload.get("input", payload))
        response = await self._post(
            "/runs",
            {
                "query": input_payload["query"],
                "credit_code": input_payload.get("credit_code"),
                "task_type": input_payload.get("task_type", "company"),
                "site_scope": input_payload.get("site_scope", []),
                "requested_by": input_payload.get("requested_by") or payload.get("requested_by"),
                "delivery_profile": input_payload.get("delivery_profile", "legacy_yingdao"),
            },
        )
        normalized = self._normalize_run(response)
        return {
            "run": normalized,
            "artifacts": await self.list_artifacts(normalized["run_id"]),
            "review_actions": await self.review_actions(normalized["run_id"]),
        }

    async def list_artifacts(self, run_id: str) -> List[Dict[str, Any]]:
        manifest = await self._get(f"/runs/{run_id}/artifacts")
        artifacts: List[Dict[str, Any]] = []
        if manifest.get("delivery_zip_path"):
            artifacts.append(
                {
                    "artifact_id": f"{run_id}:delivery_zip",
                    "run_id": run_id,
                    "kind": "delivery_zip",
                    "uri": manifest["delivery_zip_path"],
                    "title": "delivery zip",
                    "metadata": {
                        "legacy_summary_message": manifest.get("legacy_summary_message", ""),
                        "lost_sites": manifest.get("lost_sites", []),
                    },
                }
            )
        if manifest.get("diagnostic_manifest_path"):
            artifacts.append(
                {
                    "artifact_id": f"{run_id}:diagnostic_manifest",
                    "run_id": run_id,
                    "kind": "diagnostic_manifest",
                    "uri": manifest["diagnostic_manifest_path"],
                    "title": "diagnostic manifest",
                    "metadata": {},
                }
            )
        return artifacts

    async def review_actions(self, run_id: str) -> List[Dict[str, Any]]:
        queue = await self.list_manual_review_queue()
        return [
            {
                "action_id": item["review_id"],
                "run_id": run_id,
                "kind": "manual_review",
                "label": f"Review {item['site_slug']}",
                "payload": item,
            }
            for item in queue
            if item.get("run_id") == run_id
        ]

    async def list_manual_review_queue(self) -> List[Dict[str, Any]]:
        queue = await self._get("/manual-review-queue")
        return [dict(item, domain="due_diligence", pack_id="due_diligence") for item in queue]

    async def list_workers(self) -> List[Dict[str, Any]]:
        return await self._get("/workers")

    async def list_site_health(self) -> List[Dict[str, Any]]:
        return await self._get("/site-health")

    async def list_repair_cases(self) -> List[Dict[str, Any]]:
        return await self._get("/repair-cases")

    async def submit_manual_review_decision(
        self,
        review_id: str,
        *,
        decision: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._post(
            f"/manual-review/{review_id}/decision",
            {
                "decision": decision,
                "notes": notes or "",
            },
        )

    async def retry_run(
        self,
        run_id: str,
        *,
        site_scope: Optional[List[str]] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._post(
            f"/runs/{run_id}/retry",
            {
                "site_scope": site_scope or [],
                "note": note or "",
            },
        )

    def eval_suite(self) -> List[Dict[str, Any]]:
        return [
            {
                "suite_id": "due_diligence_http_api",
                "name": "Due Diligence HTTP API",
                "description": "Remote control-plane compatibility checks for due-diligence-core.",
                "command": "pytest tests/test_orchestration_api.py tests/test_domain_pack.py",
            }
        ]

    def _normalize_run(self, run: Mapping[str, Any]) -> Dict[str, Any]:
        task_type = str(run.get("task_type") or "company")
        return {
            "run_id": str(run["run_id"]),
            "domain": "due_diligence",
            "capability": f"{task_type}_due_diligence",
            "status": str(run.get("status") or "queued"),
            "session_id": None,
            "task_id": None,
            "requested_by": run.get("requested_by"),
            "summary": str(run.get("legacy_summary_message") or run.get("query") or ""),
            "created_at": run.get("created_at"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "metadata": {
                "query": run.get("query"),
                "credit_code": run.get("credit_code"),
                "task_type": task_type,
                "delivery_profile": run.get("delivery_profile"),
                "site_scope": run.get("site_scope", []),
                "total_sites": run.get("total_sites", 0),
                "completed_sites": run.get("completed_sites", 0),
                "succeeded_sites": run.get("succeeded_sites", 0),
                "failed_sites": run.get("failed_sites", 0),
                "review_sites": run.get("review_sites", 0),
                "partial_sites": run.get("partial_sites", 0),
                "build_sha": run.get("build_sha", ""),
                "output_root": run.get("output_root"),
            },
        }

    async def _get(self, path: str) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            return response.json()

    async def _post(self, path: str, payload: Mapping[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                json=dict(payload),
            )
            response.raise_for_status()
            return response.json()


class SignalsLedgerPack:
    def __init__(
        self,
        *,
        state_root: str | Path,
        repo_root: Optional[str | Path] = None,
        python_executable: Optional[str] = None,
        web2_base_url: Optional[str] = None,
    ) -> None:
        self.state_root = Path(state_root)
        self.repo_root = Path(repo_root) if repo_root else None
        self.python_executable = python_executable or sys.executable
        self.web2_base_url = web2_base_url.rstrip("/") if web2_base_url else None

    def describe(self) -> Dict[str, Any]:
        return {
            "pack_id": "signals",
            "domain": "financial_analysis",
            "version": "0.1.0",
            "owner_repo": "Signals",
            "runtime": "cloud",
            "description": "Financial analysis flagship pack backed by the Signals run ledger.",
            "metadata": {
                "state_root": str(self.state_root),
                "repo_root": str(self.repo_root) if self.repo_root else None,
                "web2_base_url": self.web2_base_url,
            },
            "capabilities": self.capabilities(),
        }

    def capabilities(self) -> List[Dict[str, Any]]:
        return [
            {
                "capability_id": capability_id,
                "name": name,
                "description": description,
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "default": capability_id},
                        "start": {"type": "string"},
                        "market": {"type": "string"},
                        "push": {"type": "boolean"},
                    },
                },
            }
            for capability_id, name, description in [
                ("intraday", "Intraday Monitor", "实时盘中监测与多层联动分析"),
                ("review", "Review", "盘后复盘与阶段性对比"),
                ("index", "Index Report", "快速指数报告"),
                ("backtest", "Backtest", "历史信号验证与回测"),
                ("weekly", "Weekly", "周度总结与观察"),
                ("rss", "RSS", "市场资讯订阅与推送"),
            ]
        ]

    def health(self) -> Dict[str, Any]:
        runner = self.repo_root / "run.py" if self.repo_root else None
        env = self._env_config()
        tushare_token = bool(env.get("TUSHARE_TOKEN"))
        backtest_db_exists = self._backtest_db_path().exists()
        status = "ok"
        if not runner or not runner.exists() or not tushare_token:
            status = "degraded"
        return {
            "status": status,
            "checks": {
                "state_root_exists": self.state_root.exists(),
                "runner_exists": bool(runner and runner.exists()),
                "tushare_token_configured": tushare_token,
                "backtest_db_exists": backtest_db_exists,
                "weclaw_enabled": self._weclaw_enabled(env),
            },
        }

    async def list_runs(self) -> List[Dict[str, Any]]:
        runs_root = self.state_root / "runs"
        if not runs_root.exists():
            return []
        runs: List[Dict[str, Any]] = []
        for metadata_path in sorted(runs_root.glob("*/run.json")):
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            runs.append(self._normalize_run(payload))
        runs.sort(key=lambda run: str(run["created_at"]), reverse=True)
        return runs

    async def run(self, request: Mapping[str, Any]) -> Dict[str, Any]:
        if not self.repo_root:
            raise RuntimeError("SignalsLedgerPack cannot launch runs without repo_root")

        request_payload = dict(request)
        input_payload = dict(request_payload.get("input", request_payload))
        mode = str(input_payload.get("mode") or request_payload.get("capability") or "intraday")
        run_id = f"signals-{uuid.uuid4().hex[:10]}"
        run_dir = self.state_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = run_dir / "stdout.log"
        metadata_path = run_dir / "run.json"
        command = [self.python_executable, str(self.repo_root / "run.py"), "--mode", mode]
        command.extend(self._build_cli_args(input_payload))

        metadata = {
            "run_id": run_id,
            "domain": "financial_analysis",
            "capability": mode,
            "status": "running",
            "requested_by": request_payload.get("requested_by") or input_payload.get("requested_by"),
            "summary": f"Signals {mode}",
            "created_at": utc_now().isoformat(),
            "started_at": utc_now().isoformat(),
            "finished_at": None,
            "metadata": {
                "mode": mode,
                "command": command,
                "cwd": str(self.repo_root),
                "stdout_path": str(stdout_path),
                "state_root": str(self.state_root),
                "input": _safe_json_value(input_payload),
            },
        }

        wait = bool(request_payload.get("wait", False))
        if wait:
            completed = subprocess.run(
                command,
                cwd=self.repo_root,
                text=True,
                capture_output=True,
            )
            stdout_path.write_text(
                (completed.stdout or "") + (("\n" + completed.stderr) if completed.stderr else ""),
                encoding="utf-8",
            )
            metadata["status"] = "succeeded" if completed.returncode == 0 else "failed"
            metadata["finished_at"] = utc_now().isoformat()
            metadata["metadata"]["returncode"] = completed.returncode
        else:
            with stdout_path.open("w", encoding="utf-8") as handle:
                process = subprocess.Popen(
                    command,
                    cwd=self.repo_root,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            metadata["metadata"]["pid"] = process.pid

        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        normalized = self._normalize_run(metadata)
        return {
            "run": normalized,
            "artifacts": await self.list_artifacts(normalized["run_id"]),
            "review_actions": [],
        }

    async def list_artifacts(self, run_id: str) -> List[Dict[str, Any]]:
        payload = self._read_run_metadata(run_id)
        if not payload:
            return []
        artifacts: List[Dict[str, Any]] = []
        stdout_path = payload.get("metadata", {}).get("stdout_path")
        if stdout_path:
            artifacts.append(
                {
                    "artifact_id": f"{run_id}:stdout",
                    "run_id": run_id,
                    "kind": "stdout_log",
                    "uri": str(stdout_path),
                    "title": "signals stdout",
                    "metadata": {},
                }
            )
        output_dir = payload.get("metadata", {}).get("input", {}).get("output_dir")
        if output_dir:
            artifacts.append(
                {
                    "artifact_id": f"{run_id}:output",
                    "run_id": run_id,
                    "kind": "output_dir",
                    "uri": str(output_dir),
                    "title": "signals output",
                    "metadata": {},
                }
            )
        backtest_report_path = payload.get("metadata", {}).get("backtest_report_path")
        if backtest_report_path:
            artifacts.append(
                {
                    "artifact_id": f"{run_id}:backtest_report",
                    "run_id": run_id,
                    "kind": "backtest_report",
                    "uri": str(backtest_report_path),
                    "title": "backtest report",
                    "metadata": {},
                }
            )
        return artifacts

    async def review_actions(self, run_id: str) -> List[Dict[str, Any]]:
        payload = self._read_run_metadata(run_id)
        if not payload:
            return []
        report_path = payload.get("metadata", {}).get("backtest_report_path")
        if not report_path:
            return []
        return [
            {
                "action_id": f"pack:signals:report:push:{run_id}",
                "run_id": run_id,
                "kind": "push_report",
                "label": "Push Report",
                "payload": {
                    "run_id": run_id,
                    "report_path": str(report_path),
                },
            }
        ]

    async def list_manual_review_queue(self) -> List[Dict[str, Any]]:
        return []

    async def dashboard(
        self,
        *,
        recent_limit: int = 20,
        backlog_limit: int = 10,
    ) -> Dict[str, Any]:
        runs = await self.list_runs()
        recent_runs = runs[:recent_limit]
        review_runs = [
            run for run in recent_runs if str(run.get("capability")) == "review"
        ][: recent_limit // 2 or 1]
        return {
            "pack_id": "signals",
            "title": "Signals",
            "recent_runs": recent_runs,
            "review_runs": review_runs,
            "backtest_summary": self._backtest_summary(),
            "pending_backlog_preview": self._pending_backlog_preview(backlog_limit),
            "connector_health": self._connector_health(),
            "operator_actions": [
                {
                    "action_id": "pack:signals:run:review",
                    "run_id": "signals:dashboard",
                    "kind": "run_pack",
                    "label": "Run Review",
                    "payload": {
                        "pack_id": "signals",
                        "capability": "review",
                        "input": {"mode": "review"},
                    },
                },
                {
                    "action_id": "pack:signals:run:backtest",
                    "run_id": "signals:dashboard",
                    "kind": "run_pack",
                    "label": "Run Backtest",
                    "payload": {
                        "pack_id": "signals",
                        "capability": "backtest",
                        "input": {"mode": "backtest"},
                    },
                },
            ],
        }

    async def push_report(
        self,
        *,
        run_id: Optional[str] = None,
        report_path: Optional[str] = None,
        report_data: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.web2_base_url:
            raise RuntimeError("Signals push_report requires LONGCLAW_SIGNALS_WEB2_BASE_URL")

        resolved_data = dict(report_data or {})
        if not resolved_data:
            resolved_path = report_path
            if not resolved_path and run_id:
                payload = self._read_run_metadata(run_id)
                if payload:
                    resolved_path = payload.get("metadata", {}).get("backtest_report_path")
            if not resolved_path:
                raise RuntimeError("Signals push_report requires report_path or report_data")
            resolved_data = json.loads(Path(resolved_path).read_text(encoding="utf-8"))

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.web2_base_url}/api/backtest/push",
                json=resolved_data,
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {"ok": True, "data": payload}

    def eval_suite(self) -> List[Dict[str, Any]]:
        return [
            {
                "suite_id": "signals_ledger_pack",
                "name": "Signals Ledger Pack",
                "description": "Ledger compatibility for the Signals flagship pack.",
                "command": "python -m py_compile signals/domain_pack.py run.py",
            }
        ]

    def _normalize_run(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "run_id": str(payload["run_id"]),
            "domain": "financial_analysis",
            "capability": str(payload.get("capability") or payload.get("metadata", {}).get("mode") or "intraday"),
            "status": str(payload.get("status") or "queued"),
            "session_id": None,
            "task_id": None,
            "requested_by": payload.get("requested_by"),
            "summary": str(payload.get("summary") or ""),
            "created_at": payload.get("created_at"),
            "started_at": payload.get("started_at"),
            "finished_at": payload.get("finished_at"),
            "metadata": dict(payload.get("metadata", {})),
        }

    def _read_run_metadata(self, run_id: str) -> Optional[Dict[str, Any]]:
        path = self.state_root / "runs" / run_id / "run.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _env_config(self) -> Dict[str, str]:
        env = dict(os.environ)
        if self.repo_root:
            env.update(_read_dotenv(self.repo_root / ".env"))
        return env

    def _backtest_db_path(self) -> Path:
        env = self._env_config()
        raw_path = env.get("BACKTEST_DB_PATH", ".data/backtest.db")
        path = Path(raw_path)
        if not path.is_absolute() and self.repo_root:
            path = self.repo_root / path
        return path

    def _backtest_summary(self) -> Dict[str, int]:
        path = self._backtest_db_path()
        if not path.exists():
            return {"total": 0, "evaluated": 0, "pending": 0}
        connection = sqlite3.connect(path)
        try:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COALESCE(SUM(CASE WHEN evaluated = 1 THEN 1 ELSE 0 END), 0) as evaluated,
                    COALESCE(SUM(CASE WHEN evaluated = 0 THEN 1 ELSE 0 END), 0) as pending
                FROM signal_records
                """
            ).fetchone()
            return {
                "total": int(row[0] or 0),
                "evaluated": int(row[1] or 0),
                "pending": int(row[2] or 0),
            }
        finally:
            connection.close()

    def _pending_backlog_preview(self, limit: int) -> List[Dict[str, Any]]:
        path = self._backtest_db_path()
        if not path.exists():
            return []
        connection = sqlite3.connect(path)
        try:
            cursor = connection.execute(
                """
                SELECT symbol, signal_date, signal_type, freq, created_at
                FROM signal_records
                WHERE evaluated = 0
                ORDER BY signal_date DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [
                {
                    "symbol": row[0],
                    "signal_date": row[1],
                    "signal_type": row[2],
                    "freq": row[3],
                    "created_at": row[4],
                }
                for row in cursor.fetchall()
            ]
        finally:
            connection.close()

    def _connector_health(self) -> List[Dict[str, Any]]:
        env = self._env_config()
        runner_exists = bool(self.repo_root and (self.repo_root / "run.py").exists())
        tushare_token = bool(env.get("TUSHARE_TOKEN"))
        futu_configured = bool(env.get("FUTU_HOST")) and bool(env.get("FUTU_PORT"))
        weclaw_enabled = self._weclaw_enabled(env)
        return [
            {
                "connector_id": "tushare",
                "status": "ok" if tushare_token else "critical",
                "summary": "Tushare market data token",
                "details": {"configured": tushare_token},
            },
            {
                "connector_id": "futu",
                "status": "ok" if futu_configured else "warning",
                "summary": "Futu OpenD market data bridge",
                "details": {
                    "host": env.get("FUTU_HOST", ""),
                    "port": env.get("FUTU_PORT", ""),
                    "configured": futu_configured,
                },
            },
            {
                "connector_id": "weclaw_notify",
                "status": "ok" if weclaw_enabled else "info",
                "summary": "WeClaw push notification bridge",
                "details": {"enabled": weclaw_enabled},
            },
            {
                "connector_id": "runner",
                "status": "ok" if runner_exists else "critical",
                "summary": "Signals CLI runtime",
                "details": {
                    "repo_root": str(self.repo_root) if self.repo_root else "",
                    "runner_exists": runner_exists,
                },
            },
        ]

    @staticmethod
    def _weclaw_enabled(env: Mapping[str, Any]) -> bool:
        return str(env.get("WECLAW_ENABLED", "false")).lower() == "true"

    def _build_cli_args(self, input_payload: Mapping[str, Any]) -> List[str]:
        args: List[str] = []
        passthrough_keys = [
            "start",
            "industries",
            "notes",
            "file",
            "source",
            "author",
            "market",
            "signal_type",
            "freq_filter",
            "session",
            "end",
            "symbols",
            "port",
            "themes",
            "symbol",
        ]
        bool_keys = ["push", "dry_run", "list_dates", "create", "list_sessions", "sync"]
        for key in passthrough_keys:
            value = input_payload.get(key)
            if value is None or value == "":
                continue
            args.extend([f"--{key.replace('_', '-')}", str(value)])
        for key in bool_keys:
            if input_payload.get(key):
                args.append(f"--{key.replace('_', '-')}")
        return args
