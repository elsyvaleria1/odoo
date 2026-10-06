# The rules test_lint still runs over Python: the two that read every model of a
# repository at once, and the scan's own failure to read a file. The per-file
# AST rules are the ruff fork's (`E85`, Agro-Marin/ruff), held to the same
# floors by lint_ruff_gates.py.
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    lineno: int
    rule: str
    message: str = ""
    col_offset: int = 0

    def __str__(self) -> str:
        tail = f" {self.message}" if self.message else ""
        return f"{self.path}:{self.lineno}:{self.col_offset} [{self.rule}]{tail}"

    @property
    def sort_key(self) -> tuple[str, int, int, str]:
        return (self.path, self.lineno, self.col_offset, self.rule)


@dataclass(frozen=True, slots=True)
class Source:
    path: str
    in_module: bool
    repo: str = "odoo"


def is_test_path(path: str) -> bool:
    return any(part == "tests" or part.startswith("test_") for part in path.split("/"))


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    code: str
    advice: str

    @property
    def gate(self) -> str:
        return "lint_" + self.name.replace("-", "_")


RULES: tuple[Rule, ...] = (
    Rule(
        "unique-over-translated-column",
        "E8512",
        "a translated column is jsonb, so UNIQUE over it compares whole "
        "translation documents and stops matching as soon as one row carries a "
        "language the other does not -- declare name_uniq_index(...) from "
        "odoo/addons/base/models/catalog_mixin.py instead, which indexes the "
        "source term",
    ),
    Rule(
        "null-exempt-composite-unique",
        "E8517",
        "a composite UNIQUE naming a column that may be NULL enforces nothing on "
        "the rows where it is empty, because PostgreSQL counts NULLs as distinct "
        "-- say NULLS NOT DISTINCT if the key must hold there, or make the "
        "exemption explicit with a partial WHERE <column> IS NOT NULL",
    ),
    Rule(
        "unreadable-source",
        "",
        "the scan could not parse or tokenise this file, so every other rule "
        "silently skipped it; fix the file or take it out of the corpus",
    ),
)

BY_NAME: dict[str, Rule] = {rule.name: rule for rule in RULES}

CROSS_UNIT_RULES = frozenset(
    {
        "unique-over-translated-column",
        "null-exempt-composite-unique",
        "unreadable-source",
    }
)
