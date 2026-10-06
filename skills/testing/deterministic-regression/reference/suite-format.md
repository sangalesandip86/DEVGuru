# Golden Case Format

## Structure

Each golden case is a JSON file with the following structure:

```json
{
  "case_id": "route-high-risk-payment",
  "description": "Payment-domain change routes to HIGH tier with security-reviewer",
  "fixture": {
    "lines_changed": 450,
    "files_changed": 3,
    "file_paths": ["src/payment/processor.py", "tests/test_processor.py"],
    "churn_ratio": 0.2,
    "coverage_gap": 0.3
  },
  "steps": [
    {
      "action": "compute_risk_tier",
      "expected": {
        "tier": "HIGH",
        "score_min": 0.50,
        "score_max": 0.75
      }
    }
  ]
}
```

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `case_id` | string | Yes | Unique identifier, kebab-case |
| `description` | string | Yes | What this case validates |
| `fixture` | object | Yes | Input data for the replay |
| `steps` | array | Yes | Ordered actions to replay |
| `steps[].action` | string | Yes | The check to run (from check catalog) |
| `steps[].expected` | object | Yes | Expected output to verify |

## Constraints

- Maximum fixture size: 256 KB
- Maximum steps per case: 80
- Maximum cases in suite: 500
