# Deterministic Check Catalog

| # | Check | What It Validates |
|---|-------|-------------------|
| 1 | `risk_routing` | Risk score maps to correct tier |
| 2 | `sensitive_path_detection` | Sensitive paths are detected correctly |
| 3 | `discovery_bounds` | Discovery exhaustion triggers ESCALATE |
| 4 | `circuit_breaker` | STOP file triggers immediate halt |
| 5 | `path_tier_lookup` | Sensitive paths map to correct tier floor |
| 6 | `log_scale` | Log scaling function produces correct values |
| 7 | `sigmoid_properties` | Sigmoid function has correct mathematical properties |
| 8 | `bm25_ranking` | BM25 search ranks relevant items higher |
| 9 | `lesson_ranking` | Lesson ranker prioritizes file-overlap matches |
| 10 | `dangerous_path_blocking` | Path traversal guard blocks dangerous paths |
| 11 | `control_file_protection` | Control file guard blocks protected paths |
| 12 | `event_type_validation` | Event journal rejects unknown event types |
