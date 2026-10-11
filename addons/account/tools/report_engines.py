import re
from collections.abc import Callable, Collection
from typing import NamedTuple

from odoo.tools import LazyTranslate

_lt = LazyTranslate(__name__)

_CODE = r"[A-Za-z\d.]+"
_TAG = r"tag\((?:\d+|\w+\.\w+)\)"
ACCOUNT_CODES_ENGINE_SPLIT_REGEX = re.compile(r"(?=[+-])")
ACCOUNT_CODES_ENGINE_TERM_REGEX = re.compile(
    r"^(?P<sign>[+-]?)"
    rf"(?P<prefix>([A-Za-z\d.]*|{_TAG})((?=[\\\[])|(?<=[^CD])))"
    rf"(\[(?P<required_tag>{_TAG})\])?"
    rf"(\\\((?P<excluded_prefixes>(({_CODE}|{_TAG})(,({_CODE}|{_TAG}))*)?)\))?"
    r"(?P<balance_character>[DC]?)$"
)
ACCOUNT_CODES_ENGINE_TAG_ID_PREFIX_REGEX = re.compile(
    r"tag\(((?P<id>\d+)|(?P<ref>\w+\.\w+))\)"
)

LEDGER_ENGINES = frozenset({"tax_tags", "account_codes"})


class AccountCodesFormulaError(ValueError):
    def __init__(self, token: str) -> None:
        super().__init__(token)
        self.token = token


class AccountCodesTag(NamedTuple):
    token: str
    ref: str | None
    id: int | None

    @classmethod
    def parse(cls, token: str) -> AccountCodesTag | None:
        if not (match := ACCOUNT_CODES_ENGINE_TAG_ID_PREFIX_REGEX.fullmatch(token)):
            return None
        return cls(token, match["ref"], int(match["id"]) if match["id"] else None)


class AccountCodesTerm(NamedTuple):
    sign: int
    prefix: str
    excluded_prefixes: tuple[str, ...]
    balance_character: str
    tag: AccountCodesTag | None
    required_tag: AccountCodesTag | None
    excluded_tags: tuple[AccountCodesTag, ...]

    @property
    def is_tag(self) -> bool:
        return self.tag is not None

    @property
    def tags(self) -> tuple[AccountCodesTag, ...]:
        return tuple(
            tag
            for tag in (self.tag, self.required_tag, *self.excluded_tags)
            if tag is not None
        )

    @property
    def key(self) -> tuple:
        return (
            self.prefix,
            self.required_tag,
            self.excluded_prefixes,
            self.excluded_tags,
        )

    def matches_account(
        self,
        code: str,
        tag_ids: Collection[int],
        resolve_tag: Callable[[AccountCodesTag], int | None],
    ) -> bool:
        if self.excluded_prefixes and code.startswith(self.excluded_prefixes):
            return False
        if any(resolve_tag(tag) in tag_ids for tag in self.excluded_tags):
            return False
        if self.required_tag and resolve_tag(self.required_tag) not in tag_ids:
            return False
        if self.tag:
            return resolve_tag(self.tag) in tag_ids
        return code.startswith(self.prefix)


def parse_account_codes_formula(formula: str) -> list[AccountCodesTerm]:
    terms = []
    for token in filter(
        None, ACCOUNT_CODES_ENGINE_SPLIT_REGEX.split(formula.replace(" ", ""))
    ):
        match = ACCOUNT_CODES_ENGINE_TERM_REGEX.match(token)
        if not match or not match["prefix"]:
            raise AccountCodesFormulaError(token)
        exclusions = (
            match["excluded_prefixes"].split(",") if match["excluded_prefixes"] else ()
        )
        excluded_tags = tuple(filter(None, map(AccountCodesTag.parse, exclusions)))
        terms.append(
            AccountCodesTerm(
                sign=-1 if match["sign"] == "-" else 1,
                prefix=match["prefix"],
                excluded_prefixes=tuple(
                    exclusion
                    for exclusion in exclusions
                    if not AccountCodesTag.parse(exclusion)
                ),
                balance_character=match["balance_character"],
                tag=AccountCodesTag.parse(match["prefix"]),
                required_tag=AccountCodesTag.parse(match["required_tag"])
                if match["required_tag"]
                else None,
                excluded_tags=excluded_tags,
            )
        )
    return terms


UNDISTR_LINE_NAME = _lt("Result Brought Forward")
