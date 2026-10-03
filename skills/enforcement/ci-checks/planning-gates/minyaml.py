"""Minimal, stdlib-only YAML-subset loader for plan files and planning policies.

Why a subset loader: plan files and policies must be readable by humans who review them
in PRs, and every gate must run with the standard library only (docs/authoring-conventions.md).
PyYAML is not assumed. The subset below covers everything the schemas need; anything
outside it raises ``YamlSubsetError``, so a file is never silently mis-parsed.

Supported:
  * block mappings (``key: value``, ``key:`` + nested block)
  * block sequences (``- value``, ``- key: value`` with continuation lines)
  * flow sequences / mappings on one line (``[a, "b c", 3]``, ``{a: 1, b: [x]}``)
  * scalars: double-quoted (JSON escapes), single-quoted (``''`` escape), plain,
    ``null``/``~``, ``true``/``false``, integers, floats
  * block scalars ``|`` / ``>`` with optional ``-`` / ``+`` chomping
  * ``#`` comments, a leading ``---``
  * a document that is plain JSON (tried first)

Not supported (raises): anchors/aliases, tags, multi-document streams, multi-line flow
collections, multi-line plain scalars, complex keys.
"""
from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["load", "loads", "YamlSubsetError"]


class YamlSubsetError(ValueError):
    pass


_INT = re.compile(r"^[-+]?\d+$")
_FLOAT = re.compile(r"^[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")
_UNSUPPORTED_START = ("&", "*", "!", "%", "@", "`")


def _strip_comment(s: str) -> str:
    """Remove a trailing comment that is outside quotes."""
    in_s = in_d = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == "'" and not in_d:
            in_s = not in_s
        elif c == '"' and not in_s:
            if in_d and s[i - 1] == "\\":
                pass
            else:
                in_d = not in_d
        elif c == "#" and not in_s and not in_d and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
        i += 1
    return s.rstrip()


def _split_key(s: str) -> tuple[str, str] | None:
    """Split ``key: rest`` at the first mapping colon outside quotes/brackets."""
    in_s = in_d = False
    depth = 0
    for i, c in enumerate(s):
        if c == "'" and not in_d:
            in_s = not in_s
        elif c == '"' and not in_s and (i == 0 or s[i - 1] != "\\"):
            in_d = not in_d
        elif in_s or in_d:
            continue
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        elif c == ":" and depth == 0 and (i + 1 == len(s) or s[i + 1] in " \t"):
            key = s[:i].strip()
            if not key:
                return None
            return _scalar_key(key), s[i + 1:].strip()
    return None


def _scalar_key(key: str) -> str:
    if key[0] in "\"'":
        v = _parse_scalar(key)
        if not isinstance(v, str):
            raise YamlSubsetError(f"unsupported key {key!r}")
        return v
    if key.startswith(("?", "[", "{")):
        raise YamlSubsetError(f"complex keys are not supported: {key!r}")
    return key


