# Design System — Longclaw Agent OS

## Product Context
- **What this is:** Longclaw is an Agent OS for a single high-leverage operator. It combines a `Cowork Front Door` for launching work, a `Governance Console` for supervising runs and evidence, and a `Reviewed Knowledge Plane` for promoted outputs.
- **Who it's for:** One high-context operator who moves between WeChat, a desktop home base, specialist financial and due-diligence work, and durable knowledge capture.
- **Core principle:** `Chat launches, console governs.`
- **Project type:** Electron-first product shell with companion surfaces and cloud-side orchestration.

## Product Structure
- `Electron` is the default home.
- `Home` is the new landing surface. It replaces `Overview`.
- `Home` is now a `chat-first workspace`.
- `Home` always combines:
  - a central conversation transcript
  - a sticky launch composer
  - a shared task ledger backdrop through threads, receipts, and detail drawers
- `Runs`, `Work Items`, and `Packs` remain governance-first surfaces.
- `Studio` is a capability curation surface, not a marketplace home screen.
- `WeClaw` is the remote cowork companion.
- `Signals` and `due-diligence-core` are flagship packs inside the `Professional Grounds`.
- `Obsidian` is the reviewed knowledge plane, not a runtime inbox.

## Design North Star
- **Direction:** `Warm Industrial Command Center`
- **Decoration level:** `intentional`
- **Mood:** Calm, capable, evidence-driven. It should feel like a serious operator's desk, not a generic SaaS dashboard and not a glowing cyberpunk AI toy.
- **Promise:** The interface should make five things obvious:
  - what can be launched right now
  - what is currently running
  - what needs intervention
  - what evidence exists
  - what has been promoted into reviewed knowledge

## Borrow Strategy
These products inform the design language and interaction patterns, not the product center of gravity.

| Reference | Why It Matters | Borrow | Do Not Borrow |
| --- | --- | --- | --- |
| `langflow-ai/langflow` | Strong graph literacy and tool organization | clear object modeling, tool palette discipline | canvas-first home screen |
| `open-webui/open-webui` | Mature AI workspace conventions | capability visibility, context awareness, session framing | chat-first product gravity |
| `browser-use/browser-use` | Browser execution as a visible runtime | evidence presence, execution visibility, live task feel | turning browser automation into the brand center |
| `All-Hands-AI/OpenHands` | Agent cockpit logic | operator posture, execution detail hierarchy | coding-first tone and IDE-heavy density |
| `FlowiseAI/Flowise` | Visual workflow clarity | explicit workflow object language | node editor as the primary experience |
| `Claude Cowork / WorkBuddy / cowork products` | Better launch experience and capability surfacing | launch composer, active capability chips, recent launch feedback | full-screen chat home, marketplace-first storytelling |

## Surface Hierarchy
- `Electron` is the only default home.
- `WeClaw` is a remote cowork companion for launch, status checks, and lightweight follow-up.
- `Signals` and `due-diligence-core` are flagship packs under `Packs`, not second home screens.
- `Studio` is where curated capabilities are surfaced and adjusted.
- `Obsidian` receives reviewed outputs only.

## Aesthetic Direction
- **Primary aesthetic:** industrial / utilitarian with editorial tension
- **Core materials:** warm paper, slate structure, copper emphasis, muted teal system accents
- **Texture policy:** subtle grain or tonal wash is allowed; decorative blobs, neon glows, and noisy gradients are banned
- **Radius policy:** hierarchy matters
  - `sm`: `8px`
  - `md`: `12px`
  - `lg`: `18px`
  - `pill`: `999px`
- **Shadow policy:** shallow and structural, never puffy

## Typography
### Primary Typefaces
- **Display / Section Headings:** `Instrument Serif`
- **Body / Navigation / UI Labels:** `Instrument Sans`
- **Data / Tables / IDs / Paths:** `IBM Plex Mono`

### Fallback Chains
- **Display:** `"Instrument Serif", "Noto Serif SC", "Source Han Serif SC", "Songti SC", serif`
- **UI:** `"Instrument Sans", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif`
- **Mono:** `"IBM Plex Mono", "SFMono-Regular", "Menlo", "Consolas", monospace`

### Type Rules
- Use serif only for product-defining headings, pack titles, and decision moments.
- Use sans for all workflow UI.
- Use mono anywhere the operator benefits from visual precision: run IDs, timestamps, status payloads, paths, tabular metrics.
- Enable tabular numerals in every metric or table surface.
- Never use `Inter`, `Roboto`, `Arial`, `Helvetica`, or other default system stacks as the primary design choice.

