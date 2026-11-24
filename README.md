# a2ui-discord

Render [A2UI 1.0](https://a2ui.org/specification/v1.0-a2ui/) cards as native [Discord Components V2](https://docs.discord.com/developers/components/reference) messages. A dropdown edits the card's model. A button returns an action with the current values. Your bot owns transport, storage, authorization and dispatch.

Choose **one** package. Both are native implementations under the MIT license. Neither has runtime dependencies or requires the other language.

| Package | Runtime | Install from this checkout |
|---|---|---|
| [Python](python/README.md) | Python 3.11+ | `python -m pip install ./python` |
| [TypeScript / JavaScript](typescript/README.md) | Node.js 22+; ESM and CommonJS | Run `npm ci` and `npm pack` in `typescript/`, then install the `.tgz` in your app. |

## Supported subset

| Input | Behavior |
|---|---|
| `createSurface` | One complete basic-catalog tree rooted at `root`. Each mounted component occurs once. |
| `updateComponents` | Add or replace definitions by ID. Only controls reachable from `root` can act. |
| `updateDataModel` | Replace the root object or write at an absolute model path. `null` deletes the leaf; deleting an array element shifts later elements left. |
| `Column`, `Text` | Explicit ordered children and Discord Markdown text. Mention notifications are off. |
| `Image` | Render one item in a [Discord media gallery](https://docs.discord.com/developers/components/reference#media-gallery). `url` and optional `description` (1–1,024 characters of alt text) accept literal strings or bindings. `fit`, `variant` and `weight` are unsupported. |
| `Row`, `Divider` | A row contains 1–5 buttons or exactly one picker. A divider renders a horizontal separator. Vertical dividers and row styling are unsupported. |
| `ChoicePicker` | 1–25 distinct string options. Select one by default, or several with `variant: "multipleSelection"`. The optional label becomes a placeholder. Bind to an existing list. A click supplies at least one choice; set the model to `[]` to clear it. |
| `Button` | A `Text` child supplies the label. An omitted or `default` variant becomes secondary; `primary` becomes primary. `action.event` requires `name`. Optional `context` and `userMessage` resolve on click. |

Pass decoded JSON objects. Bind text, labels, picker values and action context with absolute [JSON Pointers](https://www.rfc-editor.org/rfc/rfc6901), e.g. `{"@path":"/findings/0/tags"}`. `/` is the model root. Escape `~` as `~0` and `/` as `~1` in keys. Parent objects and array slots must exist; writes may create a final object key. Array indices are zero-based decimal numbers without leading zeros. Relative paths, appends and automatic parent creation are unsupported.

Each action context value can be a string, number, boolean, array, plain object, or binding. Literal array/object contents are not evaluated. Top-level `@` keys in object literals are reserved. For portable snapshots, use strings for identifiers and for integers outside JavaScript's safe integer range.

Creates, updates and selections validate the mounted tree. Invalid input raises `SurfaceError`; failed updates and selections leave the previous card intact. Each message allows 40 Discord components including rows and container, and 4,000 total text-display characters. Templates, checks, RPC, `deleteSurface`, and incomplete streamed trees are not supported.

## Chart example

The [sample surface](examples/charts/surface.json) displays the same fictional ticket counts as a bar or line chart. The picker writes to `/view`; `Image.url` reads `/view/0`. Selecting **Line chart** changes the image without a chart-specific component or handler. Both images have the same alt text because they show the same values.

![Sample week: 18, 27, 21, 34, and 30 tickets resolved Monday through Friday.](examples/charts/bars.png)

With either package installed, run the matching snippet where `examples/charts/` is available:

```python
import json
from pathlib import Path
from a2ui_discord import Surface

card = Surface(json.loads(Path('examples/charts/surface.json').read_text()))
initial = card.message()  # Send with bars.png.
card.interact({'custom_id': 'a2ui:style', 'component_type': 3, 'values': ['attachment://line.png']})
edit = {'type': 7, 'data': card.message()}  # Respond with line.png.
```

```js
import { readFileSync } from 'node:fs';
import { Surface } from 'a2ui-discord';

const card = new Surface(JSON.parse(readFileSync('examples/charts/surface.json', 'utf8')));
const initial = card.message(); // Send with bars.png.
card.interact({ custom_id: 'a2ui:style', component_type: 3, values: ['attachment://line.png'] });
const edit = { type: 7, data: card.message() }; // Respond with line.png.
```

For an attachment, the bot supplies the bytes. In this example, send `bars.png` with the initial message. On the edit, upload `line.png` instead. Use [Discord multipart uploads](https://docs.discord.com/developers/reference#uploading-files): add `attachments: [{"id":0,"filename":"line.png"}]` to the edit's `data`, and send that PNG as `files[0]` alongside `payload_json`. The [two PNGs](examples/charts/) are ready to use. Matplotlib is optional and only needed to regenerate them.

For a hosted image, use a direct `https://` URL instead; no attachment is needed. This subset accepts ASCII DNS-style hosts without credentials or explicit ports. Percent-encode spaces and non-ASCII path or query characters. An `attachment://` name uses only ASCII letters, digits, `_`, `-` and `.` and cannot start with a dot. The renderer does not fetch URLs, read files, or verify the image format. Allow only trusted media sources and map attachment names to files the bot may share.

## Connect a bot

1. Construct a `Surface` from the envelope. Send `message()` to Discord. Store `snapshot()` with the returned message and channel IDs.
2. Verify the interaction, authorize the actor, and route it to that specific message. Restore with `Surface(saved)` in Python or `new Surface(saved)` in TypeScript.
3. Pass the raw Discord interaction's `data` object to `interact()`. A picker changes the model and returns `None` / `null`. A button returns an A2UI action. Dispatch only allowed actions.
4. For a local edit, acknowledge with `{"type":7,"data": ...}` using the new `message()`. For slow work, defer within Discord's three-second window. Serialize edits per message and save accepted changes. Control IDs are not credentials and do not encode a revision.

See the [security guidance](SECURITY.md), [shared JSON test cases](conformance/cases.json), [release checks](CONTRIBUTING.md), and [changelog](CHANGELOG.md). This project is independent of Discord and A2UI.
