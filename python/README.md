# a2ui-discord

A Python library that renders [A2UI 1.0](https://a2ui.org/specification/v1.0-a2ui/) as native [Discord Components V2](https://docs.discord.com/developers/components/using-message-components). `DiscordView` mounts a live protocol surface; `Surface` handles small cards without runtime dependencies. Neither sends network requests. MIT license. Python 3.11+.

## Mount a live surface

Install `python -m pip install '.[protocol]'` from this directory. From the repository root:

```python
import json
from pathlib import Path
from a2ui.core.basic_catalog.v1_0 import BasicCatalog
from a2ui.core.processing import MessageProcessor, MessageProcessorOptions
from a2ui_discord.view import DiscordView

outbox = []  # Application-owned; never forward a function call without authorization.
processor = MessageProcessor([BasicCatalog()],
    action_handler=lambda action: outbox.append({'version': '1.0', 'action': action}),
    options=MessageProcessorOptions(outbound_listener=outbox.append))
processor.process_messages(json.loads(Path('conformance/studio.json').read_text()))
view = DiscordView(processor.model.get_surface('studio'))
payload = view.message()  # Send once. Keep view under the returned message ID.
# In an async handler: reply = await view.interact(verified_interaction['data'])
# On retirement: view.dispose(); processor.dispose() when all surfaces are retired.
```

`interact()` returns a Discord callback, not an A2UI action. The processor emits actions to `action_handler`. Use `outbound_listener` for RPC; subscribe to SDK error events for diagnostics. Run agent RPC on an event loop. When the answer settles, read `message()` again and edit the original message. Pass trusted action metadata with `metadata={'extensions': {...}}` on `interact()`, not inside Discord input. The [coverage table](https://github.com/tanvesh01/a2ui-discord#live-a2ui-10-surfaces) lists native fallbacks. The rest of this guide describes the smaller `Surface` interface.

## Install and render

From a source checkout, run `python -m pip install .` in a virtual environment. This beta supports a subset of A2UI, not an arbitrary A2UI application.

```python
from a2ui_discord import CATALOG, Surface

surface = Surface({"version": "1.0", "createSurface": {
    "surfaceId": "queue", "catalogId": CATALOG,
    "components": [{"id": "root", "component": "Text", "text": {"@path": "/status"}}],
    "dataModel": {"status": "Three items need review."},
}})
payload = surface.message()  # POST /channels/{channel_id}/messages
surface.apply({"version": "1.0", "updateDataModel": {
    "surfaceId": "queue", "path": "/status", "value": "Two items need review."
}})
edited = surface.message()   # PATCH the same message
```

## Try the audit card

From this directory:

```sh
python3 -m examples.audit --finding backup
python3 -m unittest -v
```

The example prints the outgoing card and two simulated Discord interactions' responses. Pick one of three fictional findings: its details appear on the original message (callback type `7`, `UPDATE_MESSAGE`). Click **Review finding**: the example agent gets the declared `reviewFinding` action with the selected finding. The button does not approve or change an audit. Try `--finding owner` or `--finding rotation` to compare.

## Use in a bot

1. Construct `surface = Surface(envelope)` and send `surface.message()` to Discord. Keep the surface under the returned message ID and thread ID.
2. Receive a verified component interaction. The bot must authorize the actor, find the surface for **that message and thread**, and reject stale or duplicate callbacks. Control IDs are routing labels, not credentials.
3. Call `event = surface.interact(interaction['data'])`. A picker updates `surface.model` and returns `None`. A button returns an A2UI `action` with current context. Dispatch only actions the host allows.
4. Acknowledge within Discord's three-second window. For a local edit, return `{'type': 7, 'data': surface.message()}`. For slow agent work, defer the update first, then edit the original message.

## Supported subset

| Input | Behavior |
|---|---|
| `createSurface` | Start with a complete basic-catalog tree rooted at `root`. |
| `updateComponents` | Add or replace definitions by ID. Only controls reachable from `root` can act. |
| `updateDataModel` | Replace the root object, set an object field, or replace an array element. `null` deletes a field or removes an array element. Parents and array indices must already exist. |
| `Column`, `Text` | Ordered children and Discord Markdown text. Mention notifications are off. |
| `Image` | Use a direct HTTPS URL or `attachment://filename`, and optional `description` for alt text. Both fields accept bindings. The bot supplies any upload. See the [chart example and URL limits](https://github.com/tanvesh01/a2ui-discord#chart-example). |
| `Row`, `Divider` | Group 1–5 buttons or a single picker in one action row. Dividers are horizontal only. |
| `ChoicePicker` | 1–25 distinct options, single-choice by default or `variant: "multipleSelection"`. Bind `value` to an existing list. A Discord selection is nonempty; a model update can clear it. |
| `Button` | A `Text` child supplies the label. An omitted or `default` variant becomes a Discord secondary button; `primary` becomes primary. `action.event` requires `name`. Optional `context` and `userMessage` resolve on click. |

Pass decoded JSON objects. Text, labels, picker values and action context support absolute `@path` bindings such as `/findings/0/owner`. Escape `~` as `~0` and `/` as `~1` in keys. Each action context value can be a string, number, boolean, array, plain object, or binding. Literal arrays and objects are data; their contents are not evaluated. Object literals with top-level `@` keys are not supported.

`Surface(envelope)` checks the tree before accepting it. Updates and selections also check the entire mounted tree before changing state. Catch `SurfaceError` (a `ValueError`) and keep the old message on failure. Read `surface.model` for current values; use `apply()` for edits. Direct dictionary mutation bypasses validation. Check Discord transport success separately.

Every mounted component must occur exactly once. The card must fit in one Discord message: at most 40 Discord components, including the container, action rows, and controls, and 4,000 total text-display characters. This is not a complete A2UI validator. Relative paths, templates, checks, RPC, `deleteSurface` and incomplete streamed trees are not implemented.

## Restore a card after a restart

Persist `surface.snapshot()` as JSON alongside the Discord message ID, channel ID, allowed actors and revision. Use `Surface(saved_envelope)` to restore; no previous in-memory session or render call is required. Save again after accepted edits or selections. Snapshots do not include credentials, user authorization, or Discord routing unless your application puts that data in the model. Protect stored data and serialize edits per message.

The library contains no audit-specific code. The [example](examples/audit.py) owns the fictional findings and agent behavior. See the [project repository](https://github.com/tanvesh01/a2ui-discord) for the shared wire contract, security guidance and release checks. This is an independent project, not an official Discord or A2UI renderer.