### Type Scale
- `display-xl`: `36px / 1.05 / 600`
- `display-lg`: `30px / 1.1 / 600`
- `title-md`: `20px / 1.2 / 600`
- `title-sm`: `16px / 1.25 / 600`
- `body-md`: `14px / 1.5 / 450`
- `body-sm`: `12px / 1.45 / 450`
- `mono-sm`: `12px / 1.45 / 500`

## Color System
### Core Tokens
| Token | Value | Use |
| --- | --- | --- |
| `paper` | `#F7F2E8` | primary canvas |
| `stone` | `#E7DDCC` | secondary canvas, strips, capability rails |
| `panel` | `#F0E6D7` | panel fill |
| `panel-raised` | `#FBF7F0` | raised panel fill |
| `ink` | `#171A1F` | primary text |
| `slate` | `#2C3440` | sidebar, drawer chrome, inspection surfaces |
| `slate-soft` | `#4C5866` | secondary dark accents |
| `copper` | `#B8643B` | product accent |
| `teal` | `#2C7A78` | active capability / running / connected states |

### Semantic Tokens
| Token | Value | Use |
| --- | --- | --- |
| `success` | `#2E8B57` | approved, succeeded, healthy |
| `warning` | `#C7922F` | needs review, partial, degraded |
| `error` | `#C84F44` | failed, repair required, delivery failed |
| `info` | `#4C5866` | neutral supporting status |

### Color Rules
- Brand color is `copper`, not blue and not violet.
- Status color is semantic, never brand.
- State communication must never rely on color alone. Every state also needs text, badge label, or iconography.
- Launch surfaces may feel lighter and faster than governance surfaces, but they must still belong to the same industrial system.
- Dark mode is not a phase 1 requirement.

## Spacing And Density
- **Base unit:** `4px`
- **Primary rhythm:** `8 / 12 / 16 / 24 / 32`
- **Density target:** compact, not cramped
- **Principle:** this is a work surface. Favor readable density over marketing whitespace.

## Layout
### Canonical Shell
- left rail: `72px-80px`
- thread sidebar: `280px-320px`
- central workspace: flexible main plane
- right detail drawer: `380px-420px`

### Breakpoints
- `wide >= 1360px`: rail + thread sidebar + main workspace + detail drawer
- `mid 1080px-1359px`: detail drawer becomes overlay while the two left columns stay visible
- `narrow < 1080px`: thread sidebar becomes collapsible and detail drawer overlays

### Navigation Rules
- Primary navigation is:
  - `Home`
  - `Runs`
  - `Work Items`
  - `Packs`
  - `Studio`
- `Home` is the chat-first landing surface for launch and task continuity.
- `Runs` and `Work Items` are list-driven first, drawer-driven second.
- `Packs` are deep work entry points, not alternative home screens.
- `Studio` is a curated capability surface, not a plugin marketplace front page.
- Cards only exist when the card itself is the interaction object. Decorative card mosaics are banned.

### Home Rules
- `Home` should feel closest to Codex / Claude Code in information structure, but still belong to Longclaw visually.
- The primary visual field is:
  - thread header
  - conversation transcript
  - sticky composer
- `work_mode` lives inside the composer as a dropdown, not as large mode cards.
- Status, readiness, and project context move into the dual left sidebars.
- Governance objects appear in the transcript as receipts and continue into the shared detail drawer.
- `Home` is still not a generic chat app:
  - it must keep task receipts visible
  - it must keep the right detail drawer as the only deep inspection surface
  - it must keep thread/task continuity tied to the canonical ledger

## Motion
- **Approach:** `minimal-functional`
- **Durations**
  - `micro`: `120ms`
  - `short`: `160-180ms`
  - `medium`: `220ms`
- **Allowed**
  - drawer transitions
  - state refresh emphasis
  - row highlight on hover/focus
  - capability chip activation feedback
- **Banned**
  - persistent glow
  - decorative background animation
  - bounce or toy-like motion

## Component Contracts
These components define the first batch of UI contracts for Longclaw.

### `AppShell`
- owns the left rail, thread sidebar, main workspace, and right detail drawer
- the shell must feel stable even when content refreshes

### `LaunchComposer`
- canonical task launch input for `Home`
- supports natural language plus `@plugin / @skill / @pack`
- must look like a serious command surface, not a messaging bubble composer
- includes the canonical `work_mode` dropdown inline

