# Longclaw Product Roadmap

This roadmap describes how Longclaw moves from a local-first personal stack
into a coherent Agent OS with two connected front doors, one governance center,
curated capabilities, flagship professional grounds, and a reviewed knowledge
plane.

## Concept Goal

- `Agent Core（云侧）` remains the target runtime architecture.
- `Harness Engineering Loop` remains the mechanism that improves behavior and promotes validated changes.
- `Chat launches, console governs` becomes the product rule that organizes all surfaces.

## Phase 0

### `Product Reframe（现在）`

Primary shape:

- `Electron` becomes the explicit default home
- `Overview` is replaced by `Home`
- `Home` combines `Cowork Launch` and `Governance Snapshot`
- `WeClaw` is formalized as the remote cowork companion
- `Signals` and `due-diligence-core` are formalized as flagship packs in the `Professional Grounds`
- `Obsidian` is reduced to the reviewed knowledge plane only

Goal:

- replace the old `desktop shell / pure control plane` narrative with the new product structure
- lock canonical terminology before broader implementation drifts

## Phase 1

### `Front Door Convergence`

Primary shape:

- `Electron Home` and `WeClaw` both launch work
- Hermes introduces canonical `LaunchIntent`
- `LaunchIntent` compiles into `Task / Run / Work Item`
- side-effectful and evidence-heavy work always lands in governance surfaces

Goal:

- make launch feel natural without letting chat become the system of record
- keep one canonical path from launch into governance

## Phase 2

### `Governance Console Stabilization`

Primary shape:

- `Runs`
- `Work Items`
- `Packs`
- shared detail drawer
- consistent evidence, review, retry, and delivery surfaces

Goal:

- make governance legible, reviewable, and durable
- ensure failures, partials, and delivery fallbacks never disappear into chat

## Phase 3

### `Professional Grounds Productization`

Primary shape:

- `Signals` becomes the financial professional ground
- `due-diligence-core` becomes the due-diligence professional ground
- pack-specific launch shortcuts, review state, and operator actions are exposed through Longclaw surfaces

Goal:

- keep specialist depth in flagship packs without turning them into second home screens
- make specialist work feel native to Longclaw without flattening domain semantics

## Phase 4

### `Capability Studio Curation`

Primary shape:

- `Studio` manages curated:
  - plugins
  - skills
  - aliases
  - presets
  - flagship pack entrypoints
- marketplace-first storytelling remains out of scope

Goal:

- expose the `Capability Substrate` without turning Longclaw into a plugin mall

## Phase 5

### `Reviewed Promotion Loop`

Primary shape:

- governance and professional grounds produce reviewed outputs
- reviewed handoff promotes into `Obsidian`
- raw logs, raw chat, and unreviewed evidence stay out of the reviewed plane

Goal:

- complete the `launch -> run -> review -> promotion -> knowledge` loop

## Near-term Priorities

- keep `longclaw-agent-os` stable as the current default home and `Client Runtime（端侧）`
- keep `weclaw` and `Chanless` as adapters, not product-core repos
- formalize `LaunchIntent`
- formalize `Capability Substrate` and `Professional Grounds`
- formalize WeChat as `windowed proactive` plus pull-based entrypoints like `任务:` and `/runtime`
- make `reliable_local` delivery the default guarantee for governance and reviewed handoff outputs

## North Star

Longclaw should end up as:

- one core for sessions, memory, skills, scheduling, delivery, approvals, and the `Harness Engineering Loop`
- one default home that combines launch and governance
- thin companion adapters rather than competing product shells
- flagship professional grounds rather than generic plugin demos
- reviewed knowledge promotion rather than raw archive sprawl
