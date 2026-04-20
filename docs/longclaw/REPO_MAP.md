# Longclaw Repo Map

This is the canonical repo map for the Longclaw Agent OS. Other repos should
point here instead of re-describing the architecture in incompatible ways.

## Product Objective

- One `Agent Core（云侧）` owns `session / memory / skills / scheduler / delivery / approvals / eval`.
- Two connected front doors launch work:
  - `Electron Home`
  - `WeClaw`
- One governance center owns `runs / artifacts / evidence / review / work items / promotion`.
- One curated `Capability Substrate` exposes `skills / plugins / bundled skills / built-in plugins / cowork runtime`.
- Multiple flagship packs form the `Professional Grounds`.
- One reviewed knowledge plane receives promoted outputs only.

## Canonical Mapping

| Repository or artifact | Classification | Role |
| --- | --- | --- |
| `hermes-agent` | `Agent Core（云侧）` | Portable runtime base, `LaunchIntent` compiler, routing, delivery policy, approvals, memory promotion, evaluation gates, pack orchestration |
| `longclaw-agent-os` | `Client Runtime（端侧）` + default home + `Capability Substrate` host | `Home / Runs / Work Items / Packs / Studio`, local shell, reliable local delivery, capability curation, guardian/recovery flows |
| `weclaw` | `Interaction Adapter Layer（通道侧）` + remote cowork companion | WeChat bridge core, remote launch, lightweight status follow-up, message semantics, media transport, canonical agent input |
| `Chanless` | `Interaction Adapter Layer（通道侧）` | Optional voice ingress and device-coupled voice routing |
| `Signals` | Flagship `Domain Pack` + `Professional Ground` | Financial specialist workspace: review, backtest, connector health, output artifacts |
| `due-diligence-core` | Flagship `Domain Pack` + `Professional Ground` | Due-diligence cloud execution runtime: evidence, manual review, repair, site health, export logic |
| `mempalace-sync` | `Memory Ingestion Utility` | Raw/verbatim memory ingestion path into MemPalace; not a product shell |
| `MemPalace` | `Raw Memory Plane` | Raw memory, weekly reports, operational notes, verbatim records |
| `Obsidian` knowledge base | `Reviewed Knowledge Plane` | Reviewed knowledge only: promoted insights, playbooks, final decisions, stable operator-facing knowledge |
| `gstack` | `Internal Workflow Framework` | Planning, review, QA, retro, and release workflows; not a runtime dependency |
| `superpowers` | `Internal Workflow / Operator Tooling` | Internal workflows and operator leverage; not part of the product runtime boundary |

## Front-Door Rule

Longclaw follows one product rule:

- `Chat launches, console governs.`

That means:

- `Electron Home` and `WeClaw` may initiate work.
- Hermes compiles launch requests into canonical runtime objects.
- All side-effectful, long-running, reviewable, or evidence-generating work lands in governance surfaces.

## Explicit Non-Migrations

These boundaries are frozen for phase 1:

- Do not move `weclaw` message semantics into `hermes-agent` or `longclaw-agent-os`.
- Do not rewrite the `Signals` analysis engine inside the core.
- Do not move `due-diligence-core` site adapters, challenge logic, or export parity logic into the desktop client.
- Do not turn `mempalace-sync` into a product runtime.
- Do not pull `gstack` or `superpowers` into the shipped runtime dependency graph.
- Do not turn `Studio` into an open marketplace before the curated capability set is stable.

## Internal Sub-systems

| Sub-system | Current classification | Long-term direction |
| --- | --- | --- |
| `guardian` | `Client Runtime（端侧）` substrate | Device-side supervision, installation, and recovery stays local |
| `watchdog` | Transitional | Portable scheduling/routing logic moves toward `hermes-agent` |
| `harness` | Transitional | Formalized into evaluation, shadow compare, and promotion gates inside the core |
| `learning runtime` | Transitional name only | Fold into `memory ingress + user model + eval/promotion loop` |

## Contract Surfaces

`hermes-agent` is the source of truth for:

- canonical `LaunchIntent`, `Session`, `Task`, `Run`, `Artifact`, `Approval`, `DeliveryPolicy`, `MemoryRecord`, and `ReviewDecision`
- `DomainPack` and `InteractionAdapter` contracts
- domain pack registry and adapter registry

`longclaw-agent-os` consumes those contracts and should not redefine pack state machines.

## Design Ownership

`hermes-agent/docs/longclaw/DESIGN.md` is the canonical product design source
for Longclaw.

- `longclaw-agent-os` implements the default home and governance surfaces using that design system.
- `Signals`, `WeClaw`, and `Obsidian` inherit the same terminology, state semantics, and visual hierarchy constraints.
- No downstream repo should fork a second brand language for phase 1.

## Practical Interpretation

Near term:

- `hermes-agent` becomes the architectural center of gravity.
- `longclaw-agent-os` becomes the default home plus governance console.
- `WeClaw` becomes the remote cowork companion, not a desktop substitute.
- `Signals` and `due-diligence-core` are integrated as flagship packs and `Professional Grounds`.
- `Obsidian` stays reviewed-only.

Long term:

- the same `Agent Core（云侧）` should serve desktop, WeChat, voice, and future mobile/cloud surfaces
- new domains should look like new domain packs, not new top-level architectures
- the capability substrate should remain curated even as the ecosystem expands
