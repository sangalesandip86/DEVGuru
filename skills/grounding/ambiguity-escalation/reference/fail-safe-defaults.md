# Fail-Safe Defaults (§5.3)

When evidence is incomplete, the system resolves toward more scrutiny — the cautious reading,
never the convenient one.

| Situation | Default | Never |
|---|---|---|
| Dependency not found by static analysis | UNRESOLVED | "no dependency" |
| Consumer/provider compatibility unknown | INCOMPATIBLE | "assume fine" |
| Risk tier can't be computed | HIGH | LOW |
| Two roles disagree on risk level | Higher assessment wins | Lower assessment |
| Agent uncertain about its own output, matching a named reason code | Escalate risk tier by exactly one level | Proceed at current tier, or escalate more than one level |
| A mandatory capability for the computed tier doesn't exist yet | Route to a named human (Degraded Mode, §2) | Block indefinitely, or silently skip the requirement |

## Applying a default
1. Record an ASSUMPTION whose `content` names the default applied and whose `reason` cites
   this table row.
2. Set `impact` to at least MEDIUM — a default stands in for missing evidence.
3. The default stays in force until a FACT (hook-written) or VERIFIED result replaces it.

## Why Degraded Mode exists
A fail-safe default that cannot be satisfied during early build phases (e.g. HIGH tier requires
architect + security-reviewer, which arrive in Phase 3) will otherwise silently stall
everything or get quietly bypassed — exactly the failure the fail-safe principle exists to
prevent. Routing to a named human keeps the scrutiny and the throughput.

## Risk-tier fallback before Phase 2
Before the full risk-tiering capability exists, the Phase 0 path-based lookup
(`change-management/risk-tiering/path-tiers.json`) provides a tier. If no pattern matches and
the change is non-trivial, the default is HIGH, not LOW.
