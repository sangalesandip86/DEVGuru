# Note Search CLI — Requirements

**Stage:** INTAKE  
**Date:** 2026-10-07

## Commands

| Command | Description |
|---------|-------------|
| `note-search new <title>` | Create note, read content from stdin |
| `note-search list [--tag TAG] [--since YYYY-MM-DD]` | List notes with optional filters |
| `note-search search <query> [--case-sensitive]` | Full-text search with context |
| `note-search show <id>` | Display note content |
| `note-search tag <id> <tag1,tag2,...>` | Add tags to a note |
| `note-search delete <id> [--yes]` | Delete a note |
| `note-search stats` | Show statistics |

## Data Model

- id: auto-increment integer
- title: string
- content: multiline text
- tags: list of lowercase alphanumeric+hyphen strings
- created_at: ISO 8601 timestamp
- updated_at: ISO 8601 timestamp

## Storage

- JSON at `~/.note-search/notes.json`
- Auto-create directory on first use

## Search Behavior

- Case-insensitive by default
- 1 line of context before/after match
- Highlight: `>>>match<<<`
- Exit code 0 if matches, 1 if none

## NFRs

- Python 3.10+, stdlib only
- Graceful error handling
- Exit code 0 success, 1 error
- Unit + integration tests
