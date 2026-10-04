# Contract Schema


| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | Yes | Stable, e.g. `billing-api`, `refund-events` |
| `type` | `http` \| `grpc` \| `graphql` \| `event` | Yes | Decides which directions are checked |
| `provider` | application name | Yes | Producer / server |
| `consumers[]` | application names | Yes | Known consumers; unknown consumers make blast radius `UNKNOWN_BLAST_RADIUS` |
| `spec` | `{artifact_ref: "repo@sha:path", content_hash: "sha256:…", format: openapi\|proto\|graphql\|avro\|jsonschema\|asyncapi}` | Yes | Never a bare filename |
| `version` | semver string | Yes | Contract version, independent of app version |
| `compatibility_policy` | `BACKWARD` \| `FORWARD` \| `FULL` \| `NONE` | Yes | See below |
| `verifications[]` | `{provider_version, consumer, consumer_version, result, evidence}` | No | Written from CI contract-test results (`VERIFIED` source), never by agents |
| `owner` | team / CODEOWNERS entry | Yes | |

## Compatibility direction

| Direction | Question | Required when |
|---|---|---|
| **New producer → old consumer** | Can consumers still deployed read what the new provider sends/returns? | Deploying a provider (all types) |
| **Old producer → new consumer** | Can the new consumer handle what the still-deployed provider sends — including retained messages from older producer versions? | Deploying a consumer (all types); for `event`, against every retained producer version |

| Policy | Meaning |
|---|---|
| `BACKWARD` | New consumers read data from old producers |
| `FORWARD` | Old consumers read data from new producers |
| `FULL` | Both |
| `NONE` | No guarantee — every deploy needs a fresh pair verification |

Request/response contracts (`http`, `grpc`, `graphql`) need both directions at deploy time for the
side being deployed; event contracts need `FULL` in practice because messages outlive deployments.

## Default
No verification for an exact deployed version pair → **INCOMPATIBLE** (§5.3). "Latest against
latest" is never evidence.

## Example
```yaml
id: refund-events
type: event
provider: billing
consumers: [ledger, notifications]
spec:
  artifact_ref: "acme/billing@a1b2c3d:schemas/refund-issued.avsc"
  content_hash: "sha256:9f8e..."
  format: avro
version: 2.1.0
compatibility_policy: FULL
owner: "@acme/billing-team"
```
