# Vertical slicing patterns

A **vertical slice** cuts through every layer it needs (UI, API, logic, data) to deliver one
observable behaviour. A **horizontal slice** ("the DB part", "the API part") delivers nothing
on its own. It can't be accepted by a user, and it hides integration risk until the end.

Test each slice with **INVEST**: Independent, Negotiable, Valuable, Estimable, Small (≤ M),
Testable (qa-derive can test it blind).

## Start with the walking skeleton
The first slice is the thinnest end-to-end path that delivers the core outcome for the
simplest case. Example: "one PM, one equity book, VaR shown, no stale badge, no
entitlements beyond the existing one". Later slices thicken it.

## SPIDR (Mike Cohn), plus three more

| Pattern | Split along | Example (intraday VaR) |
|---|---|---|
| **S**pike | an unknown that blocks estimation | "Can parametric VaR run in < 60 s per book?" → SPIKE, then stories |
| **P**aths | alternative or error paths through the workflow | happy path; stale VaR; API error; not entitled |
| **I**nterfaces | channel, device, consumer | dashboard tile first; API for limit monitoring next; mobile later |
| **D**ata | data subsets or types | equity books first; FX next; fixed income out of scope |
| **R**ules | business rules or variations | 99% 1-day VaR first; 97.5% ES later; per-desk overrides last |
| Workflow steps | steps of a longer journey | view VaR → drill down by asset class → export |
| Quality / NFR | progressively stricter qualities | correct at 1 RPS → p95 < 300 ms at 200 RPS (separate story with an nfr criterion) |
| CRUD / operations | operations on one entity | create limit → change limit → retire limit (each with its negative path) |

## Choosing the next cut
1. Is there an unknown that blocks estimating? Use a **Spike**.
2. Are there several paths? Ship the happy path plus the most likely failure path first.
3. Are there several data kinds or rules? Ship the most valuable subset first.
4. Is it still `L`? Slice by **workflow step**.
5. Is it still `L`? It's probably an epic.

## Anti-patterns

| Smell | Example | Fix |
|---|---|---|
| Layer story | "Create VaR table", "Build VaR API", "Build VaR tile" | One slice: "PM sees VaR for one book" through all three layers |
| Setup story | "Set up the project" with no behaviour | Fold the setup into the walking skeleton, or make it a typed TECHNICAL_STORY with a measurable no-behaviour-change criterion |
| Testing story | "Write tests for ST-12" | Tests belong to the story whose criteria they verify. TEST_AUTOMATION is only for existing, untested criteria. |
| Hardening at the end | "Make it fast", "Make it secure" after all features | Quality slices with numbered nfr criteria, scheduled early for HIGH tier |
| Mega-spike | "Investigate the risk platform" | One question per spike, time-box ≤ 10 days |
| Contract and consumer in one story | "Add endpoint and use it in the UI" | `API_CONTRACT` story (floor HIGH, architect review) and a consumer story that depends on it |
