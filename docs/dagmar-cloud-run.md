# Dagmar Cloud Run rollout

This branch integrates upstream main `3362b43cb92f60afe4de3ffd382bcdd053ee5f4f`
(package version 0.0.6) with Dagmar's read-only, Workspace-only hosted server.
The original working directory and its uncommitted PII edits remain intact.

## Compatibility boundary

The existing `google-ads-mcp` service is in project `dagmar-mcp`, region
`europe-north1`. The approved issuer remains
`https://google-ads-mcp.dagmar.app`; the transport endpoint is `/mcp`.
FastMCP 4.1.2 and py-key-value-aio 0.4.6 match the inspected deployed image.
`requirements.lock` pins and hashes the complete platform-independent runtime.
Docker installs the Firestore extra from this lock, then installs this package
without dependency resolution. The source upload excludes everything except
the explicit build inputs, so local credentials, account data, checkouts, and
test artifacts cannot enter the image.

The recovered legacy Firestore adapter preserves collection/key identities,
TTLs, encryption salt, and key precedence. The final cutover deliberately uses
the new Native database `google-ads-mcp-cutover-north1-20261110` in `europe-north1`
because current Coolify sessions have changed since the earlier Cloud snapshot.
Existing sessions must reconnect once. No records from the old stores are copied
into the fresh database; old signed reference tokens without backing session
mappings are rejected. Both the original `google-ads-mcp` Firestore database and
Coolify FileTree remain untouched. Keep the existing service account and Secret
Manager version references, and do not rotate keys. Hosted validation is tied
to this approved fresh database and the unchanged canonical OAuth issuer.
The obsolete developer token is neither read nor passed to the Ads client.
Remove only its `GOOGLE_ADS_DEVELOPER_TOKEN` Cloud Run secret binding atomically
with deployment of this updated image. Preserve the underlying Secret Manager
resource and all other OAuth/storage secret references.

Only `customers_list_accessible_customers`, `search_search`, and
`metadata_get_resource_metadata` can be mounted. New upstream mutation modules
are not imported by the coordinator. Hosted requests require a verified user's
OAuth token; the Cloud Run service account cannot substitute for that token.

## Verify and build

Run from the migration checkout, with no production secrets in the shell:

```sh
uv venv --python python3.11
uv pip install --python .venv/bin/python --require-hashes -r requirements.lock
uv pip install --python .venv/bin/python black pyfakefs coverage
.venv/bin/python -m unittest discover --buffer -s tests -p '*_test.py'
.venv/bin/python -m unittest tests.smoke.smoke_test
.venv/bin/black --check -l 80 ads_mcp tests noxfile.py
git diff --check
```

After code review, choose a unique immutable image tag and build:

```sh
gcloud builds submit --project dagmar-mcp --config cloudbuild.yaml \
  --substitutions=_IMAGE=europe-north1-docker.pkg.dev/dagmar-mcp/mcp-servers/google-ads-mcp:REVIEWED_TAG .
```

Resolve its registry digest, then update the existing service without changing
traffic or its configuration. Substitute the reviewed digest and unique tag:

```sh
gcloud run deploy google-ads-mcp --project dagmar-mcp --region europe-north1 \
  --image europe-north1-docker.pkg.dev/dagmar-mcp/mcp-servers/google-ads-mcp@sha256:REVIEWED_DIGEST \
  --no-traffic --tag REVIEWED_TAG
```

Inspect the revision's Ready condition and image digest. The tag URL has a
different hostname from `GOOGLE_ADS_MCP_HTTP_HOST` and is deliberately rejected
by host protection. Probe `/health` and OAuth discovery through an approved
route that preserves the accepted Host header and current IAM boundary, if
Google's frontend supports it. Otherwise configure the exact candidate tag
hostname as the candidate revision's HTTP host, preserving the canonical
issuer; restore the correct production HTTP host in the final revision.
Do not disable host protection or introduce wildcard hosts to make a probe work.
Confirm the discovery issuer still names the canonical hostname.
Do not exercise OAuth writes against the shared database during this stage.
Cloud Run invocation IAM must permit intended external MCP clients before
public cutover; application OAuth and Workspace restriction must remain active.
Before making invocation public, remove every traffic tag pointing at a revision
configured with the stale original database. Retain those revisions unrouted.
The final service route must send 100% to the reviewed fresh-database revision,
with no publicly reachable stale-database candidate tag.

## Cutover gates and rollback

Coolify FileTree freshness was confirmed to be later than the existing Cloud
snapshot. The approved cutover avoids stale sessions by starting fresh, with
one reconnect for existing users. Do not import the stale Cloud session snapshot
or claim session continuity. Restore the stable Cloud Run HTTP hostname and set
the approved fresh Firestore database when deploying the final reviewed image.

Keep the canonical hostname and OAuth redirect registration unchanged. Configure
Cloud Run custom-domain routing and its certificate, then apply the exact DNS
records returned by Google through the authoritative DNS provider. Preserve
Coolify available for rollback while DNS converges, with exactly one active
OAuth writer or a reviewed shared-state synchronization mechanism. Allowing
both old FileTree and new Firestore servers to write independently forks session
state. Stop or route OAuth writes during the controlled cutover interval.
Verify public TLS, canonical discovery, rejected
unauthenticated `/mcp`, a fresh allowed Workspace OAuth login, rejection of an
outside account, and the exact three-tool authenticated inventory. Check an
existing session is rejected and requires reconnecting, then confirm the fresh
session succeeds and a synthetic read-only Ads request supports per-request MCC.
Record evidence without tokens, queries, account data, or production logs.

Only after the above gates pass should traffic move to the reviewed revision.
Record the prior revision and DNS values first. Roll back by restoring traffic
to a reviewed compatible application image configured against the fresh cutover
database. Do not automatically restore original revisions `00002` through
`00005`, which use the stale original database. Returning DNS to preserved
Coolify requires state and revocation reconciliation, or an explicitly reviewed
new authentication epoch with reconnects; accepting reconnects alone does not
prevent old preserved sessions from becoming valid again. A return to FileTree
after fresh Firestore writes requires a reviewed reverse-sync/revocation
procedure. DNS rollback alone cannot preserve the cutover security boundary.
Keep the same OAuth secrets and storage adapter during rollback.
Do not delete the prior revision, Coolify deployment, or OAuth data until the
user has accepted the completed migration.
