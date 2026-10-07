# REQ-001: Quiz Engine CLI — Requirement Specification

**Change Set:** CS-01ecb4a1  
**Stage:** INTAKE  
**Role:** product-owner  
**Date:** 2026-10-07  
**Status:** READY_FOR_APPROVAL

---

## 1. Requirement Summary

Build a Python command-line quiz engine that lets users create multiple-choice quizzes from JSON files, take them interactively or via batch answers, track attempt history, view statistics, and export quizzes.

## 2. User Stories

### US-001: Create a quiz
**As a** quiz author, **I want to** create a quiz from a JSON file of questions, **so that** I can build quizzes for study or training.
- **Command:** `quiz create <title> --questions <file.json>`
- **AC-001.1:** Reads a JSON file containing a list of question objects.
- **AC-001.2:** Each question must have: `text` (str), `options` (list of exactly 4 strings), `correct_answer` (int 0-3). `explanation` is optional.
- **AC-001.3:** The quiz is assigned an auto-incremented integer ID and stored with `created_at` timestamp.
- **AC-001.4:** Prints confirmation: `"Created quiz {id}: {title} ({n} questions)"`.
- **AC-001.5:** Validates the JSON structure; rejects files with missing fields or invalid `correct_answer` values.
- **AC-001.6:** Rejects empty question lists.

### US-002: List quizzes
**As a** user, **I want to** see all available quizzes, **so that** I can choose one to take.
- **Command:** `quiz list`
- **AC-002.1:** Shows a table with columns: ID, Title, Questions, Best Score.
- **AC-002.2:** Best Score shows the highest percentage from past attempts, or "—" if never taken.
- **AC-002.3:** Empty list prints `"No quizzes available."`.

### US-003: Take a quiz
**As a** user, **I want to** take a quiz and get my score, **so that** I can test my knowledge.
- **Command:** `quiz take <quiz-id> [--shuffle] [--timed <seconds>] [--answers 1,3,2,4]`
- **AC-003.1:** In interactive mode, presents each question with numbered options and waits for input.
- **AC-003.2:** `--answers` flag accepts comma-separated answer indices (0-3) for non-interactive/test mode.
- **AC-003.3:** `--shuffle` randomizes question order but scoring uses original question indices.
- **AC-003.4:** `--timed <seconds>` sets a time limit; unanswered questions count as wrong when time expires.
- **AC-003.5:** Score = (correct / total) * 100, rounded to 1 decimal place.
- **AC-003.6:** Creates an Attempt record with: quiz_id, answers, score, completed_at, time_taken_seconds.
- **AC-003.7:** Prints score and per-question breakdown showing correct/wrong and explanations.
- **AC-003.8:** Validates answer indices are 0-3; rejects invalid values.
- **AC-003.9:** If quiz ID doesn't exist, prints error and exits with code 1.

### US-004: View results
**As a** user, **I want to** see my past attempt history for a quiz, **so that** I can track improvement.
- **Command:** `quiz results <quiz-id>`
- **AC-004.1:** Shows a table of past attempts: Attempt #, Score, Date, Time Taken.
- **AC-004.2:** If no attempts, prints `"No attempts for this quiz."`.
- **AC-004.3:** If quiz ID doesn't exist, prints error and exits with code 1.

### US-005: View statistics
**As a** user, **I want to** see overall statistics, **so that** I know my progress.
- **Command:** `quiz stats`
- **AC-005.1:** Shows: quizzes taken (unique), total attempts, average score, best quiz (title + score), worst quiz (title + score).
- **AC-005.2:** With no attempts, shows `"No quiz attempts yet."`.

### US-006: Export a quiz
**As a** user, **I want to** export a quiz in JSON or CSV format, **so that** I can share or back it up.
- **Command:** `quiz export <quiz-id> --format json|csv`
- **AC-006.1:** JSON format outputs the quiz with all questions and correct answers.
- **AC-006.2:** CSV format outputs: question_id, question_text, option_a, option_b, option_c, option_d, correct_answer, explanation.
- **AC-006.3:** Output goes to stdout (can be redirected to file).
- **AC-006.4:** If quiz ID doesn't exist, prints error and exits with code 1.

## 3. Non-Functional Requirements

- **NFR-001:** Python 3.10+ with stdlib only (no external dependencies).
- **NFR-002:** Storage directory `~/.quiz-engine/` auto-created on first use.
- **NFR-003:** Graceful error handling for corrupted JSON, missing files, invalid inputs.
- **NFR-004:** Exit code 0 on success, 1 on user error. Errors to stderr.
- **NFR-005:** Must include both unit tests and integration tests.

## 4. Assumptions

| ID | Assumption | Impact | Expires |
|----|-----------|--------|---------|
| A-001 | Single-user tool, no concurrency | Simplifies storage | 2027-01-01 |
| A-002 | Quiz IDs and Attempt IDs are never reused | Monotonically increasing | 2027-01-01 |
| A-003 | Questions have exactly 4 options | Simplifies validation and display | 2027-01-01 |

## 5. Out of Scope
- Question editing after quiz creation
- Multi-user / remote sync
- Timed mode with real-time countdown (only elapsed time check)
- Question types other than multiple-choice
- Quiz categories or tagging
