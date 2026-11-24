# a2ui-discord for Node.js

Translate A2UI 1.0 into native Discord Components V2 on Node.js 22+. `DiscordView` mounts a live protocol surface. `Surface` handles small cards without runtime dependencies. Neither sends network requests. MIT license.

From this directory run `npm ci` and `npm pack`. Install the resulting `.tgz` in your app.

## Mount a live surface

Also install `@a2ui/web_core@0.16.1`. Use the ESM subpath. With TypeScript `moduleResolution: "NodeNext"` or `"Node16"`, set `skipLibCheck: true`: the pinned SDK has two extensionless imports in its legacy declarations. Your application code can still use `strict: true`.

In an app with a copy of the repository's `conformance/studio.json`:

```js
import { readFileSync } from 'node:fs';
import { MessageProcessor, basicCatalog } from '@a2ui/web_core/v1_0';
import { DiscordView } from 'a2ui-discord/view';

const outbox = []; // Application-owned; authorize before dispatch.
const processor = new MessageProcessor([basicCatalog], undefined, {
  unifiedOutbound: true, outboundListener: message => { outbox.push(message); },
});
processor.processMessages(JSON.parse(readFileSync('conformance/studio.json', 'utf8')));
const view = new DiscordView(processor.getSurface('studio'));
const payload = view.message(); // Send once. Keep view under the returned message ID.
// In an async handler: const reply = await view.interact(verifiedInteraction.data);
// On retirement: view.dispose(); processor.dispose() when all surfaces are retired.
```

`interact()` returns the Discord callback; the processor sends A2UI action and RPC envelopes to `outboundListener`. Pass trusted action metadata as the second argument: `{ metadata: { extensions: { ... } } }`. Read `message()` after protocol updates and settled RPCs. See the [coverage and limits](https://github.com/tanvesh01/a2ui-discord#live-a2ui-10-surfaces).

## Render a dependency-free card

```ts
import { CATALOG, Surface } from 'a2ui-discord';

const card = new Surface({ version: '1.0', createSurface: {
  surfaceId: 'queue', catalogId: CATALOG, dataModel: { title: 'Review queue' },
  components: [{ id: 'root', component: 'Text', text: { '@path': '/title' } }],
} });
const payload = card.message(); // POST this JSON to Discord
card.apply({ version: '1.0', updateDataModel: { surfaceId: card.id, path: '/title', value: 'Queue closed' } });
const edited = card.message(); // PATCH the same message
```

CommonJS: `const { CATALOG, Surface } = require('a2ui-discord')`. Type declarations ship with the package.

Use `Text`, `Column`, horizontal `Divider`, `ChoicePicker`, or a `Button` with a `Text` label. Group 1–5 buttons or one picker in a `Row`. Set `variant: 'multipleSelection'` to let a picker select several distinct options. Bind to nested fields with absolute paths such as `/findings/0/tags`.

Use `Image` with a direct HTTPS URL or `attachment://filename`, and optional `description` for alt text. Both fields accept bindings. The bot supplies any upload. See the [chart example and URL limits](https://github.com/tanvesh01/a2ui-discord#chart-example).

Pass verified raw Discord `interaction.data` to `card.interact(data)`. A selection returns `null` and edits the model; a button returns a timestamped action. Catch `SurfaceError` for invalid input. Use `card.apply()` to edit, and `new Surface(card.snapshot())` to restore. Snapshots contain application data, not authorization state.

The host must authenticate requests, authorize actors, check the originating message and channel, and acknowledge Discord interactions. See the [supported subset and host contract](https://github.com/tanvesh01/a2ui-discord#supported-subset).
