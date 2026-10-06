import re
from collections.abc import Iterator
from dataclasses import dataclass

from ._model_classes import ModelClass, fold

_UNIQUE_COLUMNS = re.compile(
    r"unique\s*(?:nulls\s+not\s+distinct\s*)?\(([^)]*)\)", re.IGNORECASE
)
_INDEX_COLUMNS = re.compile(r"^\s*\(([^)]*)\)")
_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*", re.IGNORECASE)


@dataclass(frozen=True)
class Violation:
    path: str
    lineno: int
    model: str
    attribute: str
    columns: tuple[str, ...]
    rule: str = "unique-over-translated-column"

    def __str__(self) -> str:
        cols = ", ".join(self.columns)
        return (
            f"{self.path}:{self.lineno} [{self.rule}] {self.model}.{self.attribute} "
            f"is UNIQUE over translated column(s) {cols}; it compares jsonb "
            f"documents, not values -- use name_uniq_index()"
        )


def resolve_translated(classes: list[ModelClass]) -> dict[str, set[str]]:
    return {
        model: {name for name, translated in fields_.items() if translated}
        for model, fields_ in fold(classes, "translate").items()
    }


def _columns(text: str, is_index: bool) -> tuple[str, ...]:
    match = (_INDEX_COLUMNS if is_index else _UNIQUE_COLUMNS).search(text)
    if not match:
        return ()
    return tuple(
        token.strip().strip('"').strip("'") for token in match.group(1).split(",")
    )


def violations(units: list[tuple[str, list[ModelClass]]]) -> Iterator[Violation]:
    translated = resolve_translated(
        [cls for _path, classes in units for cls in classes]
    )
    for path, classes in units:
        for info in classes:
            model_fields = translated.get(info.model, set())
            if not model_fields:
                continue
            lowered = {name.lower() for name in model_fields}
            for constraint in info.constraints:
                attribute, text = constraint.attribute, constraint.text
                lineno, is_index = constraint.lineno, constraint.is_index
                if "->>" in text:
                    continue
                if not is_index and not _UNIQUE_COLUMNS.search(text):
                    continue
                columns = _columns(text, is_index)
                if is_index:
                    columns = tuple(
                        token
                        for column in columns
                        for token in _IDENTIFIER.findall(column)
                    )
                hit = tuple(c for c in columns if c.lower() in lowered)
                if hit:
                    yield Violation(path, lineno, info.model, attribute, hit)