def _parse_scalar(s: str) -> Any:
    s = s.strip()
    if s == "":
        return None
    if s[0] in _UNSUPPORTED_START:
        raise YamlSubsetError(f"anchors/aliases/tags are not supported: {s!r}")
    if s[0] in "[{":
        val, rest = _parse_flow(s, 0)
        if s[rest:].strip():
            raise YamlSubsetError(f"trailing content after flow collection: {s!r}")
        return val
    if s[0] == '"':
        if not s.endswith('"') or len(s) < 2:
            raise YamlSubsetError(f"unterminated double-quoted string: {s!r}")
        return json.loads(s)
    if s[0] == "'":
        if not s.endswith("'") or len(s) < 2:
            raise YamlSubsetError(f"unterminated single-quoted string: {s!r}")
        return s[1:-1].replace("''", "'")
    low = s.lower()
    if low in ("null", "~"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if _INT.match(s):
        return int(s)
    if _FLOAT.match(s):
        return float(s)
    return s


def _parse_flow(s: str, i: int) -> tuple[Any, int]:
    """Parse a one-line flow collection starting at s[i]; return (value, next index)."""
    opener = s[i]
    closer = "]" if opener == "[" else "}"
    i += 1
    items: list[Any] = []
    mapping: dict[str, Any] = {}
    while True:
        while i < len(s) and s[i] in " \t":
            i += 1
        if i >= len(s):
            raise YamlSubsetError(f"unterminated flow collection: {s!r}")
        if s[i] == closer:
            return (items if opener == "[" else mapping), i + 1
        if s[i] in "[{":
            val, i = _parse_flow(s, i)
            token_val: Any = val
            key = None
        else:
            j = i
            in_s = in_d = False
            while j < len(s):
                c = s[j]
                if c == "'" and not in_d:
                    in_s = not in_s
                elif c == '"' and not in_s and s[j - 1] != "\\":
                    in_d = not in_d
                elif not in_s and not in_d and c in ",]}":
                    break
                j += 1
            token = s[i:j].strip()
            i = j
            key = None
            if opener == "{":
                kv = _split_key(token)
                if kv is None:
                    raise YamlSubsetError(f"flow mapping entry needs 'key: value': {token!r}")
                key, raw = kv
                if raw.startswith(("[", "{")):
                    token_val, _ = _parse_flow(raw, 0)
                else:
                    token_val = _parse_scalar(raw)
            else:
                token_val = _parse_scalar(token)
        if opener == "[":
            items.append(token_val)
        else:
            if key is None:
                raise YamlSubsetError(f"flow mapping entry needs a key: {s!r}")
            mapping[key] = token_val
        while i < len(s) and s[i] in " \t":
            i += 1
        if i < len(s) and s[i] == ",":
            i += 1


class _Parser:
    def __init__(self, text: str):
        self.raw = text.replace("\r\n", "\n").replace("\t", "    ").split("\n")
        self.pos = 0

    # -- line helpers -------------------------------------------------------------
    def _skip(self) -> None:
        while self.pos < len(self.raw):
            stripped = self.raw[self.pos].strip()
            if stripped == "" or stripped.startswith("#") or stripped == "---":
                self.pos += 1
            else:
                break

    def peek(self) -> tuple[int, str] | None:
        self._skip()
        if self.pos >= len(self.raw):
            return None
        line = self.raw[self.pos]
        indent = len(line) - len(line.lstrip(" "))
        return indent, _strip_comment(line.strip())

    # -- grammar ------------------------------------------------------------------
    def parse_document(self) -> Any:
        first = self.peek()
        if first is None:
            return None
        value = self.parse_block(first[0])
        rest = self.peek()
        if rest is not None:
            raise YamlSubsetError(f"unexpected content at line {self.pos + 1}: {rest[1]!r}")
        return value

    def parse_block(self, indent: int) -> Any:
        nxt = self.peek()
        if nxt is None:
            return None
        ind, text = nxt
        if ind != indent:
            raise YamlSubsetError(f"bad indentation at line {self.pos + 1}")
        if text == "-" or text.startswith("- "):
            return self.parse_seq(indent)
        if _split_key(text) is not None:
            return self.parse_map(indent)
        # a lone scalar document / value
        self.pos += 1
        return _parse_scalar(text)

    def parse_seq(self, indent: int) -> list[Any]:
        out: list[Any] = []
        while True:
            nxt = self.peek()
            if nxt is None or nxt[0] != indent or not (nxt[1] == "-" or nxt[1].startswith("- ")):
                if nxt is not None and nxt[0] > indent:
                    raise YamlSubsetError(f"bad indentation at line {self.pos + 1}")
                return out
            line = self.raw[self.pos]
            rest = nxt[1][1:].strip()
            if rest == "":
                self.pos += 1
                child = self.peek()
                if child is None or child[0] <= indent:
                    out.append(None)
                else:
                    out.append(self.parse_block(child[0]))
                continue
            if _split_key(rest) is not None and rest[0] not in "[{\"'":
                # "- key: value" starts a mapping whose keys sit at the column of `key`.
                col = line.index("-", indent) + 1
                while line[col] == " ":
                    col += 1
                self.raw[self.pos] = " " * col + line[col:]
                out.append(self.parse_map(col))
                continue
            self.pos += 1
            if rest in ("|", "|-", "|+", ">", ">-", ">+"):
                out.append(self.parse_block_scalar(indent, rest))
            else:
                out.append(_parse_scalar(rest))

    def parse_map(self, indent: int) -> dict[str, Any]:
        out: dict[str, Any] = {}
        while True:
            nxt = self.peek()
            if nxt is None or nxt[0] < indent:
                return out
            ind, text = nxt
            if ind > indent:
                raise YamlSubsetError(f"bad indentation at line {self.pos + 1}: {text!r}")
            if text == "-" or text.startswith("- "):
                return out
            kv = _split_key(text)
            if kv is None:
                raise YamlSubsetError(f"expected 'key: value' at line {self.pos + 1}: {text!r}")
            key, rest = kv
            if key in out:
                raise YamlSubsetError(f"duplicate key {key!r} at line {self.pos + 1}")
            self.pos += 1
            if rest == "":
                child = self.peek()
                if child is not None and child[0] > indent:
                    out[key] = self.parse_block(child[0])
                elif child is not None and child[0] == indent and (
                        child[1] == "-" or child[1].startswith("- ")):
                    out[key] = self.parse_seq(indent)
                else:
                    out[key] = None
            elif rest in ("|", "|-", "|+", ">", ">-", ">+"):
                out[key] = self.parse_block_scalar(indent, rest)
            else:
                out[key] = _parse_scalar(rest)

    def parse_block_scalar(self, parent_indent: int, header: str) -> str:
        lines: list[str] = []
        block_indent = None
        while self.pos < len(self.raw):
            line = self.raw[self.pos]
            if line.strip() == "":
                lines.append("")
                self.pos += 1
                continue
            ind = len(line) - len(line.lstrip(" "))
            if ind <= parent_indent:
                break
            if block_indent is None:
                block_indent = ind
            if ind < block_indent:
                break
            lines.append(line[block_indent:])
            self.pos += 1
        while lines and lines[-1] == "" and header[-1] != "+":
            lines.pop()
        if header[0] == ">":
            text, para = [], []
            for ln in lines:
                if ln == "":
                    text.append(" ".join(para))
                    para = []
                else:
                    para.append(ln)
            text.append(" ".join(para))
            body = "\n".join(text)
        else:
            body = "\n".join(lines)
        return body if header.endswith("-") else body + "\n"


def loads(text: str) -> Any:
    stripped = text.lstrip("﻿").strip()
    if stripped.startswith(("{", "[")):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass  # fall through: could be a YAML flow collection
    return _Parser(text.lstrip("﻿")).parse_document()


def load(path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return loads(fh.read())
