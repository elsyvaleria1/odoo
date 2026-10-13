import re
from collections.abc import Iterator
from dataclasses import dataclass

from ._model_classes import ModelClass, fold

_UNIQUE_COLUMNS = re.compile(
    r"unique\s*(?:nulls\s+not\s+distinct\s*)?\(([^)]*)\)", re.IGNORECASE
)
_NULLS_NOT_DISTINCT = re.compile(r"nulls\s+not\s+distinct", re.IGNORECASE)
_PARTIAL = re.compile(r"\bwhere\b", re.IGNORECASE)
_BARE_COLUMN = re.compile(r"[a-z_][a-z0-9_]*", re.IGNORECASE)

RULE = "null-exempt-composite-unique"


@dataclass(frozen=True)
class Violation:
    path: str
    lineno: int
    model: str
    attribute: str
    columns: tuple[str, ...]
    nullable: tuple[str, ...]
    rule: str = RULE

    def __str__(self) -> str:
        empty = ", ".join(self.nullable)
        cols = ", ".join(self.columns)
        return (
            f"{self.path}:{self.lineno} [{self.rule}] {self.model}.{self.attribute} "
            f"is UNIQUE ({cols}), and {empty} may be NULL; PostgreSQL exempts those "
            f"rows, so the key does not hold for them -- say NULLS NOT DISTINCT if "
            f"it should, or WHERE {self.nullable[0]} IS NOT NULL if the exemption "
            f"is meant"
        )


def resolve_required(classes: list[ModelClass]) -> dict[str, dict[str, bool]]:
    return fold(classes, "required")


def _column_list(text: str) -> str | None:
    start = text.find("(")
    if start < 0:
        return None
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index]
    return None


def _split_top_level(raw: str) -> list[str]:
    parts, depth, current = [], 0, []
    for char in raw:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _columns(text: str) -> tuple[str, ...] | None:
    raw = _column_list(text)
    if raw is None:
        return None
    tokens = _split_top_level(raw)
    columns = []
    for token in tokens:
        bare = token.strip().strip('"').strip("'")
        if not _BARE_COLUMN.fullmatch(bare):
            return None
        columns.append(bare)
    return tuple(columns)


def violations(units: list[tuple[str, list[ModelClass]]]) -> Iterator[Violation]:
    required = resolve_required([cls for _path, classes in units for cls in classes])
    for path, classes in units:
        for info in classes:
            known = required.get(info.model, {})
            for constraint in info.constraints:
                attribute, text = constraint.attribute, constraint.text
                lineno, is_index = constraint.lineno, constraint.is_index
                if not is_index and not _UNIQUE_COLUMNS.search(text):
                    continue
                if _NULLS_NOT_DISTINCT.search(text) or _PARTIAL.search(text):
                    continue
                columns = _columns(text)
                if columns is None or len(columns) < 2:
                    continue
                nullable = tuple(c for c in columns if known.get(c) is False)
                if nullable:
                    yield Violation(
                        path, lineno, info.model, attribute, columns, nullable
                    )
