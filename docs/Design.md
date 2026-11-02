# Design

## Product experience

The dashboard is a local workspace for creating tasks, watching improvement runs, inspecting evidence, exploring harnesses, and reviewing retained lessons. The interface should make model output and operational evidence inspectable without presenting either as proof of task correctness. See `frontend/src/App.tsx` and `frontend/src/style.css` for the current implementation.

## Visual system

| Token or pattern | Current value or usage |
| --- | --- |
| Canvas | Warm off-white `#f8f9f6` (`--bg`). |
| Surface | White `#fff` (`--panel`). |
| Main text | Dark olive `#2c3228` (`--ink`). |
| Muted text | `#88917e` (`--muted`). |
| Borders | `#e5e8e0` (`--line`). |
| Soft surface | `#f0f3eb` (`--soft`). |
| Accent | Olive `#627b45` (`--green`); primary button uses `#303c27`. |
| Typography | Inter with system sans fallbacks; small monospace labels, IDs, metrics, and evidence. |
| Shape | Restrained 4–10 px radii, thin borders, compact spacing, and light panels. |

The `[data-theme=dark]` rules in `style.css` supply dark colors. The theme toggle persists its choice in `localStorage` as `harness-theme`. CSS media queries adapt the sidebar and layouts below 1100 px and 760 px.

## Components and interaction patterns

- Reuse `Button`, `Badge`, and `Card`/`Panel` from `frontend/src/components/ui/` before adding another shared control. Feature composition currently lives in `App.tsx`.
- Keep a fixed sidebar for primary navigation, a top status bar for provider status, a page heading with one clear action, and panels for data and controls.
- Use explicit loading, empty, and error states. The shared `State` component shows API failures and a path back to task creation.
- Put three example cards before the custom task form. Each card names its domain and included sources. The primary action includes source notes in the prompt and starts a base-only run; the secondary action attaches sources as files and starts a slower full improvement run. Show a pending state and explain the difference.
- Let users save execution defaults independently of task creation. Show custom run buttons only after an objective is entered; example cards have their own run controls.
- Show full improvement as five plain-language phases and base-only execution as two phases. Highlight the current phase, mark completed and terminal phases, and update the activity text from SSE events. Use a compact React Flow timeline on desktop and a vertical list on narrow screens. Keep output, trajectory, tools, candidates, contrasts, composition, and events separately inspectable below.
- Evidence list headings must be plain text. Tool actions are objects in API responses; show their action name as the heading and preserve the complete record in the detail body.
- Show Cancel run as the live-run action while a job is running; replace it with Run improvement after the job reaches a terminal state.
- Use Monaco's read-only side-by-side diff for harness changes. Preserve component names and source evidence in diff and library views.
- Make keyboard focus visible. Current focus styles use a two-pixel olive outline; icon-only controls need accessible labels.

## Main screens

Overview, New task, Tasks, Runs, Live run, Harness explorer, Harness diff, Improvement library, Evaluation, and Model settings are routes in `App.tsx`. The New task route uses `NewTask.tsx` to show bundled examples and a custom form. Custom task creation accepts an objective, domain, file uploads, recursion mode, width/depth `k`, model, and execution limits. The UI does not ask users for server-side file paths. The API supplies persisted data; the UI should not invent successful runs or quality scores.

## Current design gaps

The product concept's baseline-first review and manual library adoption are not implemented. The Evaluation page shows operational metrics but no external benchmark results. Track implementation in `Tasks.md`.
