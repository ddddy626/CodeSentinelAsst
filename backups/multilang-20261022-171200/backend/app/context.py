"""AST bounded source selection with original line mapping.

This selects exact source lines. It does not summarize or rewrite code.
"""

import ast
import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceContext:
    text: str
    source_hash: str
    original_chars: int
    selected_chars: int
    ranges: tuple[tuple[int, int], ...]
    omitted_ranges: tuple[tuple[int, int], ...]


def select_context(source: str, focus_lines: set[int] | None = None,
                   max_chars: int = 12_000) -> SourceContext:
    lines = source.splitlines(keepends=True)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if len(source) <= max_chars:
        return SourceContext(source, digest, len(source), len(source),
                             ((1, max(1, len(lines))),), ())
    tree = ast.parse(source)
    focus = focus_lines or set()
    candidates: list[tuple[int, int, int]] = []
    for node in tree.body:
        start = node.lineno
        end = node.end_lineno or start
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([start, *(item.lineno for item in node.decorator_list)])
        priority = 0 if isinstance(node, (ast.Import, ast.ImportFrom)) else 2
        if any(start <= line <= end for line in focus):
            priority = 1
        candidates.append((priority, start, end))
    selected: list[tuple[int, int]] = []
    used = 0
    for _, start, end in sorted(candidates):
        length = sum(len(line) + len(str(index)) + 3
                     for index, line in enumerate(lines[start - 1:end], start))
        if used + length <= max_chars:
            selected.append((start, end))
            used += length
    # A single oversized symbol must not hide the focused finding entirely.
    covered = {line for start, end in selected for line in range(start, end + 1)}
    for line in sorted(focus - covered):
        start, end = max(1, line - 3), min(len(lines), line + 3)
        length = sum(len(row) + len(str(index)) + 3
                     for index, row in enumerate(lines[start - 1:end], start))
        if used + length <= max_chars:
            selected.append((start, end))
            used += length
    selected.sort()
    kept_lines = {line for start, end in selected for line in range(start, end + 1)}
    omitted: list[tuple[int, int]] = []
    begin = None
    for index in range(1, len(lines) + 2):
        if index <= len(lines) and index not in kept_lines:
            begin = begin or index
        elif begin is not None:
            omitted.append((begin, index - 1))
            begin = None
    text = "".join(f"{index}: {lines[index - 1]}" for index in sorted(kept_lines))
    return SourceContext(text, digest, len(source), len(text),
                         tuple(selected), tuple(omitted))
