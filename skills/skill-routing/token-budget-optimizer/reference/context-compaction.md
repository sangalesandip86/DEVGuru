# Context Compaction

<!-- reconstructed: v2 source not provided; review -->

When context passes `context.decompose_threshold`:
1. Write a checkpoint: commit WIP on the task branch, record `ledger_cursor` and `snapshot_id`
   (`change-management/change-set/reference/tasks-and-checkpoints.md`).
2. Summarize state into a handoff-shaped record: done, remaining, open QUESTIONs, ASSUMPTIONs,
   with `artifact_ref`s (`repo@sha:path` + content hash) — never prose-only memory.
3. Decompose remaining work into sub-tasks (`REPLAN` retry policy).
4. A fresh session resumes from the checkpoint and **re-reads ledger entries**, not the summary alone.

Compaction must preserve: every open QUESTION, every unexpired ASSUMPTION, every RISK, the tier,
and the loaded mandatory skill set. Dropping these to save tokens is forbidden.
