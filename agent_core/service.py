from __future__ import annotations

import inspect
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .contracts import (
    Artifact,
    AdapterRegistry,
    DeliveryPolicy,
    DomainCapability,
    DomainPackRegistry,
    DomainRunRequest,
    ExecutionPlane,
    InboundEvent,
    InteractionSurface,
    LaunchIntent,
    LaunchReceipt,
    LocalRuntimeSeat,
    MemoryPlane,
    MemoryRecord,
    ModelPlane,
    OperatorAction,
    RuntimeProfile,
    RuntimeTarget,
    Run,
    RunStatus,
    Session,
    Task,
    TaskStatus,
    WorkMode,
    default_runtime_profile,
    execution_plane_for_runtime_target,
    interaction_surface_for_work_mode,
    runtime_target_for_work_mode,
)


class AgentOSService:
    def __init__(
        self,
        *,
        domain_packs: Optional[DomainPackRegistry] = None,
        adapters: Optional[AdapterRegistry] = None,
        state_root: Optional[str | Path] = None,
        mempalace_target: str = "mempalace://raw",
        obsidian_target: str = "obsidian://reviewed",
    ) -> None:
        self.domain_packs = domain_packs or DomainPackRegistry()
        self.adapters = adapters or AdapterRegistry()
        self.state_root = Path(
            state_root
            or os.environ.get(
                "LONGCLAW_AGENT_OS_STATE_DIR",
                Path.home() / ".hermes" / "agent-os",
            )
        )
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._memory_log_path = self.state_root / "memory-records.jsonl"
        self._adapter_event_log_path = self.state_root / "adapter-events.jsonl"
        self._tasks_log_path = self.state_root / "tasks.jsonl"
        self._local_runtime_runs_path = self.state_root / "local-runtime-runs.jsonl"
        self.mempalace_target = mempalace_target
        self.obsidian_target = obsidian_target

    @classmethod
    def from_env(cls) -> "AgentOSService":
        from .integrations import (
            ChanlessAdapter,
            RemoteDueDiligencePack,
            SignalsLedgerPack,
            WeclawAdapter,
        )

        service = cls(
            mempalace_target=os.environ.get("LONGCLAW_MEMPALACE_TARGET", "mempalace://raw"),
            obsidian_target=os.environ.get("LONGCLAW_OBSIDIAN_TARGET", "obsidian://reviewed"),
        )

        due_diligence_url = os.environ.get("LONGCLAW_DUE_DILIGENCE_API_URL")
        if due_diligence_url:
            service.register_pack(
                "due_diligence",
                RemoteDueDiligencePack(base_url=due_diligence_url),
            )

        signals_state_root = os.environ.get("LONGCLAW_SIGNALS_STATE_ROOT")
        if signals_state_root:
            service.register_pack(
                "signals",
                SignalsLedgerPack(
                    state_root=signals_state_root,
                    repo_root=os.environ.get("LONGCLAW_SIGNALS_REPO_ROOT"),
                    python_executable=os.environ.get("LONGCLAW_SIGNALS_PYTHON"),
                    web2_base_url=os.environ.get("LONGCLAW_SIGNALS_WEB2_BASE_URL"),
                ),
            )

        weclaw_api_url = cls._resolve_weclaw_api_url()
        if weclaw_api_url:
            service.register_adapter(
                "weclaw",
                WeclawAdapter(
                    base_url=weclaw_api_url,
                    default_to=os.environ.get("WECLAW_SEND_TO"),
                ),
            )

        if os.environ.get("LONGCLAW_ENABLE_CHANLESS_ADAPTER", "1") != "0":
            service.register_adapter("chanless", ChanlessAdapter())

        return service

    @staticmethod
    def _resolve_weclaw_api_url() -> Optional[str]:
        explicit = str(os.environ.get("WECLAW_API_URL", "")).strip()
        if explicit:
            return explicit

        api_addr = str(os.environ.get("WECLAW_API_ADDR", "")).strip()
        if api_addr:
            return AgentOSService._normalize_http_base_url(api_addr)

        config_path = Path.home() / ".weclaw" / "config.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                config = {}
            if isinstance(config, Mapping):
                configured_addr = str(config.get("api_addr") or "").strip()
                if configured_addr:
                    return AgentOSService._normalize_http_base_url(configured_addr)

        if default_runtime_profile() == RuntimeProfile.DEV_LOCAL_ACP_BRIDGE:
            return "http://127.0.0.1:18011"
        return None

    @staticmethod
    def _normalize_http_base_url(value: str) -> str:
        if value.startswith("http://") or value.startswith("https://"):
            return value.rstrip("/")
        return f"http://{value.rstrip('/')}"

    def register_pack(self, pack_id: str, pack: Any) -> None:
        self.domain_packs.register(pack_id, pack)

    def register_adapter(self, adapter_id: str, adapter: Any) -> None:
        self.adapters.register(adapter_id, adapter)

    async def ingest_event(
        self,
        adapter_id: str,
        event: InboundEvent | Mapping[str, Any],
    ) -> Dict[str, Any]:
        adapter = self.adapters.get(adapter_id)
        inbound = InboundEvent.model_validate(event)
        session_payload = await self._call(adapter, "ingest", inbound.model_dump(mode="json"))
        session = Session.model_validate(session_payload)
        if inbound.text:
            await self.record_memory(
                source=adapter_id,
                content=inbound.text,
                plane=MemoryPlane.RAW,
                session_id=session.session_id,
                metadata={
                    "channel": inbound.channel,
                    "channel_user_id": inbound.channel_user_id,
                },
            )
        await self._record_adapter_event(
            adapter_id,
            event_type="ingest",
            metadata={
                "channel": inbound.channel,
                "session_id": session.session_id,
            },
        )
        return session.model_dump(mode="json")

    async def deliver_run_via_adapter(
        self,
        adapter_id: str,
        run: Run | Mapping[str, Any],
        policy: DeliveryPolicy | Mapping[str, Any],
    ) -> Dict[str, Any]:
        adapter = self.adapters.get(adapter_id)
        run_obj = Run.model_validate(run)
        policy_obj = DeliveryPolicy.model_validate(policy)
        result = await self._call(
            adapter,
            "deliver",
            run_obj.model_dump(mode="json"),
            policy_obj.model_dump(mode="json"),
            default={},
        )
        await self._record_adapter_event(
            adapter_id,
            event_type="delivery",
            metadata={
                "run_id": run_obj.run_id,
                "delivered": bool((result or {}).get("delivered", False)),
                "policy_id": policy_obj.policy_id,
            },
        )
        return dict(result or {})

    async def run_pack(
        self,
        pack_id: str,
        request: DomainRunRequest | Mapping[str, Any],
    ) -> Dict[str, Any]:
        pack = self.domain_packs.get(pack_id)
        request_obj = DomainRunRequest.model_validate(request)
        result = await self._call(pack, "run", request_obj.model_dump(mode="json"))
        run_metadata = dict(result["run"].get("metadata") or {}) if isinstance(result.get("run"), Mapping) else {}
        request_metadata = dict(request_obj.metadata or {})
        task = request_obj.task
        work_mode = (
            task.work_mode
            if task is not None
            else self._coerce_work_mode(request_metadata.get("work_mode"), default=WorkMode.CLOUD_SANDBOX)
        )
        runtime_profile = (
            task.runtime_profile
            if task is not None
            else self._coerce_runtime_profile(
                request_metadata.get("runtime_profile"),
                default=default_runtime_profile(),
            )
        )
        runtime_target = (
            task.runtime_target
            if task is not None
            else self._coerce_runtime_target(
                request_metadata.get("runtime_target") or request_metadata.get("execution_plane"),
                default=self._runtime_target_for_mode(work_mode),
            )
        )
        interaction_surface = (
            task.interaction_surface
            if task is not None
            else self._coerce_interaction_surface(
                request_metadata.get("interaction_surface")
                or request_metadata.get("origin_surface")
                or request_metadata.get("launch_surface"),
                default=self._interaction_surface_for_mode(work_mode),
            )
        )
        model_plane = (
            task.model_plane
            if task is not None
            else self._coerce_model_plane(
                request_metadata.get("model_plane"),
                default=ModelPlane.CLOUD_PROVIDER,
            )
        )
        local_runtime_seat = (
            task.local_runtime_seat
            if task is not None
            else self._coerce_local_runtime_seat(
                request_metadata.get("local_runtime_seat") or run_metadata.get("local_runtime_seat"),
                default=self._default_local_runtime_seat(runtime_target, runtime_profile),
            )
        )
        execution_plane = (
            task.execution_plane
            if task is not None
            else self._execution_plane_for_runtime_target(runtime_target)
        )
        origin_surface = (
            task.origin_surface
            if task is not None
            else str(request_metadata.get("origin_surface") or request_metadata.get("launch_surface") or interaction_surface.value)
            or None
        )
        run = Run.model_validate(
            {
                **dict(result["run"]),
                "task_id": task.task_id if task is not None else result["run"].get("task_id"),
                "work_mode": work_mode,
                "origin_surface": origin_surface,
                "interaction_surface": interaction_surface,
                "runtime_profile": runtime_profile,
                "runtime_target": runtime_target,
                "model_plane": model_plane,
                "local_runtime_seat": local_runtime_seat,
                "execution_plane": execution_plane,
                "metadata": {
                **run_metadata,
                **request_metadata,
                "pack_id": pack_id,
                "work_mode": work_mode.value,
                "origin_surface": origin_surface,
                "interaction_surface": interaction_surface.value,
                "runtime_profile": runtime_profile.value,
                "runtime_target": runtime_target.value,
                "model_plane": model_plane.value,
                "local_runtime_seat": local_runtime_seat.value,
                "execution_plane": execution_plane.value,
            },
            }
        )
        return {
            "run": run.model_dump(mode="json"),
            "artifacts": result.get("artifacts", []),
            "approvals": result.get("approvals", []),
            "review_actions": result.get("review_actions", []),
        }

    async def compile_launch_intent(
        self,
        intent: LaunchIntent | Mapping[str, Any],
    ) -> Dict[str, Any]:
        launch = LaunchIntent.model_validate(intent)
        work_mode = self._resolve_work_mode(launch)
        interaction_surface = self._resolve_interaction_surface(launch, work_mode)
        runtime_profile = self._resolve_runtime_profile(launch)
        runtime_target = self._runtime_target_for_mode(work_mode)
        model_plane = self._resolve_model_plane(launch)
        local_runtime_seat = self._resolve_local_runtime_seat(
            launch,
            runtime_profile=runtime_profile,
            runtime_target=runtime_target,
        )
        execution_plane = self._execution_plane_for_runtime_target(runtime_target)
        launch_surface = self._resolve_launch_surface(launch, interaction_surface)
        workspace_target = self._resolve_workspace_target(launch)
        pack_id, capability = await self._resolve_launch_target(launch)
        session = self._build_launch_session(launch)
        channel = session.channel if session is not None else str(
            launch.session_context.get("channel") or launch.source
        )
        task_capability = f"{pack_id}.{capability}" if pack_id else capability
        task_input = self._build_launch_input(launch, capability)
        task = Task(
            task_id=f"task-{uuid.uuid4().hex[:12]}",
            capability=task_capability,
            session_id=session.session_id if session is not None else None,
            channel=channel,
            status=TaskStatus.ROUTING,
            input=task_input,
            work_mode=work_mode,
            origin_surface=launch_surface,
            interaction_surface=interaction_surface,
            runtime_profile=runtime_profile,
            runtime_target=runtime_target,
            model_plane=model_plane,
            local_runtime_seat=local_runtime_seat,
            execution_plane=execution_plane,
            metadata={
                **dict(launch.metadata),
                "launch_id": launch.launch_id,
                "launch_source": launch.source,
                "work_mode": work_mode.value,
                "origin_surface": launch_surface,
                "interaction_surface": interaction_surface.value,
                "runtime_profile": runtime_profile.value,
                "runtime_target": runtime_target.value,
                "model_plane": model_plane.value,
                "local_runtime_seat": local_runtime_seat.value,
                "execution_plane": execution_plane.value,
                "workspace_target": workspace_target,
                "pack_id": pack_id,
                "capability_id": capability,
                "requested_outcome": launch.requested_outcome,
                "raw_text": launch.raw_text,
                "mentions": [mention.model_dump(mode="json") for mention in launch.mentions],
                "skill_mentions": [
                    mention.value for mention in launch.mentions if str(mention.kind) == "skill"
                ],
                "plugin_mentions": [
                    mention.value for mention in launch.mentions if str(mention.kind) == "plugin"
                ],
            },
        )
        request = DomainRunRequest(
            capability=capability,
            input=task_input,
            session=session,
            task=task,
            delivery_policy=launch.delivery_preference,
            requested_by=(session.user_id if session is not None else launch.session_context.get("user_id")),
            metadata={
                "launch_id": launch.launch_id,
                "launch_source": launch.source,
                "work_mode": work_mode.value,
                "origin_surface": launch_surface,
                "interaction_surface": interaction_surface.value,
                "runtime_profile": runtime_profile.value,
                "runtime_target": runtime_target.value,
                "model_plane": model_plane.value,
                "local_runtime_seat": local_runtime_seat.value,
                "execution_plane": execution_plane.value,
                "workspace_target": workspace_target,
                "skill_mentions": task.metadata.get("skill_mentions", []),
                "plugin_mentions": task.metadata.get("plugin_mentions", []),
            },
        )
        return {
            "launch": launch,
            "work_mode": work_mode,
            "runtime_profile": runtime_profile,
            "runtime_target": runtime_target,
            "interaction_surface": interaction_surface,
            "model_plane": model_plane,
            "local_runtime_seat": local_runtime_seat,
            "execution_plane": execution_plane,
            "launch_surface": launch_surface,
            "workspace_target": workspace_target,
            "pack_id": pack_id,
            "task": task,
            "request": request,
        }

    async def launch(
        self,
        intent: LaunchIntent | Mapping[str, Any],
    ) -> Dict[str, Any]:
        compiled = await self.compile_launch_intent(intent)
        launch = compiled["launch"]
        raw_pack_id = compiled["pack_id"]
        pack_id = str(raw_pack_id or "local_runtime")
        task = Task.model_validate(compiled["task"])
        request = DomainRunRequest.model_validate(compiled["request"])
        local_runtime_seat = compiled.get("local_runtime_seat")

        await self._store_task(task)
        try:
            if not raw_pack_id:
                result = await self._launch_local_runtime(task, request)
            else:
                result = await self.run_pack(pack_id, request.model_dump(mode="json"))
        except Exception:
            await self._store_task(
                task.model_copy(
                    update={
                        "status": TaskStatus.FAILED,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
            )
            raise

        run = Run.model_validate(result["run"])
        artifacts = [Artifact.model_validate(item) for item in result.get("artifacts", [])]
        review_actions = [OperatorAction.model_validate(item) for item in result.get("review_actions", [])]
        run_ids = list(dict.fromkeys([*task.run_ids, run.run_id]))
        updated_task = task.model_copy(
            update={
                "status": self._task_status_from_run(run.status),
                "run_ids": run_ids,
                "last_run_id": run.run_id,
                "updated_at": datetime.now(timezone.utc),
                "metadata": {
                    **dict(task.metadata),
                    "last_run_status": run.status.value if isinstance(run.status, RunStatus) else str(run.status),
                },
            }
        )
        await self._store_task(updated_task)

        work_items = [
            item
            for item in await self.list_work_items()
            if str(item.get("run_id") or "") == run.run_id
        ]
        receipt = LaunchReceipt(
            launch_id=launch.launch_id,
            pack_id=pack_id,
            task=updated_task,
            run=run,
            artifacts=artifacts,
            review_actions=review_actions,
            work_items=work_items,
            compiled_input=request.input,
            metadata={
                "launch_source": launch.source,
                "work_mode": updated_task.work_mode.value,
                "origin_surface": updated_task.origin_surface,
                "interaction_surface": updated_task.interaction_surface.value,
                "runtime_profile": updated_task.runtime_profile.value,
                "runtime_target": updated_task.runtime_target.value,
                "model_plane": updated_task.model_plane.value,
                "local_runtime_seat": (
                    updated_task.local_runtime_seat.value
                    if isinstance(updated_task.local_runtime_seat, LocalRuntimeSeat)
                    else str(local_runtime_seat or updated_task.local_runtime_seat)
                ),
                "execution_plane": updated_task.execution_plane.value,
                "workspace_target": updated_task.metadata.get("workspace_target"),
            },
        )
        return receipt.model_dump(mode="json")

    async def list_tasks(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        tasks = list(self._read_tasks().values())
        tasks.sort(key=lambda item: item.updated_at, reverse=True)
        return [task.model_dump(mode="json") for task in tasks[:limit]]

    async def get_task(self, task_id: str) -> Dict[str, Any]:
        tasks = self._read_tasks()
        if task_id not in tasks:
            raise KeyError(task_id)
        return tasks[task_id].model_dump(mode="json")

    async def record_memory(
        self,
        *,
        source: str,
        content: str,
        plane: MemoryPlane = MemoryPlane.RAW,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> MemoryRecord:
        target = self.mempalace_target if plane == MemoryPlane.RAW else self.obsidian_target
        record = MemoryRecord(
            memory_id=f"memory-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            run_id=run_id,
            plane=plane,
            source=source,
            target=target,
            content=content,
            metadata=dict(metadata or {}),
        )
        with self._memory_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return record

    async def list_memory_records(
        self,
        *,
        limit: int = 50,
        plane: Optional[MemoryPlane] = None,
    ) -> List[MemoryRecord]:
        if not self._memory_log_path.exists():
            return []
        records: List[MemoryRecord] = []
        lines = self._memory_log_path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            record = MemoryRecord.model_validate(json.loads(line))
            if plane is not None and record.plane != plane:
                continue
            records.append(record)
            if len(records) >= limit:
                break
        return records

    async def list_packs(self) -> List[Dict[str, Any]]:
        return [
            descriptor.model_dump(mode="json")
            for descriptor in self.domain_packs.list_descriptors()
        ]

    async def list_adapters(self) -> List[Dict[str, Any]]:
        return [
            descriptor.model_dump(mode="json")
            for descriptor in self.adapters.list_descriptors()
        ]

    async def list_pack_health(self) -> List[Dict[str, Any]]:
        health_items: List[Dict[str, Any]] = []
        for pack_id, pack in self.domain_packs.items():
            health = await self._call(pack, "health", default={"status": "unknown", "checks": {}})
            health_items.append(
                {
                    "pack_id": pack_id,
                    "health": health,
                }
            )
        return health_items

    async def list_runs(self) -> List[Dict[str, Any]]:
        task_context = self._task_context_by_run_id()
        runs: List[Run] = []
        for run in self._read_local_runtime_runs():
            metadata = dict(run.metadata)
            context = task_context.get(run.run_id, {})
            work_mode = self._coerce_work_mode(
                context.get("work_mode") or metadata.get("work_mode"),
                default=run.work_mode,
            )
            runtime_profile = self._coerce_runtime_profile(
                context.get("runtime_profile") or metadata.get("runtime_profile"),
                default=run.runtime_profile,
            )
            runtime_target = self._coerce_runtime_target(
                context.get("runtime_target")
                or metadata.get("runtime_target")
                or context.get("execution_plane")
                or metadata.get("execution_plane"),
                default=run.runtime_target,
            )
            interaction_surface = self._coerce_interaction_surface(
                context.get("interaction_surface")
                or metadata.get("interaction_surface")
                or context.get("origin_surface")
                or metadata.get("origin_surface")
                or metadata.get("launch_surface"),
                default=run.interaction_surface,
            )
            model_plane = self._coerce_model_plane(
                context.get("model_plane") or metadata.get("model_plane"),
                default=run.model_plane,
            )
            local_runtime_seat = self._coerce_local_runtime_seat(
                context.get("local_runtime_seat") or metadata.get("local_runtime_seat"),
                default=run.local_runtime_seat,
            )
            execution_plane = self._coerce_execution_plane(
                context.get("execution_plane") or metadata.get("execution_plane"),
                default=run.execution_plane,
            )
            origin_surface = (
                context.get("origin_surface")
                or metadata.get("origin_surface")
                or metadata.get("launch_surface")
                or interaction_surface.value
            )
            runs.append(
                run.model_copy(
                    update={
                        "metadata": {
                            **metadata,
                            "pack_id": "local_runtime",
                        },
                        "task_id": run.task_id or context.get("task_id"),
                        "work_mode": work_mode,
                        "origin_surface": str(origin_surface) if origin_surface else None,
                        "interaction_surface": interaction_surface,
                        "runtime_profile": runtime_profile,
                        "runtime_target": runtime_target,
                        "model_plane": model_plane,
                        "local_runtime_seat": local_runtime_seat,
                        "execution_plane": execution_plane,
                        "pack_id": "local_runtime",
                    }
                )
            )
        for pack_id, pack in self.domain_packs.items():
            raw_runs = await self._call(pack, "list_runs", default=[])
            for raw_run in raw_runs or []:
                run = Run.model_validate(raw_run)
                metadata = dict(run.metadata)
                metadata.setdefault("pack_id", pack_id)
                context = task_context.get(run.run_id, {})
                work_mode = self._coerce_work_mode(
                    context.get("work_mode") or metadata.get("work_mode"),
                    default=WorkMode.CLOUD_SANDBOX,
                )
                runtime_profile = self._coerce_runtime_profile(
                    context.get("runtime_profile") or metadata.get("runtime_profile"),
                    default=default_runtime_profile(),
                )
                runtime_target = self._coerce_runtime_target(
                    context.get("runtime_target")
                    or metadata.get("runtime_target")
                    or context.get("execution_plane")
                    or metadata.get("execution_plane"),
                    default=self._runtime_target_for_mode(work_mode),
                )
                interaction_surface = self._coerce_interaction_surface(
                    context.get("interaction_surface")
                    or metadata.get("interaction_surface")
                    or context.get("origin_surface")
                    or metadata.get("origin_surface")
                    or metadata.get("launch_surface"),
                    default=self._interaction_surface_for_mode(work_mode),
                )
                model_plane = self._coerce_model_plane(
                    context.get("model_plane") or metadata.get("model_plane"),
                    default=ModelPlane.CLOUD_PROVIDER,
                )
                local_runtime_seat = self._coerce_local_runtime_seat(
                    context.get("local_runtime_seat") or metadata.get("local_runtime_seat"),
                    default=self._default_local_runtime_seat(runtime_target, runtime_profile),
                )
                execution_plane = self._coerce_execution_plane(
                    context.get("execution_plane") or metadata.get("execution_plane"),
                    default=self._execution_plane_for_runtime_target(runtime_target),
                )
                origin_surface = (
                    context.get("origin_surface")
                    or metadata.get("origin_surface")
                    or metadata.get("launch_surface")
                    or interaction_surface.value
                )
                runs.append(
                    run.model_copy(
                        update={
                            "metadata": metadata,
                            "task_id": run.task_id or context.get("task_id"),
                            "work_mode": work_mode,
                            "origin_surface": str(origin_surface) if origin_surface else None,
                            "interaction_surface": interaction_surface,
                            "runtime_profile": runtime_profile,
                            "runtime_target": runtime_target,
                            "model_plane": model_plane,
                            "local_runtime_seat": local_runtime_seat,
                            "execution_plane": execution_plane,
                            "pack_id": pack_id,
                        }
                    )
                )
        runs.sort(key=lambda item: item.created_at, reverse=True)
        return [run.model_dump(mode="json") for run in runs]

    async def list_artifacts(
        self,
        run_id: str,
        *,
        pack_id: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if pack_id:
            pack_items: Iterable[tuple[str, Any]] = [(pack_id, self.domain_packs.get(pack_id))]
        else:
            pack_items = self.domain_packs.items()

        descriptors = {
            descriptor.pack_id: descriptor
            for descriptor in self.domain_packs.list_descriptors()
        }
        artifacts: List[Artifact] = []
        for current_pack_id, pack in pack_items:
            if domain is not None:
                descriptor = descriptors.get(current_pack_id)
                if descriptor is None:
                    continue
                if descriptor.domain != domain:
                    continue
            raw_items = await self._call(pack, "list_artifacts", run_id, default=[])
            for raw_item in raw_items or []:
                artifact = Artifact.model_validate(raw_item)
                metadata = dict(artifact.metadata)
                metadata.setdefault("pack_id", current_pack_id)
                artifacts.append(artifact.model_copy(update={"metadata": metadata}))
        return [artifact.model_dump(mode="json") for artifact in artifacts]

    async def list_manual_review_queue(self) -> List[Dict[str, Any]]:
        queue: List[Dict[str, Any]] = []
        for pack_id, pack in self.domain_packs.items():
            items = await self._call(pack, "list_manual_review_queue", default=[])
            for item in items or []:
                normalized = dict(item)
                normalized.setdefault("pack_id", pack_id)
                queue.append(normalized)
        queue.sort(
            key=lambda item: str(item.get("finished_at") or item.get("created_at") or ""),
            reverse=True,
        )
        return queue

    async def list_workers(self) -> List[Dict[str, Any]]:
        workers: List[Dict[str, Any]] = []
        for pack_id, pack in self.domain_packs.items():
            items = await self._call(pack, "list_workers", default=[])
            for item in items or []:
                normalized = dict(item)
                normalized.setdefault("pack_id", pack_id)
                workers.append(normalized)
        return workers

    async def list_site_health(self) -> List[Dict[str, Any]]:
        items_out: List[Dict[str, Any]] = []
        for pack_id, pack in self.domain_packs.items():
            items = await self._call(pack, "list_site_health", default=[])
            for item in items or []:
                normalized = dict(item)
                normalized.setdefault("pack_id", pack_id)
                items_out.append(normalized)
        return items_out

    async def list_repair_cases(self) -> List[Dict[str, Any]]:
        items_out: List[Dict[str, Any]] = []
        for pack_id, pack in self.domain_packs.items():
            items = await self._call(pack, "list_repair_cases", default=[])
            for item in items or []:
                normalized = dict(item)
                normalized.setdefault("pack_id", pack_id)
                items_out.append(normalized)
        return items_out

    async def list_adapter_health(self) -> List[Dict[str, Any]]:
        recent_events = self._read_recent_adapter_events()
        health_items: List[Dict[str, Any]] = []
        for descriptor in self.adapters.list_descriptors():
            adapter_id = descriptor.adapter_id
            latest = recent_events.get(adapter_id, {})
            adapter = self.adapters.get(adapter_id)
            adapter_health = await self._call(adapter, "health", default={}) or {}
            status = str(adapter_health.get("status") or latest.get("status") or "unknown")
            notes = list(adapter_health.get("notes") or [])
            if not latest.get("last_ingest_at"):
                notes.append("No ingest observed yet")
            if not latest.get("last_delivery_at"):
                notes.append("No delivery observed yet")
            health_items.append(
                {
                    "adapter_id": adapter_id,
                    "channel": descriptor.channel,
                    "status": status,
                    "last_ingest_at": latest.get("last_ingest_at"),
                    "last_delivery_at": latest.get("last_delivery_at"),
                    "notes": notes,
                }
            )
        return health_items

    async def list_work_items(self) -> List[Dict[str, Any]]:
        work_items: List[Dict[str, Any]] = []

        for item in await self.list_manual_review_queue():
            work_items.append(self._build_due_diligence_manual_review_work_item(item))

        for item in await self.list_repair_cases():
            if str(item.get("status", "")).lower() != "open":
                continue
            work_items.append(self._build_due_diligence_repair_work_item(item))

        for item in await self.list_site_health():
            if str(item.get("recommended_action", "continue")) == "continue":
                continue
            work_items.append(self._build_due_diligence_site_health_work_item(item))

        if self.domain_packs.has("signals"):
            pack = self.domain_packs.get("signals")
            dashboard = await self._call(
                pack,
                "dashboard",
                recent_limit=20,
                backlog_limit=10,
                default={},
            )
            work_items.extend(await self._build_signals_work_items(dashboard or {}))

        work_items.sort(
            key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )
        return self._attach_work_item_context(work_items)

    async def get_pack_dashboard(self, pack_id: str) -> Dict[str, Any]:
        if not self.domain_packs.has(pack_id):
            raise KeyError(pack_id)

        if pack_id == "due_diligence":
            runs = [
                item
                for item in await self.list_runs()
                if str(item.get("metadata", {}).get("pack_id")) == "due_diligence"
            ][:20]
            queue = await self.list_manual_review_queue()
            repair_cases = await self.list_repair_cases()
            site_health = await self.list_site_health()
            return {
                "pack_id": "due_diligence",
                "title": "Due Diligence",
                "recent_runs": runs,
                "manual_review_queue": [
                    {
                        **item,
                        "artifact_refs": self._due_diligence_artifact_refs(item),
                        "operator_actions": self._due_diligence_review_actions(item),
                    }
                    for item in queue
                    if item.get("pack_id") == "due_diligence"
                ],
                "repair_cases": [
                    {
                        **item,
                        "operator_actions": self._due_diligence_repair_actions(item),
                    }
                    for item in repair_cases
                    if item.get("pack_id") == "due_diligence"
                ],
                "site_health": [
                    {
                        **item,
                        "operator_actions": [],
                    }
                    for item in site_health
                    if item.get("pack_id") == "due_diligence"
                ],
                "operator_actions": [],
            }

        pack = self.domain_packs.get(pack_id)
        dashboard = await self._call(
            pack,
            "dashboard",
            recent_limit=20,
            backlog_limit=10,
            default=None,
        )
        if dashboard is not None:
            return dict(dashboard)

        return {
            "pack_id": pack_id,
            "title": pack_id,
            "recent_runs": [
                item
                for item in await self.list_runs()
                if str(item.get("metadata", {}).get("pack_id")) == pack_id
            ][:20],
            "operator_actions": [],
        }

    async def execute_action(
        self,
        action_id: str,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        body = dict(payload or {})

        if action_id.startswith("pack:due_diligence:review:decision:"):
            parts = action_id.split(":")
            review_id = parts[-2]
            decision = body.get("decision") or parts[-1]
            pack = self.domain_packs.get("due_diligence")
            result = await self._call(
                pack,
                "submit_manual_review_decision",
                review_id,
                decision=decision,
                notes=body.get("notes"),
                default=None,
            )
            if result is None:
                raise KeyError(action_id)
            return {"action_id": action_id, "status": "ok", "result": result}

        if action_id.startswith("pack:due_diligence:run:retry:"):
            run_id = action_id.rsplit(":", 1)[-1]
            pack = self.domain_packs.get("due_diligence")
            result = await self._call(
                pack,
                "retry_run",
                run_id,
                site_scope=body.get("site_scope"),
                note=body.get("note"),
                default=None,
            )
            if result is None:
                raise KeyError(action_id)
            return {"action_id": action_id, "status": "ok", "result": result}

        if action_id == "pack:signals:run:review":
            return {
                "action_id": action_id,
                "status": "ok",
                "result": await self.run_pack(
                    "signals",
                    {
                        "capability": "review",
                        "input": body.get("input") or {"mode": "review"},
                        "requested_by": body.get("requested_by"),
                    },
                ),
            }

        if action_id == "pack:signals:run:backtest":
            return {
                "action_id": action_id,
                "status": "ok",
                "result": await self.run_pack(
                    "signals",
                    {
                        "capability": "backtest",
                        "input": body.get("input") or {"mode": "backtest"},
                        "requested_by": body.get("requested_by"),
                    },
                ),
            }

        if action_id.startswith("pack:signals:report:push:"):
            run_id = action_id.rsplit(":", 1)[-1]
            pack = self.domain_packs.get("signals")
            result = await self._call(
                pack,
                "push_report",
                run_id=run_id,
                report_path=body.get("report_path"),
                report_data=body.get("report_data"),
                default=None,
            )
            if result is None:
                raise KeyError(action_id)
            return {"action_id": action_id, "status": "ok", "result": result}

        raise KeyError(action_id)

    async def get_overview(self) -> Dict[str, Any]:
        tasks = await self.list_tasks(limit=200)
        runs = await self.list_runs()
        work_items = await self.list_work_items()
        return {
            "packs": await self.list_packs(),
            "adapters": await self.list_adapters(),
            "packHealth": await self.list_pack_health(),
            "adapterHealth": await self.list_adapter_health(),
            "mode_summary": self._summarize_modes(tasks, runs, work_items),
            "runs_summary": self._summarize_runs(runs),
            "work_items_summary": self._summarize_work_items(work_items),
            "recent_failures": [
                {
                    "run_id": run.get("run_id"),
                    "pack_id": run.get("metadata", {}).get("pack_id"),
                    "status": run.get("status"),
                    "work_mode": run.get("work_mode"),
                    "runtime_profile": run.get("runtime_profile"),
                    "runtime_target": run.get("runtime_target"),
                    "interaction_surface": run.get("interaction_surface"),
                    "model_plane": run.get("model_plane"),
                    "local_runtime_seat": run.get("local_runtime_seat"),
                    "execution_plane": run.get("execution_plane"),
                    "summary": run.get("summary", ""),
                    "created_at": run.get("created_at"),
                }
                for run in runs
                if str(run.get("status")) in {"failed", "repair_required", "partial"}
            ][:8],
            "memoryTargets": {
                "raw": self.mempalace_target,
                "reviewed": self.obsidian_target,
            },
        }

    async def get_health(self) -> Dict[str, Any]:
        pack_health = await self.list_pack_health()
        statuses = [str(item.get("health", {}).get("status", "unknown")) for item in pack_health]
        overall = "ok"
        if any(status not in {"ok", "unknown"} for status in statuses):
            overall = "degraded"
        return {
            "status": overall,
            "registered_packs": len(self.domain_packs.list_descriptors()),
            "registered_adapters": len(self.adapters.list_descriptors()),
            "memory_targets": {
                "raw": self.mempalace_target,
                "reviewed": self.obsidian_target,
            },
            "pack_health": pack_health,
        }

    async def _resolve_launch_target(self, launch: LaunchIntent) -> tuple[str, str]:
        routing_hints = self._launch_routing_hints(launch)
        pack_id = str(launch.metadata.get("pack_id") or routing_hints.get("default_pack_id") or "")
        capability_id = str(
            launch.metadata.get("capability")
            or routing_hints.get("default_capability")
            or ""
        )
        pack_mentions = [
            mention for mention in launch.mentions if str(mention.kind) == "pack"
        ]

        if pack_mentions:
            raw_target = str(pack_mentions[0].value or "").strip()
            parsed_pack, parsed_capability = self._parse_pack_target(raw_target)
            pack_id = parsed_pack or pack_id or raw_target
            capability_id = (
                parsed_capability
                or capability_id
                or str(pack_mentions[0].metadata.get("capability") or "")
            )

        if not pack_id:
            descriptors = self.domain_packs.list_descriptors()
            if len(descriptors) == 1:
                pack_id = descriptors[0].pack_id
            elif self._resolve_work_mode(launch) in {WorkMode.LOCAL, WorkMode.WECLAW_DISPATCH}:
                return "", self._local_runtime_capability_for_launch(launch)
            else:
                raise ValueError("LaunchIntent requires an @pack mention or metadata.pack_id")

        if not self.domain_packs.has(pack_id):
            raise KeyError(pack_id)

        if not capability_id:
            capability_id = await self._default_capability_for_pack(pack_id)

        return pack_id, capability_id

    def _local_runtime_capability_for_launch(self, launch: LaunchIntent) -> str:
        for mention in launch.mentions:
            kind = str(mention.kind).strip()
            value = str(mention.value).strip()
            if not value:
                continue
            if kind == "skill":
                return f"local_runtime.{value}"
            if kind == "plugin":
                return f"local_runtime.plugin:{value}"
        return (
            "local_runtime.weclaw_dispatch"
            if self._resolve_work_mode(launch) == WorkMode.WECLAW_DISPATCH
            else "local_runtime.local_work"
        )

    def _resolve_work_mode(self, launch: LaunchIntent) -> WorkMode:
        metadata_mode = (
            launch.metadata.get("work_mode")
            if isinstance(launch.metadata, Mapping)
            else None
        )
        session_mode = (
            launch.session_context.get("work_mode")
            if isinstance(launch.session_context, Mapping)
            else None
        )
        if launch.source == "weclaw" and not metadata_mode and not session_mode:
            if launch.work_mode == WorkMode.CLOUD_SANDBOX:
                return WorkMode.WECLAW_DISPATCH
        return self._coerce_work_mode(
            metadata_mode or session_mode or launch.work_mode,
            default=WorkMode.WECLAW_DISPATCH if launch.source == "weclaw" else WorkMode.CLOUD_SANDBOX,
        )

    def _resolve_launch_surface(
        self,
        launch: LaunchIntent,
        interaction_surface: InteractionSurface,
    ) -> str:
        return (
            str(launch.launch_surface or "")
            or str(launch.metadata.get("launch_surface") or "")
            or interaction_surface.value
        )

    def _resolve_interaction_surface(
        self,
        launch: LaunchIntent,
        work_mode: WorkMode,
    ) -> InteractionSurface:
        return self._coerce_interaction_surface(
            launch.interaction_surface
            or launch.metadata.get("interaction_surface")
            or launch.launch_surface
            or launch.metadata.get("launch_surface")
            or launch.metadata.get("origin_surface")
            or launch.source,
            default=self._interaction_surface_for_mode(work_mode),
        )

    def _resolve_runtime_profile(self, launch: LaunchIntent) -> RuntimeProfile:
        return self._coerce_runtime_profile(
            launch.runtime_profile
            or launch.metadata.get("runtime_profile")
            or launch.session_context.get("runtime_profile"),
            default=default_runtime_profile(),
        )

    def _resolve_local_runtime_seat(
        self,
        launch: LaunchIntent,
        *,
        runtime_profile: RuntimeProfile,
        runtime_target: RuntimeTarget,
    ) -> LocalRuntimeSeat:
        return self._coerce_local_runtime_seat(
            launch.local_runtime_seat
            or launch.metadata.get("local_runtime_seat")
            or launch.session_context.get("local_runtime_seat"),
            default=self._default_local_runtime_seat(runtime_target, runtime_profile),
        )

    def _resolve_model_plane(self, launch: LaunchIntent) -> ModelPlane:
        return self._coerce_model_plane(
            launch.model_plane
            or launch.metadata.get("model_plane")
            or launch.session_context.get("model_plane"),
            default=ModelPlane.CLOUD_PROVIDER,
        )

    def _resolve_workspace_target(self, launch: LaunchIntent) -> Optional[str]:
        for candidate in (
            launch.workspace_target,
            launch.metadata.get("workspace_target"),
            launch.session_context.get("workspace_root"),
            launch.session_context.get("context_token"),
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    def _coerce_work_mode(
        self,
        value: Any,
        *,
        default: WorkMode = WorkMode.CLOUD_SANDBOX,
    ) -> WorkMode:
        try:
            if isinstance(value, WorkMode):
                return value
            if isinstance(value, str) and value.strip():
                return WorkMode(value.strip())
        except ValueError:
            pass
        return default

    def _coerce_execution_plane(
        self,
        value: Any,
        *,
        default: ExecutionPlane,
    ) -> ExecutionPlane:
        try:
            if isinstance(value, ExecutionPlane):
                return value
            if isinstance(value, str) and value.strip():
                normalized = value.strip()
                if normalized == "weclaw_dispatch":
                    return ExecutionPlane.LOCAL_EXECUTOR
                return ExecutionPlane(normalized)
        except ValueError:
            pass
        return default

    def _coerce_runtime_profile(
        self,
        value: Any,
        *,
        default: RuntimeProfile,
    ) -> RuntimeProfile:
        try:
            if isinstance(value, RuntimeProfile):
                return value
            if isinstance(value, str) and value.strip():
                return RuntimeProfile(value.strip())
        except ValueError:
            pass
        return default

    def _coerce_runtime_target(
        self,
        value: Any,
        *,
        default: RuntimeTarget,
    ) -> RuntimeTarget:
        try:
            if isinstance(value, RuntimeTarget):
                return value
            if isinstance(value, str) and value.strip():
                normalized = value.strip()
                if normalized in {RuntimeTarget.LOCAL_RUNTIME.value, ExecutionPlane.LOCAL_EXECUTOR.value, WorkMode.LOCAL.value, WorkMode.WECLAW_DISPATCH.value}:
                    return RuntimeTarget.LOCAL_RUNTIME
                if normalized in {RuntimeTarget.CLOUD_RUNTIME.value, ExecutionPlane.CLOUD_EXECUTOR.value, WorkMode.CLOUD_SANDBOX.value}:
                    return RuntimeTarget.CLOUD_RUNTIME
        except ValueError:
            pass
        return default

    def _coerce_interaction_surface(
        self,
        value: Any,
        *,
        default: InteractionSurface,
    ) -> InteractionSurface:
        if isinstance(value, InteractionSurface):
            return value
        if isinstance(value, str) and value.strip():
            normalized = value.strip().lower()
            if normalized == InteractionSurface.WECLAW.value or "weclaw" in normalized or "wechat" in normalized or "dispatch" in normalized:
                return InteractionSurface.WECLAW
            if normalized == InteractionSurface.ELECTRON_HOME.value or "electron" in normalized or "home" in normalized or "desktop" in normalized:
                return InteractionSurface.ELECTRON_HOME
        return default

    def _coerce_model_plane(
        self,
        value: Any,
        *,
        default: ModelPlane,
    ) -> ModelPlane:
        try:
            if isinstance(value, ModelPlane):
                return value
            if isinstance(value, str) and value.strip():
                return ModelPlane(value.strip())
        except ValueError:
            pass
        return default

    def _coerce_local_runtime_seat(
        self,
        value: Any,
        *,
        default: LocalRuntimeSeat,
    ) -> LocalRuntimeSeat:
        try:
            if isinstance(value, LocalRuntimeSeat):
                return value
            if isinstance(value, str) and value.strip():
                return LocalRuntimeSeat(value.strip())
        except ValueError:
            pass
        return default

    def _runtime_target_for_mode(self, work_mode: WorkMode) -> RuntimeTarget:
        return runtime_target_for_work_mode(work_mode)

    def _interaction_surface_for_mode(self, work_mode: WorkMode) -> InteractionSurface:
        return interaction_surface_for_work_mode(work_mode)

    def _execution_plane_for_runtime_target(self, runtime_target: RuntimeTarget) -> ExecutionPlane:
        return execution_plane_for_runtime_target(runtime_target)

    def _default_local_runtime_seat(
        self,
        runtime_target: RuntimeTarget,
        runtime_profile: RuntimeProfile,
    ) -> LocalRuntimeSeat:
        if runtime_target == RuntimeTarget.CLOUD_RUNTIME:
            return LocalRuntimeSeat.UNAVAILABLE
        if runtime_profile == RuntimeProfile.PACKAGED_LOCAL_RUNTIME:
            return LocalRuntimeSeat.LOCAL_RUNTIME_API
        if runtime_profile == RuntimeProfile.DEV_LOCAL_ACP_BRIDGE:
            return LocalRuntimeSeat.ACP_BRIDGE
        return LocalRuntimeSeat.UNAVAILABLE

    def _launch_routing_hints(self, launch: LaunchIntent) -> Dict[str, Any]:
        metadata = dict(launch.metadata or {})
        hints: Dict[str, Any] = {}

        routing_hint = metadata.get("routing_hint")
        if isinstance(routing_hint, Mapping):
            hints.update(dict(routing_hint))

        if metadata.get("default_pack_id"):
            hints.setdefault("default_pack_id", metadata.get("default_pack_id"))
        if metadata.get("default_capability"):
            hints.setdefault("default_capability", metadata.get("default_capability"))

        env_default_pack = os.environ.get("LONGCLAW_DEFAULT_LAUNCH_PACK", "").strip()
        env_default_capability = os.environ.get("LONGCLAW_DEFAULT_LAUNCH_CAPABILITY", "").strip()
        if env_default_pack:
            hints.setdefault("default_pack_id", env_default_pack)
        if env_default_capability:
            hints.setdefault("default_capability", env_default_capability)

        return hints

    def _parse_pack_target(self, raw_target: str) -> tuple[str, str]:
        if ":" in raw_target:
            pack_id, capability_id = raw_target.split(":", 1)
            return pack_id.strip(), capability_id.strip()
        if raw_target.count(".") == 1:
            pack_id, capability_id = raw_target.split(".", 1)
            return pack_id.strip(), capability_id.strip()
        return raw_target.strip(), ""

    async def _default_capability_for_pack(self, pack_id: str) -> str:
        descriptor = next(
            (item for item in self.domain_packs.list_descriptors() if item.pack_id == pack_id),
            None,
        )
        capabilities = list(descriptor.capabilities) if descriptor is not None else []
        if not capabilities:
            pack = self.domain_packs.get(pack_id)
            raw_capabilities = await self._call(pack, "capabilities", default=[])
            capabilities = [DomainCapability.model_validate(item) for item in raw_capabilities or []]
        if not capabilities:
            raise ValueError(f"Pack '{pack_id}' does not expose any launchable capabilities")
        return capabilities[0].capability_id

    def _build_launch_session(self, launch: LaunchIntent) -> Optional[Session]:
        context = dict(launch.session_context or {})
        session_id = str(
            context.get("session_id")
            or context.get("canonical_session_id")
            or (f"session:{context['user_id']}" if context.get("user_id") else "")
        ).strip()
        canonical_id = str(
            context.get("canonical_id")
            or (f"user:{context['user_id']}" if context.get("user_id") else "")
        ).strip()
        if not session_id or not canonical_id:
            return None

        metadata = {
            key: value
            for key, value in context.items()
            if key not in {"session_id", "canonical_session_id", "canonical_id", "channel", "user_id"}
        }
        return Session(
            session_id=session_id,
            canonical_id=canonical_id,
            channel=str(context.get("channel") or launch.source),
            user_id=context.get("user_id"),
            metadata=metadata,
        )

    def _build_launch_input(self, launch: LaunchIntent, capability: str) -> Dict[str, Any]:
        input_payload = dict(launch.metadata.get("input") or {})
        work_mode = self._resolve_work_mode(launch)
        interaction_surface = self._resolve_interaction_surface(launch, work_mode)
        input_payload.setdefault("work_mode", work_mode.value)
        input_payload.setdefault("launch_surface", self._resolve_launch_surface(launch, interaction_surface))
        input_payload.setdefault("interaction_surface", interaction_surface.value)
        runtime_profile = self._resolve_runtime_profile(launch)
        runtime_target = self._runtime_target_for_mode(work_mode)
        input_payload.setdefault("runtime_profile", runtime_profile.value)
        input_payload.setdefault("runtime_target", runtime_target.value)
        input_payload.setdefault("model_plane", self._resolve_model_plane(launch).value)
        input_payload.setdefault(
            "local_runtime_seat",
            self._resolve_local_runtime_seat(
                launch,
                runtime_profile=runtime_profile,
                runtime_target=runtime_target,
            ).value,
        )
        workspace_target = self._resolve_workspace_target(launch)
        if workspace_target:
            input_payload.setdefault("workspace_target", workspace_target)
        if launch.requested_outcome:
            input_payload.setdefault("requested_outcome", launch.requested_outcome)
        if launch.raw_text:
            input_payload.setdefault("raw_text", launch.raw_text)
            input_payload.setdefault("query", launch.requested_outcome or launch.raw_text)
        if capability in {"review", "backtest", "intraday", "index", "weekly", "rss"}:
            input_payload.setdefault("mode", capability)
        return input_payload

    async def _launch_local_runtime(
        self,
        task: Task,
        request: DomainRunRequest,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        run = Run(
            run_id=f"run-{uuid.uuid4().hex[:12]}",
            domain="local_runtime",
            capability=request.capability,
            status=RunStatus.QUEUED,
            session_id=task.session_id,
            task_id=task.task_id,
            requested_by=request.requested_by,
            work_mode=task.work_mode,
            origin_surface=task.origin_surface,
            interaction_surface=task.interaction_surface,
            runtime_profile=task.runtime_profile,
            runtime_target=task.runtime_target,
            model_plane=task.model_plane,
            local_runtime_seat=task.local_runtime_seat,
            execution_plane=task.execution_plane,
            summary=str(
                task.input.get("requested_outcome")
                or task.input.get("query")
                or task.input.get("raw_text")
                or "Queued for local runtime execution"
            ),
            created_at=now,
            started_at=now,
            metadata={
                **dict(task.metadata),
                "pack_id": "local_runtime",
                "internal_runtime": True,
            },
        )
        await self._store_local_runtime_run(run)
        return {
            "run": run.model_dump(mode="json"),
            "artifacts": [],
            "review_actions": [],
        }

    def _task_status_from_run(self, status: RunStatus | str) -> TaskStatus:
        value = status.value if isinstance(status, RunStatus) else str(status)
        mapping = {
            "queued": TaskStatus.QUEUED,
            "running": TaskStatus.RUNNING,
            "waiting_approval": TaskStatus.BLOCKED,
            "repair_required": TaskStatus.BLOCKED,
            "succeeded": TaskStatus.SUCCEEDED,
            "partial": TaskStatus.PARTIAL,
            "failed": TaskStatus.FAILED,
            "canceled": TaskStatus.CANCELED,
        }
        return mapping.get(value, TaskStatus.ROUTING)

    def _task_context_by_run_id(self) -> Dict[str, Dict[str, Any]]:
        context_by_run: Dict[str, Dict[str, Any]] = {}
        for task in self._read_tasks().values():
            context = {
                "task_id": task.task_id,
                "work_mode": task.work_mode.value,
                "origin_surface": task.origin_surface,
                "interaction_surface": task.interaction_surface.value,
                "runtime_profile": task.runtime_profile.value,
                "runtime_target": task.runtime_target.value,
                "model_plane": task.model_plane.value,
                "local_runtime_seat": task.local_runtime_seat.value,
                "execution_plane": task.execution_plane.value,
            }
            for run_id in task.run_ids:
                context_by_run[str(run_id)] = context
            if task.last_run_id and task.last_run_id not in context_by_run:
                context_by_run[str(task.last_run_id)] = context
        return context_by_run

    def _attach_work_item_context(self, work_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        run_context = self._task_context_by_run_id()
        enriched: List[Dict[str, Any]] = []
        for item in work_items:
            run_id = str(item.get("run_id") or "")
            context = run_context.get(run_id, {})
            work_mode = self._coerce_work_mode(
                item.get("work_mode") or context.get("work_mode"),
                default=WorkMode.CLOUD_SANDBOX,
            )
            runtime_profile = self._coerce_runtime_profile(
                item.get("runtime_profile") or context.get("runtime_profile"),
                default=default_runtime_profile(),
            )
            runtime_target = self._coerce_runtime_target(
                item.get("runtime_target")
                or context.get("runtime_target")
                or item.get("execution_plane")
                or context.get("execution_plane"),
                default=self._runtime_target_for_mode(work_mode),
            )
            interaction_surface = self._coerce_interaction_surface(
                item.get("interaction_surface")
                or context.get("interaction_surface")
                or item.get("origin_surface")
                or context.get("origin_surface"),
                default=self._interaction_surface_for_mode(work_mode),
            )
            model_plane = self._coerce_model_plane(
                item.get("model_plane") or context.get("model_plane"),
                default=ModelPlane.CLOUD_PROVIDER,
            )
            local_runtime_seat = self._coerce_local_runtime_seat(
                item.get("local_runtime_seat") or context.get("local_runtime_seat"),
                default=self._default_local_runtime_seat(runtime_target, runtime_profile),
            )
            execution_plane = self._coerce_execution_plane(
                item.get("execution_plane") or context.get("execution_plane"),
                default=self._execution_plane_for_runtime_target(runtime_target),
            )
            origin_surface = item.get("origin_surface") or context.get("origin_surface") or interaction_surface.value
            enriched.append(
                {
                    **item,
                    "work_mode": work_mode.value,
                    "runtime_profile": runtime_profile.value,
                    "runtime_target": runtime_target.value,
                    "interaction_surface": interaction_surface.value,
                    "model_plane": model_plane.value,
                    "local_runtime_seat": local_runtime_seat.value,
                    "execution_plane": execution_plane.value,
                    "origin_surface": origin_surface,
                }
            )
        return enriched

    async def _store_task(self, task: Task) -> None:
        with self._tasks_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(task.model_dump(mode="json"), ensure_ascii=False) + "\n")

    async def _store_local_runtime_run(self, run: Run) -> None:
        with self._local_runtime_runs_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(run.model_dump(mode="json"), ensure_ascii=False) + "\n")

    def _read_tasks(self) -> Dict[str, Task]:
        if not self._tasks_log_path.exists():
            return {}
        tasks: Dict[str, Task] = {}
        for line in self._tasks_log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            task = Task.model_validate(json.loads(line))
            tasks[task.task_id] = task
        return tasks

    def _read_local_runtime_runs(self) -> List[Run]:
        if not self._local_runtime_runs_path.exists():
            return []
        runs: Dict[str, Run] = {}
        for line in self._local_runtime_runs_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            run = Run.model_validate(json.loads(line))
            runs[run.run_id] = run
        return sorted(runs.values(), key=lambda item: item.created_at, reverse=True)

    async def _record_adapter_event(
        self,
        adapter_id: str,
        *,
        event_type: str,
        metadata: Mapping[str, Any],
    ) -> None:
        payload = {
            "adapter_id": adapter_id,
            "event_type": event_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": dict(metadata),
        }
        with self._adapter_event_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _read_recent_adapter_events(self) -> Dict[str, Dict[str, Any]]:
        if not self._adapter_event_log_path.exists():
            return {}
        latest: Dict[str, Dict[str, Any]] = {}
        for line in self._adapter_event_log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            adapter_id = str(payload.get("adapter_id"))
            entry = latest.setdefault(adapter_id, {})
            created_at = payload.get("created_at")
            if payload.get("event_type") == "ingest":
                entry["last_ingest_at"] = created_at
            if payload.get("event_type") == "delivery" and payload.get("metadata", {}).get("delivered", False):
                entry["last_delivery_at"] = created_at
                entry["status"] = "ok"
        return latest

    def _summarize_runs(self, runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        for run in runs:
            status = str(run.get("status") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1
        return {
            "total": len(runs),
            "by_status": by_status,
            "running": by_status.get("running", 0),
            "failed": by_status.get("failed", 0) + by_status.get("repair_required", 0),
            "partial": by_status.get("partial", 0),
            "succeeded": by_status.get("succeeded", 0),
        }

    def _summarize_work_items(self, work_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_severity: Dict[str, int] = {}
        for item in work_items:
            severity = str(item.get("severity") or "info")
            by_severity[severity] = by_severity.get(severity, 0) + 1
        return {
            "total": len(work_items),
            "open": sum(1 for item in work_items if str(item.get("status")) != "resolved"),
            "critical": by_severity.get("critical", 0),
            "warning": by_severity.get("warning", 0),
            "info": by_severity.get("info", 0),
        }

    def _summarize_modes(
        self,
        tasks: List[Dict[str, Any]],
        runs: List[Dict[str, Any]],
        work_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        tasks_by_mode = {
            mode.value: sum(1 for task in tasks if str(task.get("work_mode")) == mode.value)
            for mode in WorkMode
        }
        runs_by_mode = {
            mode.value: sum(1 for run in runs if str(run.get("work_mode")) == mode.value)
            for mode in WorkMode
        }
        work_items_by_mode = {
            mode.value: sum(1 for item in work_items if str(item.get("work_mode")) == mode.value)
            for mode in WorkMode
        }
        return {
            "tasks": tasks_by_mode,
            "runs": runs_by_mode,
            "work_items": work_items_by_mode,
        }

    def _local_action(self, *, label: str, value: Optional[str], run_id: str) -> Optional[Dict[str, Any]]:
        if not value:
            return None
        if value.startswith("http://") or value.startswith("https://"):
            kind = "open_url"
            payload = {"url": value}
        elif value.startswith("/"):
            kind = "open_path"
            payload = {"path": value}
        else:
            kind = "copy_value"
            payload = {"value": value}
        return {
            "action_id": f"local:{kind}:{uuid.uuid5(uuid.NAMESPACE_URL, value).hex[:12]}",
            "run_id": run_id,
            "kind": kind,
            "label": label,
            "payload": payload,
            "metadata": {"local": True},
        }

    def _artifact_ref(self, *, uri: Optional[str], kind: str, title: str) -> Optional[Dict[str, Any]]:
        if not uri:
            return None
        return {
            "kind": kind,
            "uri": uri,
            "title": title,
        }

    def _due_diligence_artifact_refs(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        refs = [
            self._artifact_ref(uri=item.get("artifact_uri"), kind="artifact", title="Evidence Artifact"),
            self._artifact_ref(uri=item.get("evidence_root"), kind="evidence_root", title="Evidence Root"),
            self._artifact_ref(uri=item.get("report_path"), kind="report", title="Report Markdown"),
            self._artifact_ref(uri=item.get("report_json_path"), kind="report_json", title="Report JSON"),
        ]
        return [ref for ref in refs if ref]

    def _due_diligence_review_actions(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        for label, uri in [
            ("Open Evidence", item.get("evidence_root") or item.get("artifact_uri")),
            ("Open Report", item.get("report_path")),
        ]:
            local_action = self._local_action(
                label=label,
                value=uri,
                run_id=str(item.get("run_id") or "due_diligence"),
            )
            if local_action is not None:
                actions.append(local_action)

        review_id = str(item.get("review_id"))
        run_id = str(item.get("run_id") or "due_diligence")
        for decision, label in [
            ("approved", "Approve"),
            ("rejected", "Reject"),
            ("needs_retry", "Retry"),
            ("defer", "Defer"),
        ]:
            actions.append(
                {
                    "action_id": f"pack:due_diligence:review:decision:{review_id}:{decision}",
                    "run_id": run_id,
                    "kind": "submit_review_decision",
                    "label": label,
                    "payload": {
                        "pack_id": "due_diligence",
                        "review_id": review_id,
                        "decision": decision,
                    },
                }
            )
        return actions

    def _due_diligence_repair_actions(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        replay_pack_path = item.get("replay_pack_path")
        local_action = self._local_action(
            label="Open Replay Pack",
            value=str(replay_pack_path) if replay_pack_path else None,
            run_id=str((item.get("recent_run_ids") or ["due_diligence"])[0]),
        )
        if local_action is not None:
            actions.append(local_action)

        recent_run_ids = list(item.get("recent_run_ids") or [])
        if recent_run_ids:
            latest_run_id = str(recent_run_ids[-1])
            actions.append(
                {
                    "action_id": f"pack:due_diligence:run:retry:{latest_run_id}",
                    "run_id": latest_run_id,
                    "kind": "retry_run",
                    "label": "Retry Run",
                    "payload": {
                        "pack_id": "due_diligence",
                        "run_id": latest_run_id,
                    },
                }
            )
        return actions

    def _build_due_diligence_manual_review_work_item(self, item: Mapping[str, Any]) -> Dict[str, Any]:
        pack_id = str(item.get("pack_id") or "due_diligence")
        return {
            "work_item_id": f"work:{pack_id}:review:{item.get('review_id')}",
            "pack_id": pack_id,
            "kind": "manual_review",
            "title": f"Manual Review: {item.get('site_slug')}",
            "summary": item.get("summary") or "Manual review required",
            "severity": "warning",
            "status": "open",
            "run_id": item.get("run_id"),
            "artifact_refs": self._due_diligence_artifact_refs(item),
            "operator_actions": self._due_diligence_review_actions(item),
            "created_at": item.get("created_at"),
            "updated_at": item.get("finished_at") or item.get("created_at"),
            "metadata": dict(item),
        }

    def _build_due_diligence_repair_work_item(self, item: Mapping[str, Any]) -> Dict[str, Any]:
        pack_id = str(item.get("pack_id") or "due_diligence")
        return {
            "work_item_id": f"work:{pack_id}:repair:{item.get('case_id')}",
            "pack_id": pack_id,
            "kind": "repair_case",
            "title": f"Repair Case: {item.get('site_slug')}",
            "summary": item.get("trigger_reason") or "Repair case open",
            "severity": "critical",
            "status": str(item.get("status") or "open"),
            "run_id": (item.get("recent_run_ids") or [None])[-1],
            "artifact_refs": [
                ref
                for ref in [
                    self._artifact_ref(
                        uri=str(item.get("replay_pack_path")) if item.get("replay_pack_path") else None,
                        kind="replay_pack",
                        title="Replay Pack",
                    )
                ]
                if ref
            ],
            "operator_actions": self._due_diligence_repair_actions(item),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at") or item.get("created_at"),
            "metadata": dict(item),
        }

    def _build_due_diligence_site_health_work_item(self, item: Mapping[str, Any]) -> Dict[str, Any]:
        action = str(item.get("recommended_action") or "continue")
        severity = "critical" if action == "repair_case" else "warning"
        pack_id = str(item.get("pack_id") or "due_diligence")
        return {
            "work_item_id": f"work:{pack_id}:site_health:{item.get('site_slug')}",
            "pack_id": pack_id,
            "kind": "site_health",
            "title": f"Site Health: {item.get('site_slug')}",
            "summary": f"Recommended action: {action}",
            "severity": severity,
            "status": "open",
            "run_id": None,
            "artifact_refs": [],
            "operator_actions": [],
            "created_at": None,
            "updated_at": None,
            "metadata": dict(item),
        }

    async def _build_signals_work_items(self, dashboard: Mapping[str, Any]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        recent_runs = list(dashboard.get("recent_runs") or [])
        for run in recent_runs[:20]:
            if str(run.get("status")) != "failed":
                continue
            artifacts = await self.list_artifacts(str(run.get("run_id")), domain="financial_analysis")
            actions = [
                action
                for action in [
                    self._local_action(
                        label=f"Open {artifact.get('title') or artifact.get('kind')}",
                        value=str(artifact.get("uri")),
                        run_id=str(run.get("run_id")),
                    )
                    for artifact in artifacts
                ]
                if action
            ]
            items.append(
                {
                    "work_item_id": f"work:signals:failed_run:{run.get('run_id')}",
                    "pack_id": "signals",
                    "kind": "failed_run",
                    "title": f"Failed Run: {run.get('capability')}",
                    "summary": run.get("summary") or "Signals run failed",
                    "severity": "warning",
                    "status": "open",
                    "run_id": run.get("run_id"),
                    "artifact_refs": [
                        {
                            "kind": artifact.get("kind"),
                            "uri": artifact.get("uri"),
                            "title": artifact.get("title"),
                        }
                        for artifact in artifacts
                    ],
                    "operator_actions": actions,
                    "created_at": run.get("created_at"),
                    "updated_at": run.get("finished_at") or run.get("created_at"),
                    "metadata": dict(run),
                }
            )

        backtest_summary = dict(dashboard.get("backtest_summary") or {})
        pending = int(backtest_summary.get("pending") or 0)
        if pending > 0:
            severity = "critical" if pending > 100 else "warning"
            items.append(
                {
                    "work_item_id": "work:signals:backtest_backlog",
                    "pack_id": "signals",
                    "kind": "backtest_backlog",
                    "title": "Backtest Backlog",
                    "summary": f"{pending} pending signals require evaluation",
                    "severity": severity,
                    "status": "open",
                    "run_id": None,
                    "artifact_refs": [],
                    "operator_actions": [
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
                        }
                    ],
                    "created_at": None,
                    "updated_at": None,
                    "metadata": backtest_summary,
                }
            )

        for connector in list(dashboard.get("connector_health") or []):
            status = str(connector.get("status") or "info")
            if status == "ok":
                continue
            severity = "critical" if status == "critical" else "info"
            items.append(
                {
                    "work_item_id": f"work:signals:connector:{connector.get('connector_id')}",
                    "pack_id": "signals",
                    "kind": "connector_health",
                    "title": f"Connector: {connector.get('connector_id')}",
                    "summary": connector.get("summary") or "Signals connector requires attention",
                    "severity": severity,
                    "status": "open",
                    "run_id": None,
                    "artifact_refs": [],
                    "operator_actions": [],
                    "created_at": None,
                    "updated_at": None,
                    "metadata": dict(connector),
                }
            )

        return items

    async def _call(
        self,
        obj: Any,
        method_name: str,
        *args: Any,
        default: Any = None,
        **kwargs: Any,
    ) -> Any:
        method = getattr(obj, method_name, None)
        if method is None:
            return default
        result = method(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
