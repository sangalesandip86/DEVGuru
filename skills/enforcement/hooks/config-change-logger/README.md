# config-change-logger (ConfigChange-class)

Logs every attempted control-file change regardless of outcome (plan §4.1, §4.11).

- Registered on **PreToolUse / `preToolUse`** next to control-file-guard so denied attempts
  are logged too — the portable mechanism on both platforms.
- If your Claude Code version exposes a dedicated configuration-change hook event, register
  it there as well; the script accepts any payload with `file_path`/`source`. Check the
  current event name in the Claude Code hook reference first (plan §8 warns that circulating
  event names aren't always current).
- Output: `.adlc/config-changes.log` (JSONL, always) + a FACT ledger entry with
  `source_type: hook_observation` (fails open).
- Never blocks.
