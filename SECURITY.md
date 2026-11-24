# Security and trust model

The renderer translates data. It does not authenticate callers, verify Discord requests, authorize actions, or execute tools. Treat agent output and action context as untrusted input. Limit envelope size before parsing. Treat snapshots as private application data.

Accept interactions only from a verified Discord gateway session or a signature-verified Discord HTTP request. Retrieve the surface by the originating message and channel; check the actor, control lifetime, and application permissions on every interaction. Serialize edits per message, deduplicate interaction IDs, and reject stale versions. A `custom_id` is not an authorization token. Revoke or disable controls when their host session ends. Do not turn action names or context into arbitrary tool calls.

Report security concerns privately to the repository owner. Do not include tokens, real interactions, or company data in issues, fixtures, or logs.