### `ActiveCapabilitiesRail`
- compact strip of curated active capabilities
- allowed on `Home`, `Studio`, and flagship pack headers
- shows what is currently available without becoming a marketplace gallery

### `CapabilityChip`
- capsule for `@plugin / @skill / @pack`
- used for hints, active context, and curated presets
- must inherit standard state semantics

### `RecentLaunchRow`
- canonical row for the latest launch feedback
- summarizes launch source, outcome target, current state, and handoff into governance

### `ThreadSidebar`
- renderer-derived list of threads grouped from canonical ledger data
- shows workspace, flagship pack shortcuts, and thread summaries
- is allowed to derive from existing launch/task data without introducing new persistence

### `ConversationTranscript`
- canonical event stream shown on `Home`
- supports:
  - `user_launch`
  - `task_receipt`
  - `run_receipt`
  - `work_item_receipt`
  - `system_status`
  - `degraded_notice`
- must stay quiet and tool-like rather than chat-bubble heavy

### `LaunchContextPanel`
- secondary context panel for current launch constraints, session context, or delivery preference
- must remain compact and subordinate to launch + governance

### `StatusStrip`
- compact metrics summary
- allowed on `Home`, inside governance snapshots, and inside pack backlog summaries
- never styled like hero KPI cards

### `QueueRow`
- canonical row for runs, work items, repair cases, review tasks, connector health, and recent launches
- left side: title + metadata
- right side: status badge + optional next action
- clicking opens the shared detail drawer

### `StatusBadge`
- canonical state container
- states supported:
  - `loading`
  - `empty`
  - `success`
  - `partial`
  - `failed`
  - `needs_review`
  - `degraded`
  - `delivery_failed`
  - `running`

### `DetailDrawer`
- shared across runs, work items, recent launches, and pack records
- includes title, key metadata, actions, artifacts, and evidence preview
- in mid and narrow widths it overlays, not reflows the main list into chaos

### `ArtifactPreview`
- only inline-preview small text-like artifacts
- large files and binaries should open externally
- preview panels use mono typography and dark inspection surfaces

## Companion Surface Rules
### `WeClaw`
- role: remote cowork companion
- allowed:
  - task launch
  - lightweight status reply
  - delivery fallback messaging
  - next-step prompting
- banned:
  - evidence review
  - repair workflows
  - long-running governance UI
- terms must align with Longclaw:
  - `work item`
  - `needs review`
  - `partial`
  - `delivery failed`

### `Obsidian`
- role: reviewed knowledge plane
- only receives reviewed outputs:
  - `reviewed insight`
  - stable knowledge cards
  - final decisions
  - operator playbooks
- banned content:
  - raw WeChat logs
  - unreviewed evidence bundles
  - delivery fallback noise

### `Signals` And `due-diligence-core`
- role: flagship packs inside the `Professional Grounds`
- inherit typography, color semantics, row logic, and drawer behavior from Longclaw
- may become denser and more technical, but may not drift into separate brands
- must never outrank `Electron` as the default home

## Accessibility
- every interactive row must be keyboard reachable
- every badge must have text, not just color
- minimum touch target: `44px`
- structural landmarks must be present:
  - `nav`
  - `main`
  - `complementary`
  - section labels

## Anti-Patterns
- full-screen chat as the default home
- plugin marketplace as the product center
- purple / blue-violet AI gradients
- generic SaaS metric-card mosaics
- uniform bubbly radius on every surface
- default system font stacks as the final decision
- treating `Signals` like a second product home
- treating `Obsidian` like a runtime queue
- treating `WeClaw` like a miniature control plane

## Decision Log
| Date | Decision | Rationale |
| --- | --- | --- |
| 2026-04-19 | Set Longclaw design direction to `Warm Industrial Command Center` | Longclaw is an evidence-driven personal operations center, not a generic AI chat shell |
| 2026-04-19 | Adopted `Chat launches, console governs` as the product rule | Longclaw needs a launch front door without collapsing governance into chat |
| 2026-04-19 | Chose `Instrument Serif / Instrument Sans / IBM Plex Mono` | Needed editorial judgment + clear workflow UI + precise data surfaces |
| 2026-04-19 | Locked `Home / Runs / Work Items / Packs / Studio` | The product needs one default home, plus governance and curated capability surfaces |
| 2026-04-19 | Borrowed capability visibility and launch experience without chat-first gravity | Cowork products solve discoverability well, but Longclaw still centers governance and evidence |
