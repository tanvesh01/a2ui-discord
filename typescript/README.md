# a2ui-discord for Node.js

Translate a subset of A2UI 1.0 into native Discord Components V2. Use from TypeScript or JavaScript on Node.js 22+. No Discord SDK, runtime dependencies, or network calls. MIT license.

From this directory run `npm ci` and `npm pack`. Install the resulting package in your app with `npm install /path/to/a2ui-discord-0.1.0-beta.3.tgz`.

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
