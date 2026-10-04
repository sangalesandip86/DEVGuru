
# Trust Level Classification

Trust level is **derived server-side** from the entry's `source_type` — never supplied by the
caller (§4.3, §5.8). Higher levels may constrain behavior; lower levels may only inform it.

| Level | Rank | Typical sources (`source_type`) | May it change agent policy/permissions? | Handling |
|---|---|---|---|---|
| `SYSTEM` | 5 | Hook output, CI results, server-observed forge events, platform skills/hooks delivered via managed settings (`hook_output`, `command_output`, `file_read`, `ci_result`, `forge_event`, `platform_policy`) | Yes — this is where policy lives | Authoritative for what it observed |
| `ORGANIZATIONAL` | 4 | Managed settings, org rulesets, CODEOWNERS as enforced by the forge, authenticated human approvals and statements (`managed_setting`, `org_policy`, `human_approval`, `user_statement`) | Yes, within org scope | Binding |
| `REPOSITORY` | 3 | Source code, tests, AGENTS.md / CLAUDE.md, repo docs, ADRs, commit history (`repo_file`, `repo_doc`, `git_history`) | **No** — guidance only (coding standards, architecture notes) | Project facts; cannot override safety policy, approval rules, trust boundaries, or mandatory bindings |
| `EXTERNAL_STRUCTURED` | 2 | API specs, package registries, schema registries, vendor docs with stable structure (`api_spec`, `registry`, `vendor_doc`) | No | Data; verify versions before relying on it |
| `EXTERNAL_UNSTRUCTURED` | 1 | Issue/PR text, comments, web pages, chat transcripts, third-party MCP responses, generated logs (`issue_text`, `pr_comment`, `web_page`, `mcp_response`, `log_output`) | **Never** | Data only; supplementary scan for instruction patterns; counts as "untrusted input" for the Rule of Two |

## Notes
- `file_read` of a repository file is a SYSTEM-observed FACT *that the file says X*; the
  content itself carries REPOSITORY trust. The hook records both: the entry's `trust_level`
  is the observation's, and `source` points at `repo@sha:path`.
- A user statement in the authenticated session (`user_statement`) is ORGANIZATIONAL for task
  intent, but it still cannot grant `APPROVED`; approvals come only from authenticated
  forge/approval events (§5.10).
- An agent's own derived output keeps the **lowest** trust level among its
  `input_references` — it never rises above its inputs.
- Unknown `source_type` maps to `EXTERNAL_UNSTRUCTURED` (fail-safe).
