# Password Vault CLI — Mutation Testing Results

**Project**: `tetaprojects/password-vault-cli/`  
**Date**: 2026-10-07  
**Tests**: 82 (all passing)  

---

## Aggregate Score: 15/18 = 83%

### crypto.py + vault.py — 78% (11/14)

| ID | Mutation | Result | Security Impact |
|----|----------|--------|-----------------|
| PV-1 | PBKDF2 iterations 100K→1 | **SURVIVED** | CRITICAL: makes brute-force trivial |
| PV-2 | Salt length 16→1 | CAUGHT | |
| PV-3 | Key length 32→8 | CAUGHT | |
| PV-4 | SHA-256→MD5 | **SURVIVED** | HIGH: weaker hash, known vulnerabilities |
| PV-5 | Skip uppercase validation | CAUGHT | |
| PV-6 | Skip digit validation | CAUGHT | |
| PV-7 | Min password length 8→4 | **SURVIVED** | HIGH: weak master passwords allowed |
| PV-8 | XOR key not repeated | CAUGHT | |
| PV-9 | Skip session check on get_credential | CAUGHT | |
| PV-10 | Session never expires | CAUGHT | |
| PV-11 | Accept wrong master password | CAUGHT | |
| PV-12 | Skip duplicate service check | CAUGHT | |
| PV-13 | Don't encrypt password (store plaintext) | CAUGHT | |
| PV-14 | Case-sensitive service lookup | CAUGHT | |

### generator.py — 100% (4/4)

| ID | Mutation | Result |
|----|----------|--------|
| PV-16 | Remove special characters from charset | CAUGHT |
| PV-17 | Skip uppercase guarantee in output | CAUGHT |
| PV-18 | Skip digit guarantee in output | CAUGHT |
| PV-19 | Use constant character instead of `secrets.choice` | CAUGHT (infinite loop/timeout) |

---

## Critical Security Findings

### PV-F1: PBKDF2 iteration count not tested (CRITICAL)
**File**: `crypto.py:6`  
Reducing iterations from 100,000 to 1 survives all 82 tests. No test verifies
that the KDF uses a sufficient number of iterations. An attacker modifying this
constant could make brute-force attacks orders of magnitude faster with zero
functional change detected by the test suite.

**Why this matters**: PBKDF2 iteration count is the primary defense against
offline brute-force attacks. Tests verify the crypto roundtrips correctly
(encrypt→decrypt) but not the security parameters of the derivation.

### PV-F2: Hash algorithm not tested (HIGH)
**File**: `crypto.py:16`  
Changing `"sha256"` to `"md5"` survives. Tests verify password hashing
works (hash→verify roundtrip) but not which algorithm is used. MD5 has
known collision vulnerabilities.

### PV-F3: Password minimum length boundary untested (HIGH)
**File**: `crypto.py:45`  
Changing minimum length from 8 to 4 survives. Tests verify that very
short passwords (empty, 1-char) are rejected, but don't test the boundary
at 7 characters (should fail) vs 8 characters (should pass).

---

## Pattern: Security Parameters vs Functional Correctness

The ADLC pipeline produces tests that verify **functional correctness**
(encrypt/decrypt roundtrips, session expiry, authentication) but not
**security parameter adequacy** (iteration counts, algorithm choices,
key lengths). This is a fundamental gap:

| What tests verify | What tests miss |
|-------------------|-----------------|
| Password hashing roundtrips | Which hash algorithm is used |
| Encryption/decryption works | Whether encryption uses enough iterations |
| Min length is enforced | Where the exact length boundary is |
| Session expiry works | Whether TTL is reasonable (could be set to 1 year) |
| Salt is used | Whether salt is long enough (caught: 16→1 detected) |

**Recommendation**: For security-sensitive projects, the ADLC pipeline
should generate "security parameter assertion" tests that verify constants
like iteration counts, algorithm names, and key/salt lengths against
minimum thresholds.
