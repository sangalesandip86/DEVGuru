# GitHub Copilot — organization-level control-file protection

Copilot's coding agent works on a branch and opens a PR, so the durable control point is the
forge, not the client. Apply all of the following at the **organization** level:

1. **CODEOWNERS** — every glob in `control-file-paths.json` owned by a platform-owners team.
   (CODEOWNERS is itself a control file.)
2. **Branch ruleset** (org-level, targeting all repos in the pilot):
   - Require pull request + review from Code Owners.
   - Require status check `control-file-policy-check` (see `../../ci-checks/`).
   - Block force pushes; restrict bypass list to platform owners (humans only, no apps).
3. **Push ruleset — restricted file paths**: block pushes from the Copilot agent's identity
   that modify control-file paths, where your plan supports file-path push rules.
4. **Copilot policies**: restrict which MCP servers custom agents may use to the approved
   `adlc` server; disable agent access for repos not enrolled in the pilot.
5. **Hooks**: `.github/hooks/hooks.json` from `../../hooks/registration/copilot-hooks.json`,
   protected by (1)–(3). Copilot hooks use the same `permissionDecision: deny` contract.

Gap to track: Copilot hooks live in the repo, so (1)–(3) are what make them non-editable by an
agent. Treat any change under `.github/hooks/` as CRITICAL (it is in the control-file list).
