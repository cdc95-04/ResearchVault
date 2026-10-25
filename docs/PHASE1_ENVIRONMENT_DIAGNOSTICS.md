# Read-only environment diagnostics

Use this checklist before real identifier-intake acceptance. It describes what
to measure on an installation; it contains no machine inventory or live-service
claim. Keep actual responses and environment details in ignored local storage.

## Configuration and process

Inspect the chosen configuration without printing secrets. Confirm an explicit
external Vault, separate external runtime, intended library and `read_only:
true`. Leave acquisition disabled for diagnostics. Personal Library uses
`library_id: null` and the Local API namespace `users/0`; a group uses its explicit
group identity. Confirm local configuration remains ignored by Git.

Check that Zotero Desktop is running on the host that owns the intended library
and that its local-communication setting is enabled. An enabled setting does
not prove that a listener is running. Do not reset credentials, launch another
profile or switch backends to compensate for an unreachable service.

For Windows, these read-only commands can help distinguish the layers:

```powershell
Get-Process -Name zotero -ErrorAction SilentlyContinue
curl.exe --noproxy "*" --max-time 10 -i http://127.0.0.1:23119/api/
python -X utf8 -m researchvault --config config/local.yaml zotero-inventory
python -X utf8 -m researchvault --config config/local.yaml validate
```

On another platform, use its process inspection command and `curl` equivalent.
The loopback address is Zotero's protocol endpoint, not a remote service. When
terminal encoding cannot represent library metadata, Python's `-X utf8` can
separate an output-encoding failure from a connection failure.

## Record the failing layer

| Observation | Interpretation and next check |
| --- | --- |
| Process absent or connection refused | Desktop/listener is unavailable; request startup or correct host context |
| Permission denied by executor | Execution policy may block loopback; use approved host access if available |
| DNS/TCP/TLS timeout on a public source | Record the transport layer and bounded timeout; do not label it an identity failure |
| HTTP response received | Record actual status and API/schema/Server ID headers, including missing headers |
| Inventory incomplete or version changed | Dedup is not established; do not treat partial pagination as complete |
| Inventory unavailable | Item count is unavailable, not zero |
| Empty complete inventory | Valid empty-library observation; nonempty reuse coverage remains untested |
| Host succeeds but restricted executor fails | Document their different reachability; do not infer a separate VM or database without evidence |

Read access does not prove write authorization. Schema/API versions are not a
substitute for the exact Desktop release. Preserve real Server IDs in private
run evidence so later requests can detect instance changes.

## Selected metadata, version and dedup preview

Use a previously selected paper; this diagnostic is not literature discovery.
Replace the following synthetic identifier with an approved exact identity:

```sh
researchvault --config config/local.yaml intake 2401.01234v2 --resolve --dry-run
```

The resolver reads canonical public metadata and the configured Zotero inventory.
Check title/authors, DOI and arXiv version separately, canonical URLs, source
responses and existing-parent/attachment decisions. Title similarity alone is
not deduplication. Related publisher and preprint versions must not silently
merge. Keep response digests and actual item keys out of committed reports.

Check public PDF route reachability separately from acquisition. A successful
HEAD response, PDF MIME type or filename does not verify PDF bytes or paper
identity. Inspect lawful access and applicable source terms; availability does
not itself grant redistribution rights. If the resolver did not extract license
metadata, record that limit rather than claiming it verified a license.

## Authorization boundary

Consult the [official Zotero Local API documentation](https://www.zotero.org/support/dev/web_api/v3/local_api)
for the installed version's supported read/write and authorization behavior.
The existing client uses the official Local API, Server ID checks, durable
mutation-intent receipts, conditional attachment upload and read-back. Reuse
that client; do not substitute database access or another import mechanism.

Diagnostics must not request a new key, print an existing key or alter protected
credential storage. Checking whether the configured environment variable exists
does not establish its permissions or whether another protected credential exists.
No write attempt is justified merely by a successful read-only probe.

After prerequisites succeed, follow the separately authorized [real acceptance
procedure](PHASE1_REAL_ACCEPTANCE.md). If a service, permission or credential is
missing, stop that operation and report the exact blocker and minimal user action.
