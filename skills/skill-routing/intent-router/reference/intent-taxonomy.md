# Intent Taxonomy

Classification categories for user requests. Each intent maps to a primary role,
a set of skills, and the ADLC stage where work begins.

## Categories

### 1. Build / Implement

**Signals:** "build", "create", "add", "implement", "develop", "make", "write code for"

| Sub-intent | Start Stage | Primary Role | Skills |
|-----------|------------|-------------|--------|
| New feature from scratch | INTAKE | product-owner | requirements-ingestion, story-writer |
| Add to existing feature | IMPLEMENT | developer | project-conventions, test-implementation |
| Prototype / spike | IMPLEMENT | developer | (minimal skill set) |

### 2. Fix / Debug

**Signals:** "fix", "bug", "broken", "error", "crash", "doesn't work", "failing", "regression"

| Sub-intent | Start Stage | Primary Role | Skills |
|-----------|------------|-------------|--------|
| Known bug (ticket/repro) | IMPLEMENT | developer | test-implementation |
| Unknown cause | TEST | qa-diagnose | failure-capture |
| Flaky test | TEST | qa-diagnose | test-implementation |

### 3. Review / Audit

**Signals:** "review", "check", "audit", "look at", "evaluate", "assess"

| Sub-intent | Start Stage | Primary Role | Skills |
|-----------|------------|-------------|--------|
| Code review | REVIEW | code-reviewer | project-conventions |
| Security review | REVIEW | security-reviewer | trust-boundaries |
| Architecture review | ARCHITECTURE | architect | engineering-design |
| Risk assessment | INTAKE | (risk-tiering) | risk-tiering |

### 4. Test

**Signals:** "test", "coverage", "verify", "validate", "QA", "acceptance"

| Sub-intent | Start Stage | Primary Role | Skills |
|-----------|------------|-------------|--------|
| Write unit tests | IMPLEMENT | developer | test-implementation |
| Write acceptance tests | TEST | test-engineer | test-implementation |
| Design test cases | TEST | qa-derive | definition-of-done |

### 5. Plan / Design

**Signals:** "plan", "design", "architect", "propose", "structure", "decompose", "break down"

| Sub-intent | Start Stage | Primary Role | Skills |
|-----------|------------|-------------|--------|
| Requirements gathering | INTAKE | product-owner | requirements-ingestion |
| Story decomposition | PLAN | product-planner | story-writer |
| Architecture design | ARCHITECTURE | architect | engineering-design |
| Risk planning | PLAN | product-planner | risk-tiering |

### 6. Explain / Explore

**Signals:** "explain", "what is", "how does", "why", "show me", "find", "search", "where"

| Sub-intent | Start Stage | Primary Role | Skills |
|-----------|------------|-------------|--------|
| Code explanation | — | (none) | (read-only) |
| Architecture overview | — | (none) | (read-only) |
| Search for code/tasks | — | (none) | bm25, evidence-ledger |

### 7. Refactor

**Signals:** "refactor", "clean up", "restructure", "rename", "extract", "simplify", "optimize"

| Sub-intent | Start Stage | Primary Role | Skills |
|-----------|------------|-------------|--------|
| Local refactor | IMPLEMENT | developer | project-conventions |
| Cross-module refactor | ARCHITECTURE | architect → developer | engineering-design |

### 8. Deploy / Release

**Signals:** "deploy", "release", "ship", "publish", "merge"

| Sub-intent | Start Stage | Primary Role | Skills |
|-----------|------------|-------------|--------|
| Release process | RELEASE | (human required) | — |
| CI/CD configuration | IMPLEMENT | developer | project-conventions |

### 9. Incident / Diagnose

**Signals:** "incident", "outage", "alert", "on-call", "investigate", "diagnose", "root cause"

| Sub-intent | Start Stage | Primary Role | Skills |
|-----------|------------|-------------|--------|
| Active incident | TEST | qa-diagnose | failure-capture |
| Post-mortem | LEARN | qa-diagnose | failure-capture |

## Confidence scoring

| Level | Condition | Action |
|-------|-----------|--------|
| HIGH | Single category matches with 2+ signal words | Auto-assign role |
| MEDIUM | 2–3 categories match | Present options, default to strongest |
| LOW | No clear match or conflicting signals | Ask one clarifying question |

## Fallback

When no intent is classifiable, default to **Explain / Explore** (read-only,
lowest risk). Never default to a write-capable role on ambiguous input.
