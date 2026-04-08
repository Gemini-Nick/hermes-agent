# Longclaw Product Roadmap

This roadmap describes how Longclaw moves from a local-first personal stack into a distributable product built around a Hermes-like core, with a built-in `Harness Engineering Loop` that enables a real self-improving agent.

## Concept Goal

- `Hermes-like Agent Core（云侧）` is the target runtime architecture.
- `Harness Engineering Loop` is the mechanism that improves behavior and promotes validated changes.
- `Self-improving agent` is the product outcome that users should feel.

## Phase 0

### `Local-first Reference System（现在）`

Primary shape:

- `longclaw-agent-os` drives the device-side runtime
- `weclaw` handles WeChat semantics and bridge behavior
- Obsidian remains the main human review surface
- `guardian / watchdog / harness` are still partly local-first subsystems

Goal:

- prove product workflows and boundaries without prematurely rewriting everything

## Phase 1

### `Umbrella Repo Consolidation`

Primary shape:

- this `hermes-agent` fork becomes the product-level umbrella repo
- architecture, repo map, and extraction targets are documented here
- upstream Hermes remains the runtime foundation

Goal:

- make the future product path explicit
- move the source of truth for product architecture out of any single device-side repository

## Phase 2

### `Harness Engineering Convergence`

Primary shape:

- portable pieces of `watchdog` and `harness` move toward the core runtime
- learning is no longer described as a separate runtime
- `session / memory / skills / scheduler` become first-class extraction targets
- `user model` and `Harness Engineering Loop` become explicit core concerns

Goal:

- turn `harness` from an attached subsystem into a closed improvement loop:
  - ingest
  - evaluate
  - regress
  - promote
  - deliver

## Phase 3

### `Distributed Product Architecture`

Primary shape:

- `Agent Core（云侧）` becomes the main product core
- `Client Runtime（端侧）` becomes thinner and more portable
- `Interaction Adapter Layer（通道侧）` supports multiple channels consistently
- `Knowledge Review Plane（知识侧）` remains a review and audit surface rather than the only machine state source

Goal:

- support Mac, mobile, glasses, and cloud deployments against one shared core

## Near-term Priorities

- keep `longclaw-agent-os` stable as the current `Client Runtime（端侧）`
- keep `weclaw` and `Chanless` as adapters, not product-core repos
- stop treating `learning runtime` as an independent top-level architecture bucket
- define the improvement loop as `Harness Engineering` inside the core

## North Star

Longclaw should end up closer to a Hermes-style runtime than to a permanent local service mesh:

- one core for sessions, memory, skills, scheduling, user model, and the `Harness Engineering Loop`
- thin clients and adapters
- explicit review and intervention surfaces
- a built-in harness engineering loop that keeps improving the agent from real usage
