# Changelog

## Python 0.1.0b3 / TypeScript 0.1.0-beta.3

- Render `Image` as a Discord media gallery item with a literal or bound URL and optional alt text. The bot supplies any attachment; the renderer does no I/O.
- Try the [bar and line chart example](README.md#chart-example). One dropdown switches the image on the same card.

## Python 0.1.0b2 / TypeScript 0.1.0-beta.2

- Group buttons in `Row`, render a horizontal `Divider`, and accept single- or multiple-selection `ChoicePicker` controls.
- Read and update nested object fields and existing array elements with absolute JSON Pointers. Rejected edits leave the previous snapshot intact.

## Python 0.1.0b1 / TypeScript 0.1.0-beta.1 — first beta candidates

- Choose a native Python or TypeScript/JavaScript package. Both implement the same JSON wire contract with no runtime dependencies.
- Convert A2UI 1.0 text, columns, single-choice pickers and default or primary buttons into Discord Components V2 messages.
- Return a button action with the current context and optional `userMessage`.
- Restore a card and its selections from a JSON snapshot. Reject an invalid create, update or selection without replacing a working card.
- Raise `SurfaceError` for invalid supported input. The host retains control of Discord I/O, storage, authorization and agent dispatch.

This is a subset renderer, not a claim of full A2UI conformance. The beta interface may change before 1.0; breaking changes will be listed here.
