# Security and trust model

The renderer translates data. It does not authenticate callers, verify Discord requests, authorize actions, or execute tools. Treat agent output and action context as untrusted input. Limit envelope size before parsing. Treat snapshots as private application data.

Accept interactions only from a verified Discord gateway session or a signature-verified Discord HTTP request. Retrieve the surface by the originating message and channel; check the actor, control lifetime, and application permissions on every interaction. Serialize edits per message, deduplicate interaction IDs, and reject stale versions. A `custom_id` is not an authorization token. Revoke or disable controls when their host session ends. Do not turn action names or context into arbitrary tool calls.

The live SDK resolves bindings and can emit agent RPC requests while mounting a tree, before a person clicks. Register only trusted catalogs, functions, and custom renderers. Authorize outbound RPC independently of user actions. Check budgets for model size, template expansion, pending calls, and message edits. `allowed_mentions` suppresses notifications, not Markdown links. Approve destination hosts and attachment names before rendering. Share only the data each recipient may see; `sendDataModel` can include a whole model. Remounts and changed lists can invalidate control IDs and menu values. Bind form submissions to the opening actor, message and revision.

Report security concerns privately to the repository owner. Do not include tokens, real interactions, or company data in issues, fixtures, or logs.
