# Tool Safety Bounds

Limits enforced by the host tool, not by skills.

| Tool | Host-enforced limit |
|---|---|
| Read | 256 KiB per read, 2000 lines |
| Bash | 120 s default timeout, 600 s hard cap, 30K characters of output |
| Grep | 200 results, 400 characters per line |
| Walk / Glob | 20K entries |

## Policy
- Host limits are the **primary control**. Skills do not rely on, restate as enforcement, or try
  to bypass them.
- Skills design within the bounds: read by range, narrow searches, paginate.
- **Decompose rather than raise limits.** If a task needs more than a limit allows, split the
  task (`REPLAN`); do not request a higher limit.
- Output truncated by a bound is incomplete evidence — never treat it as the full content.
- Values above reflect current host defaults and may differ per host; verify against the host
  before relying on an exact number.
