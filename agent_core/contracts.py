from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import os
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionStatus(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    ROUTING = "routing"
    RUNNING = "running"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELED = "canceled"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    REPAIR_REQUIRED = "repair_required"
    FAILED = "failed"
    CANCELED = "canceled"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ReviewDecisionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"


class MemoryPlane(str, Enum):
    RAW = "raw"
    REVIEWED = "reviewed"


class WorkMode(str, Enum):
    LOCAL = "local"
    CLOUD_SANDBOX = "cloud_sandbox"
    WECLAW_DISPATCH = "weclaw_dispatch"


class ExecutionPlane(str, Enum):
    LOCAL_EXECUTOR = "local_executor"
    CLOUD_EXECUTOR = "cloud_executor"


class RuntimeProfile(str, Enum):
    DEV_LOCAL_ACP_BRIDGE = "dev_local_acp_bridge"
    PACKAGED_LOCAL_RUNTIME = "packaged_local_runtime"
    CLOUD_MANAGED_RUNTIME = "cloud_managed_runtime"


class RuntimeTarget(str, Enum):
    LOCAL_RUNTIME = "local_runtime"
    CLOUD_RUNTIME = "cloud_runtime"


class InteractionSurface(str, Enum):
    ELECTRON_HOME = "electron_home"
    WECLAW = "weclaw"


class ModelPlane(str, Enum):
    CLOUD_PROVIDER = "cloud_provider"


class LocalRuntimeSeat(str, Enum):
    ACP_BRIDGE = "acp_bridge"
    LOCAL_RUNTIME_API = "local_runtime_api"
    UNAVAILABLE = "unavailable"


def default_runtime_profile() -> RuntimeProfile:
    candidate = str(os.environ.get("LONGCLAW_RUNTIME_PROFILE", RuntimeProfile.DEV_LOCAL_ACP_BRIDGE.value)).strip()
    try:
        return RuntimeProfile(candidate)
    except ValueError:
        return RuntimeProfile.DEV_LOCAL_ACP_BRIDGE


def runtime_target_for_work_mode(work_mode: WorkMode) -> RuntimeTarget:
    if work_mode == WorkMode.CLOUD_SANDBOX:
        return RuntimeTarget.CLOUD_RUNTIME
    return RuntimeTarget.LOCAL_RUNTIME


def interaction_surface_for_work_mode(work_mode: WorkMode) -> InteractionSurface:
    if work_mode == WorkMode.WECLAW_DISPATCH:
        return InteractionSurface.WECLAW
    return InteractionSurface.ELECTRON_HOME


def execution_plane_for_runtime_target(runtime_target: RuntimeTarget) -> ExecutionPlane:
    if runtime_target == RuntimeTarget.CLOUD_RUNTIME:
        return ExecutionPlane.CLOUD_EXECUTOR
    return ExecutionPlane.LOCAL_EXECUTOR


def local_runtime_seat_for_runtime(
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


def _coerce_work_mode_value(value: Any, *, default: WorkMode = WorkMode.CLOUD_SANDBOX) -> WorkMode:
    try:
        if isinstance(value, WorkMode):
            return value
        if isinstance(value, str) and value.strip():
            return WorkMode(value.strip())
    except ValueError:
        pass
    return default


def _coerce_runtime_profile_value(
    value: Any,
    *,
    default: Optional[RuntimeProfile] = None,
) -> RuntimeProfile:
    fallback = default or default_runtime_profile()
    try:
        if isinstance(value, RuntimeProfile):
            return value
        if isinstance(value, str) and value.strip():
            return RuntimeProfile(value.strip())
    except ValueError:
        pass
    return fallback


def _coerce_runtime_target_value(
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


def _coerce_interaction_surface_value(
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


def _coerce_model_plane_value(
    value: Any,
    *,
    default: ModelPlane = ModelPlane.CLOUD_PROVIDER,
) -> ModelPlane:
    try:
        if isinstance(value, ModelPlane):
            return value
        if isinstance(value, str) and value.strip():
            return ModelPlane(value.strip())
    except ValueError:
        pass
    return default


def _coerce_execution_plane_value(
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


def _coerce_local_runtime_seat_value(
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


class Session(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str
    canonical_id: str
    channel: str
    user_id: Optional[str] = None
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str
    capability: str
    session_id: Optional[str] = None
    channel: Optional[str] = None
    status: TaskStatus = TaskStatus.QUEUED
    input: dict[str, Any] = Field(default_factory=dict)
    work_mode: WorkMode = WorkMode.CLOUD_SANDBOX
    origin_surface: Optional[str] = None
    interaction_surface: InteractionSurface = InteractionSurface.ELECTRON_HOME
    runtime_profile: RuntimeProfile = Field(default_factory=default_runtime_profile)
    runtime_target: RuntimeTarget = RuntimeTarget.CLOUD_RUNTIME
    model_plane: ModelPlane = ModelPlane.CLOUD_PROVIDER
    local_runtime_seat: LocalRuntimeSeat = LocalRuntimeSeat.UNAVAILABLE
    execution_plane: ExecutionPlane = ExecutionPlane.CLOUD_EXECUTOR
    run_ids: list[str] = Field(default_factory=list)
    last_run_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _sync_mode_fields(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        metadata = dict(data.get("metadata") or {})
        raw_work_mode = data.get("work_mode") or metadata.get("work_mode")
        if not raw_work_mode and str(data.get("execution_plane") or metadata.get("execution_plane") or "").strip() == "weclaw_dispatch":
            raw_work_mode = WorkMode.WECLAW_DISPATCH.value
        work_mode = _coerce_work_mode_value(raw_work_mode)
        runtime_target = _coerce_runtime_target_value(
            data.get("runtime_target") or metadata.get("runtime_target") or data.get("execution_plane") or metadata.get("execution_plane"),
            default=runtime_target_for_work_mode(work_mode),
        )
        interaction_surface = _coerce_interaction_surface_value(
            data.get("interaction_surface")
            or metadata.get("interaction_surface")
            or data.get("origin_surface")
            or metadata.get("origin_surface")
            or metadata.get("launch_surface"),
            default=interaction_surface_for_work_mode(work_mode),
        )
        runtime_profile = _coerce_runtime_profile_value(
            data.get("runtime_profile") or metadata.get("runtime_profile")
        )
        model_plane = _coerce_model_plane_value(
            data.get("model_plane") or metadata.get("model_plane")
        )
        local_runtime_seat = _coerce_local_runtime_seat_value(
            data.get("local_runtime_seat") or metadata.get("local_runtime_seat"),
            default=local_runtime_seat_for_runtime(runtime_target, runtime_profile),
        )
        execution_plane = _coerce_execution_plane_value(
            data.get("execution_plane") or metadata.get("execution_plane"),
            default=execution_plane_for_runtime_target(runtime_target),
        )
        data["work_mode"] = work_mode.value
        data["interaction_surface"] = interaction_surface.value
        data["runtime_profile"] = runtime_profile.value
        data["runtime_target"] = runtime_target.value
        data["model_plane"] = model_plane.value
        data["local_runtime_seat"] = local_runtime_seat.value
        data["execution_plane"] = execution_plane.value
        data["origin_surface"] = (
            str(data.get("origin_surface") or metadata.get("origin_surface") or metadata.get("launch_surface") or interaction_surface.value)
            or None
        )
        return data


class Run(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    domain: str
    capability: str
    status: RunStatus = RunStatus.QUEUED
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    requested_by: Optional[str] = None
    work_mode: WorkMode = WorkMode.CLOUD_SANDBOX
    origin_surface: Optional[str] = None
    interaction_surface: InteractionSurface = InteractionSurface.ELECTRON_HOME
    runtime_profile: RuntimeProfile = Field(default_factory=default_runtime_profile)
    runtime_target: RuntimeTarget = RuntimeTarget.CLOUD_RUNTIME
    model_plane: ModelPlane = ModelPlane.CLOUD_PROVIDER
    local_runtime_seat: LocalRuntimeSeat = LocalRuntimeSeat.UNAVAILABLE
    execution_plane: ExecutionPlane = ExecutionPlane.CLOUD_EXECUTOR
    summary: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _sync_mode_fields(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        metadata = dict(data.get("metadata") or {})
        raw_work_mode = data.get("work_mode") or metadata.get("work_mode")
        if not raw_work_mode and str(data.get("execution_plane") or metadata.get("execution_plane") or "").strip() == "weclaw_dispatch":
            raw_work_mode = WorkMode.WECLAW_DISPATCH.value
        work_mode = _coerce_work_mode_value(raw_work_mode)
        runtime_target = _coerce_runtime_target_value(
            data.get("runtime_target") or metadata.get("runtime_target") or data.get("execution_plane") or metadata.get("execution_plane"),
            default=runtime_target_for_work_mode(work_mode),
        )
        interaction_surface = _coerce_interaction_surface_value(
            data.get("interaction_surface")
            or metadata.get("interaction_surface")
            or data.get("origin_surface")
            or metadata.get("origin_surface")
            or metadata.get("launch_surface"),
            default=interaction_surface_for_work_mode(work_mode),
        )
        runtime_profile = _coerce_runtime_profile_value(
            data.get("runtime_profile") or metadata.get("runtime_profile")
        )
        model_plane = _coerce_model_plane_value(
            data.get("model_plane") or metadata.get("model_plane")
        )
        local_runtime_seat = _coerce_local_runtime_seat_value(
            data.get("local_runtime_seat") or metadata.get("local_runtime_seat"),
            default=local_runtime_seat_for_runtime(runtime_target, runtime_profile),
        )
        execution_plane = _coerce_execution_plane_value(
            data.get("execution_plane") or metadata.get("execution_plane"),
            default=execution_plane_for_runtime_target(runtime_target),
        )
        data["work_mode"] = work_mode.value
        data["interaction_surface"] = interaction_surface.value
        data["runtime_profile"] = runtime_profile.value
        data["runtime_target"] = runtime_target.value
        data["model_plane"] = model_plane.value
        data["local_runtime_seat"] = local_runtime_seat.value
        data["execution_plane"] = execution_plane.value
        data["origin_surface"] = (
            str(data.get("origin_surface") or metadata.get("origin_surface") or metadata.get("launch_surface") or interaction_surface.value)
            or None
        )
        return data


class Artifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    artifact_id: str
    run_id: str
    kind: str
    uri: str
    title: str = ""
    mime_type: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Approval(BaseModel):
    model_config = ConfigDict(extra="allow")

    approval_id: str
    run_id: str
    kind: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_by: Optional[str] = None
    requested_at: datetime = Field(default_factory=utc_now)
    decided_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliveryPolicy(BaseModel):
    model_config = ConfigDict(extra="allow")

    policy_id: str = "default"
    live_reply_channel: Optional[str] = None
    preferred_channels: list[str] = Field(default_factory=list)
    fallback_channels: list[str] = Field(default_factory=list)
    windowed_proactive: bool = False
    desktop_fallback: bool = True
    requires_approval: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    memory_id: str
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    plane: MemoryPlane = MemoryPlane.RAW
    source: str
    target: str
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    review_id: str
    run_id: str
    decision: ReviewDecisionStatus = ReviewDecisionStatus.PENDING
    reviewer: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    decided_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DomainCapability(BaseModel):
    model_config = ConfigDict(extra="allow")

    capability_id: str
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalSuiteDescriptor(BaseModel):
    model_config = ConfigDict(extra="allow")

    suite_id: str
    name: str
    description: str
    command: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperatorAction(BaseModel):
    model_config = ConfigDict(extra="allow")

    action_id: str
    run_id: str
    kind: str
    label: str
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DomainPackDescriptor(BaseModel):
    model_config = ConfigDict(extra="allow")

    pack_id: str
    domain: str
    version: str
    owner_repo: str
    runtime: str
    description: str
    capabilities: list[DomainCapability] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DomainPackHealth(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = "ok"
    checks: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utc_now)


class AdapterDescriptor(BaseModel):
    model_config = ConfigDict(extra="allow")

    adapter_id: str
    channel: str
    owner_repo: str
    description: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class InboundEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    channel: str
    channel_user_id: str
    text: Optional[str] = None
    session_hint: Optional[str] = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    delivery_policy: DeliveryPolicy = Field(default_factory=DeliveryPolicy)
    occurred_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LaunchMention(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: str
    value: str
    label: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LaunchIntent(BaseModel):
    model_config = ConfigDict(extra="allow")

    launch_id: str = Field(default_factory=lambda: f"launch-{utc_now().strftime('%Y%m%d%H%M%S')}-{utc_now().microsecond:06d}")
    source: str
    raw_text: str
    mentions: list[LaunchMention] = Field(default_factory=list)
    requested_outcome: Optional[str] = None
    work_mode: WorkMode = WorkMode.CLOUD_SANDBOX
    launch_surface: Optional[str] = None
    interaction_surface: InteractionSurface = InteractionSurface.ELECTRON_HOME
    runtime_profile: RuntimeProfile = Field(default_factory=default_runtime_profile)
    runtime_target: RuntimeTarget = RuntimeTarget.CLOUD_RUNTIME
    model_plane: ModelPlane = ModelPlane.CLOUD_PROVIDER
    local_runtime_seat: LocalRuntimeSeat = LocalRuntimeSeat.UNAVAILABLE
    workspace_target: Optional[str] = None
    session_context: dict[str, Any] = Field(default_factory=dict)
    delivery_preference: DeliveryPolicy = Field(default_factory=DeliveryPolicy)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _sync_launch_fields(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        metadata = dict(data.get("metadata") or {})
        session_context = dict(data.get("session_context") or {})
        raw_work_mode = data.get("work_mode") or metadata.get("work_mode") or session_context.get("work_mode")
        if not raw_work_mode and str(metadata.get("execution_plane") or "").strip() == "weclaw_dispatch":
            raw_work_mode = WorkMode.WECLAW_DISPATCH.value
        work_mode = _coerce_work_mode_value(
            raw_work_mode,
            default=WorkMode.WECLAW_DISPATCH if str(data.get("source") or "").strip() == "weclaw" else WorkMode.CLOUD_SANDBOX,
        )
        interaction_surface = _coerce_interaction_surface_value(
            data.get("interaction_surface")
            or metadata.get("interaction_surface")
            or data.get("launch_surface")
            or metadata.get("launch_surface")
            or metadata.get("origin_surface")
            or session_context.get("interaction_surface")
            or data.get("source"),
            default=interaction_surface_for_work_mode(work_mode),
        )
        runtime_profile = _coerce_runtime_profile_value(
            data.get("runtime_profile")
            or metadata.get("runtime_profile")
            or session_context.get("runtime_profile")
        )
        runtime_target = _coerce_runtime_target_value(
            data.get("runtime_target")
            or metadata.get("runtime_target")
            or metadata.get("execution_plane"),
            default=runtime_target_for_work_mode(work_mode),
        )
        model_plane = _coerce_model_plane_value(
            data.get("model_plane") or metadata.get("model_plane") or session_context.get("model_plane")
        )
        local_runtime_seat = _coerce_local_runtime_seat_value(
            data.get("local_runtime_seat")
            or metadata.get("local_runtime_seat")
            or session_context.get("local_runtime_seat"),
            default=local_runtime_seat_for_runtime(runtime_target, runtime_profile),
        )
        data["work_mode"] = work_mode.value
        data["interaction_surface"] = interaction_surface.value
        data["runtime_profile"] = runtime_profile.value
        data["runtime_target"] = runtime_target.value
        data["model_plane"] = model_plane.value
        data["local_runtime_seat"] = local_runtime_seat.value
        if not data.get("launch_surface"):
            launch_surface = metadata.get("launch_surface") or metadata.get("origin_surface") or interaction_surface.value
            if launch_surface:
                data["launch_surface"] = launch_surface
        if not data.get("workspace_target"):
            workspace_target = metadata.get("workspace_target") or session_context.get("workspace_root")
            if workspace_target:
                data["workspace_target"] = workspace_target
        return data


class DomainRunRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    capability: str
    input: dict[str, Any] = Field(default_factory=dict)
    session: Optional[Session] = None
    task: Optional[Task] = None
    delivery_policy: DeliveryPolicy = Field(default_factory=DeliveryPolicy)
    requested_by: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DomainRunResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    run: Run
    artifacts: list[Artifact] = Field(default_factory=list)
    approvals: list[Approval] = Field(default_factory=list)
    review_actions: list[OperatorAction] = Field(default_factory=list)
    memory_records: list[MemoryRecord] = Field(default_factory=list)


class LaunchReceipt(BaseModel):
    model_config = ConfigDict(extra="allow")

    launch_id: str
    pack_id: str
    task: Task
    run: Run
    artifacts: list[Artifact] = Field(default_factory=list)
    review_actions: list[OperatorAction] = Field(default_factory=list)
    work_items: list[dict[str, Any]] = Field(default_factory=list)
    compiled_input: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlPlaneRunView(BaseModel):
    model_config = ConfigDict(extra="allow")

    run: Run
    artifacts: list[Artifact] = Field(default_factory=list)
    approvals: list[Approval] = Field(default_factory=list)
    reviews: list[ReviewDecision] = Field(default_factory=list)
    operator_actions: list[OperatorAction] = Field(default_factory=list)


@runtime_checkable
class DomainPack(Protocol):
    def describe(self) -> DomainPackDescriptor | Mapping[str, Any]:
        ...

    def health(self) -> DomainPackHealth | Mapping[str, Any]:
        ...

    def capabilities(self) -> list[DomainCapability] | list[Mapping[str, Any]]:
        ...

    async def run(
        self, request: DomainRunRequest | Mapping[str, Any]
    ) -> DomainRunResult | Mapping[str, Any]:
        ...

    async def list_artifacts(
        self, run_id: str
    ) -> list[Artifact] | list[Mapping[str, Any]]:
        ...

    async def review_actions(
        self, run_id: str
    ) -> list[OperatorAction] | list[Mapping[str, Any]]:
        ...

    def eval_suite(self) -> list[EvalSuiteDescriptor] | list[Mapping[str, Any]]:
        ...


@runtime_checkable
class InteractionAdapter(Protocol):
    def describe(self) -> AdapterDescriptor | Mapping[str, Any]:
        ...

    async def ingest(self, event: InboundEvent | Mapping[str, Any]) -> Session | Mapping[str, Any]:
        ...

    async def deliver(
        self,
        run: Run | Mapping[str, Any],
        policy: DeliveryPolicy | Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...


class DomainPackRegistry:
    def __init__(self) -> None:
        self._packs: dict[str, DomainPack] = {}
        self._descriptors: dict[str, DomainPackDescriptor] = {}

    def register(
        self,
        pack_id: str,
        pack: DomainPack,
        descriptor: DomainPackDescriptor | Mapping[str, Any] | None = None,
    ) -> None:
        if pack_id in self._packs:
            raise ValueError(f"Domain pack already registered: {pack_id}")
        normalized = DomainPackDescriptor.model_validate(descriptor or pack.describe())
        self._packs[pack_id] = pack
        self._descriptors[pack_id] = normalized

    def get(self, pack_id: str) -> DomainPack:
        return self._packs[pack_id]

    def has(self, pack_id: str) -> bool:
        return pack_id in self._packs

    def list_descriptors(self) -> list[DomainPackDescriptor]:
        return sorted(self._descriptors.values(), key=lambda descriptor: descriptor.pack_id)

    def items(self) -> list[tuple[str, DomainPack]]:
        return sorted(self._packs.items(), key=lambda item: item[0])


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, InteractionAdapter] = {}
        self._descriptors: dict[str, AdapterDescriptor] = {}

    def register(
        self,
        adapter_id: str,
        adapter: InteractionAdapter,
        descriptor: AdapterDescriptor | Mapping[str, Any] | None = None,
    ) -> None:
        if adapter_id in self._adapters:
            raise ValueError(f"Adapter already registered: {adapter_id}")
        normalized = AdapterDescriptor.model_validate(descriptor or adapter.describe())
        self._adapters[adapter_id] = adapter
        self._descriptors[adapter_id] = normalized

    def get(self, adapter_id: str) -> InteractionAdapter:
        return self._adapters[adapter_id]

    def has(self, adapter_id: str) -> bool:
        return adapter_id in self._adapters

    def by_channel(self, channel: str) -> list[InteractionAdapter]:
        return [
            adapter
            for adapter_id, adapter in sorted(self._adapters.items())
            if self._descriptors[adapter_id].channel == channel
        ]

    def list_descriptors(self, channel: str | None = None) -> list[AdapterDescriptor]:
        descriptors = self._descriptors.values()
        if channel is not None:
            descriptors = [
                descriptor
                for descriptor in descriptors
                if descriptor.channel == channel
            ]
        return sorted(descriptors, key=lambda descriptor: descriptor.adapter_id)
