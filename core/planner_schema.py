"""Text parsing and validation for Planner output.
The Planner is expected to output a single JSON object with the following schema:
    {
        "needs_code_change": <bool>,
        "summary": "<1-2 sentences>",
        "steps": ["..."],            // [] when needs_code_change is false
        "files_to_modify": ["..."]   // [] when needs_code_change is false
    }
This module provides:
- Plan dataclass: a validated representation of the Planner's output.
- parse_plan(text): parse and validate the Planner's raw text into a Plan.
Raises PlanParseError on any parsing or validation failure.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

class PlanParseError(Exception):
    """Planner 输出无法解析或不满足 schema 时抛出。"""
    
@dataclass(frozen=True)
class Plan:
    needs_code_change: bool
    summary: str
    steps: tuple[str, ...]
    files_to_modify: tuple[str, ...]
    
    def allowed_files(self) -> frozenset[str]:
        # 本轮暂不强制，先备着给下一轮的 write_file 白名单用
        return frozenset(self.files_to_modify)
    
_Fence_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

def _extract_json(text: str) -> str:
    if not text or not text.strip():
        raise PlanParseError("planner returned empty response")
    
    m = _Fence_RE.search(text)
    if m:
        return m.group(1).strip()
    
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                return text[start : i + 1]
    
    raise PlanParseError("no JSON object found in planner output")

def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise PlanParseError(msg)

def _check_str_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PlanParseError(f"{field} must be a list")
    out: list[str] = []
    for item in value:
        _require(isinstance(item, str), f"{field} items must be strings")
        out.append(item)
    return tuple(out)

def parse_plan(text: str) -> Plan:
    """Parse the Planner's raw text into a validated Plan; raise PlanParseError on failure."""
    raw = _extract_json(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise PlanParseError(f"invalid JSON: {e}") from e
    
    _require(isinstance(data, dict), "top-level JSON must be an object")
    required = {"needs_code_change", "summary", "steps", "files_to_modify"}
    missing = required - data.keys()
    _require(not missing, f"missing keys: {sorted(missing)}")
    needs = data["needs_code_change"]
    summary = data["summary"]
    _require(isinstance(needs, bool), "needs_code_change must be a bool")
    _require(isinstance(summary, str) and summary.strip() != "", "summary must be a non-empty string")
    
    steps = _check_str_list(data["steps"], "steps")
    files = _check_str_list(data["files_to_modify"], "files_to_modify")
    
    if needs:
        _require(len(steps) > 0, "needs_code_change=true requires non-empty steps")
        _require(len(files) > 0, "needs_code_change=true requires non-empty files_to_modify")
    else:
        _require(len(files) == 0, "needs_code_change=false requires empty files_to_modify")

    normalized: list[str] = []
    seen: set[str] = set()
    for p in files:
        norm = Path(p).as_posix()
        if norm and norm not in seen:
            seen.add(norm)
            normalized.append(norm)
    
    return Plan(
        needs_code_change=needs,
        summary=summary.strip(),
        steps=steps,
        files_to_modify=tuple(normalized))
