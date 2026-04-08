# Longclaw Repo Map

This fork is the product-level umbrella repository. The repositories below are classified against the canonical Longclaw architecture.

## Concept Boundaries

- `Hermes-like Agent Core（云侧）` is the target runtime shape.
- `Self-improving agent` is the user-facing product capability.
- `Harness Engineering Loop` is the internal evaluation and promotion loop inside the core.

That means `self-improving agent` is not a separate repository or layer. It is the behavior produced when the core and the improvement loop are working together.

## Primary Mapping

| Repository or artifact | Current classification | Role |
| --- | --- | --- |
| `hermes-agent` | `Agent Core（云侧）` umbrella and future base | Product-level umbrella repo, architecture source of truth, and future portable runtime base |
| `longclaw-agent-os` | `Client Runtime（端侧）` | Current device-side reference implementation for install/upgrade, launchd/runtime orchestration, desktop shell, and local recovery |
| `weclaw` | `Interaction Adapter Layer（通道侧）` | WeChat bridge core: message semantics, media handling, transcript-first flow, session/media facts, archive contracts |
| `Chanless` | `Interaction Adapter Layer（通道侧）` | Voice input and local voice routing adapter with stronger device-side coupling |
| `Signals` | `Agent Core（云侧）` adjacent domain engine | Financial analysis engine and callable business-domain capability |
| Obsidian knowledge base | `Knowledge Review Plane（知识侧）` | Inbox, promotion, review, and long-term human-readable knowledge projection |

## Internal Sub-systems

| Sub-system | Current classification | Long-term direction |
| --- | --- | --- |
| `guardian` | `Client Runtime（端侧）` substrate | Remains a device-side supervision layer instead of a portable core concern |
| `watchdog` | Transitional, currently closer to `Client Runtime（端侧）` | Portable scheduling and orchestration logic should move into `Agent Core（云侧）` |
| `harness` | Transitional, currently split across local workflows | Becomes the evaluation, regression, and promotion loop inside `Agent Core（云侧）` |
| `learning runtime` | Do not keep as a top-level product name | Fold into `user model + skills + Harness Engineering Loop` inside `Agent Core（云侧）` |

## Guiding Rules

- `Client Runtime（端侧）` owns device-local integration, recovery, packaging, and UX.
- `Agent Core（云侧）` owns portable state and core agent behavior.
- `Interaction Adapter Layer（通道侧）` owns protocol translation, identity, and transport.
- `Knowledge Review Plane（知识侧）` owns reviewability, intervention, evidence, and human-readable projection.

## Practical Interpretation

Near term:

- `longclaw-agent-os` stays operationally central for personal use.
- `hermes-agent` becomes the place where the product architecture is defined.

Long term:

- `hermes-agent` should become the main product core.
- `longclaw-agent-os` should become one concrete client/runtime implementation rather than the architectural center of gravity.
