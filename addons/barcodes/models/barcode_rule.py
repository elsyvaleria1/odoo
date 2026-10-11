import functools
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

NUMERIC_GROUP = re.compile(r"[{](?P<whole>N*)(?P<decimal>D*)[}]")
_ESCAPE = re.compile(r"\\.", re.DOTALL)
_NUMBERED_BACKREFERENCE = re.compile(r"\\[1-9]")

_UNBOUNDED = r"(?:[+*]|\{\d+,\d*\})"
_NESTED_QUANTIFIER = re.compile(rf"\([^()]*{_UNBOUNDED}[^()]*\)\s*{_UNBOUNDED}")

_QUANTIFIED_GROUP = re.compile(rf"\((?P<body>[^()]*)\)\s*{_UNBOUNDED}")
_LITERAL_ALTERNATIVE = re.compile(r"^[A-Za-z0-9]+$")

_PORTABLE_GROUP_PREFIX = re.compile(r"\(\?(?:[:=!]|<[=!])")
_PORTABLE_ESCAPE = re.compile(
    r"\\(?:[dDwWsSbBfnrtv0-9]|x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|[^0-9A-Za-z])"
)
_NESTED_SET_TOKENS = ("[", "--", "&&", "~~", "||")
RULE_REGEX_FLAGS = re.ASCII

_BROWSER_WHITESPACE = (
    r"\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)
_BROWSER_EQUIVALENTS = {
    ".": r"[^\n\r\u2028\u2029]",
    "$": r"\Z",
    r"\s": f"[{_BROWSER_WHITESPACE}]",
    r"\S": f"[^{_BROWSER_WHITESPACE}]",
}


@functools.lru_cache(maxsize=1024)
def browser_semantics(pattern) -> str:
    out, i = [], 0
    while i < len(pattern):
        char = pattern[i]
        if char == "\\":
            escape = pattern[i : i + 2]
            out.append(_BROWSER_EQUIVALENTS.get(escape, escape))
            i += 2
        elif char == "[":
            end = _class_end(pattern, i)
            out.append(_ESCAPE.sub(_class_escape, pattern[i:end]))
            i = end
        else:
            out.append(_BROWSER_EQUIVALENTS.get(char, char))
            i += 1
    return "".join(out)


def _class_end(pattern, start):
    i = start + 1
    if pattern[i : i + 1] == "^":
        i += 1
    if pattern[i : i + 1] == "]":
        i += 1
    while i < len(pattern) and pattern[i] != "]":
        i += 2 if pattern[i] == "\\" else 1
    return i + 1


def _class_escape(escape):
    return _BROWSER_WHITESPACE if escape.group() == r"\s" else escape.group()


@functools.lru_cache(maxsize=1024)
def rule_regex(pattern) -> tuple:
    pattern = browser_semantics(pattern)
    numeric_group = NUMERIC_GROUP.search(pattern)
    if not numeric_group:
        return pattern, None
    whole_size = len(numeric_group.group("whole"))
    size = whole_size + len(numeric_group.group("decimal"))
    regex = (
        pattern[: numeric_group.start()]
        + f"(?P<value>[0-9]{{{size}}})"
        + pattern[numeric_group.end() :]
    )
    return regex, whole_size


def unportable_construct(pattern):
    i, previous_is_quantifier, closed_lookaround = 0, False, False
    lookarounds = []
    while i < len(pattern):
        char = pattern[i]
        if closed_lookaround and char in "*+?":
            return pattern[i - 1 : i + 1]
        closed_lookaround = False
        if char == "\\":
            escape = _PORTABLE_ESCAPE.match(pattern, i)
            if not escape:
                return pattern[i : i + 2]
            i, previous_is_quantifier = escape.end(), False
            continue
        if char == "[":
            end, construct = _scan_class(pattern, i)
            if construct:
                return construct
            i, previous_is_quantifier = end, False
            continue
        if char == "(":
            prefix = _PORTABLE_GROUP_PREFIX.match(pattern, i)
            if pattern.startswith("(?", i) and not prefix:
                return pattern[i : i + 3]
            lookarounds.append(bool(prefix) and prefix.group() != "(?:")
            i = prefix.end() if prefix else i + 1
            previous_is_quantifier = False
            continue
        if char == ")":
            closed_lookaround = bool(lookarounds) and lookarounds.pop()
        elif char == "+" and previous_is_quantifier:
            return pattern[i - 1 : i + 1]
        previous_is_quantifier = char in "*+?" and not previous_is_quantifier
        i += 1
    return None


def _scan_class(pattern, start) -> tuple:
    i = start + 1
    if pattern[i : i + 1] == "^":
        i += 1
    if pattern[i : i + 1] == "]":
        return i + 1, pattern[start : i + 1]
    while i < len(pattern) and pattern[i] != "]":
        if pattern[i] == "\\":
            escape = _PORTABLE_ESCAPE.match(pattern, i)
            if not escape or escape.group() == r"\S":
                return i + 2, pattern[i : i + 2]
            i = escape.end()
            continue
        for token in _NESTED_SET_TOKENS:
            if pattern.startswith(token, i):
                return i + len(token), token
        i += 1
    return i + 1, None


def _has_ambiguous_alternation(pattern) -> bool:
    for group in _QUANTIFIED_GROUP.finditer(pattern):
        alternatives = group.group("body").split("|")
        if len(alternatives) < 2 or not all(
            _LITERAL_ALTERNATIVE.match(alt) for alt in alternatives
        ):
            continue
        for i, alt in enumerate(alternatives):
            if any(
                alt.startswith(other) or other.startswith(alt)
                for other in alternatives[i + 1 :]
            ):
                return True
    return False


class BarcodeRule(models.Model):
    _name = "barcode.rule"
    _description = "Barcode Rule"
    _order = "sequence asc, id"

    name = fields.Char(
        string="Rule Name",
        required=True,
        help="An internal identification for this barcode nomenclature rule",
    )
    barcode_nomenclature_id = fields.Many2one(
        comodel_name="barcode.nomenclature",
        index="btree_not_null",
    )
    sequence = fields.Integer(
        help="Used to order rules such that rules with a smaller sequence match first"
    )
    encoding = fields.Selection(
        selection=[
            ("any", "Any"),
            ("ean13", "EAN-13"),
            ("ean8", "EAN-8"),
            ("upca", "UPC-A"),
        ],
        default="any",
        required=True,
        help="This rule will apply only if the barcode is encoded with the specified encoding",
    )
    type = fields.Selection(
        selection=[
            ("alias", "Alias"),
            ("product", "Unit Product"),
        ],
        default="product",
        required=True,
    )
    pattern = fields.Char(
        string="Barcode Pattern",
        default=".*",
        required=True,
        help="The barcode matching pattern",
    )
    alias = fields.Char(help="The matched pattern will alias to this barcode")

    @api.constrains("type", "alias")
    def _check_alias(self) -> None:
        for rule in self:
            if rule.type == "alias" and not rule.alias:
                raise ValidationError(
                    self.env._(
                        "Barcode rule %(name)s is an alias rule, so it needs an alias to point at.",
                        name=rule.name,
                    )
                )

    @api.constrains("pattern")
    def _check_pattern(self) -> None:
        for rule in self:
            rule._check_pattern_syntax()

    def _check_pattern_syntax(self) -> None:
        pattern = self.pattern
        if pattern == "*":
            raise ValidationError(
                self.env._(
                    " '*' is not a valid Regex Barcode Pattern. Did you mean '.*'?"
                )
            )
        structure = _ESCAPE.sub("X", pattern)
        braces = [char for char in structure if char in "{}"]
        if braces:
            if len(braces) != 2:
                raise ValidationError(
                    self.env._(
                        "There is a syntax error in the barcode pattern %(pattern)s: a rule can only contain one pair of braces.",
                        pattern=pattern,
                    )
                )
            if not NUMERIC_GROUP.search(structure):
                raise ValidationError(
                    self.env._(
                        "There is a syntax error in the barcode pattern %(pattern)s: braces can only contain N's followed by D's.",
                        pattern=pattern,
                    )
                )
            if "{}" in structure:
                raise ValidationError(
                    self.env._(
                        "There is a syntax error in the barcode pattern %(pattern)s: empty braces.",
                        pattern=pattern,
                    )
                )
            if any(
                _NUMBERED_BACKREFERENCE.fullmatch(escape)
                for escape in _ESCAPE.findall(pattern)
            ):
                raise ValidationError(
                    self.env._(
                        "The barcode pattern %(pattern)s refers back to a group by number, which the value braces would renumber.",
                        pattern=pattern,
                    )
                )
        self._check_pattern_portability()
        try:
            re.compile(rule_regex(pattern)[0], RULE_REGEX_FLAGS)
        except re.error as e:
            raise ValidationError(
                self.env._(
                    "The barcode pattern %(pattern)s does not lead to a valid regular expression.",
                    pattern=pattern,
                )
            ) from e
        self._check_pattern_backtracking()

    def _check_pattern_portability(self) -> None:
        if construct := unportable_construct(self.pattern):
            raise ValidationError(
                self.env._(
                    "The barcode pattern %(pattern)s uses %(construct)s, which the browser does not read as the server does: "
                    "the point of sale and the barcode app match patterns in the browser.",
                    pattern=self.pattern,
                    construct=construct,
                )
            )

    def _check_pattern_backtracking(self) -> None:
        bare_pattern = NUMERIC_GROUP.sub("", _ESCAPE.sub("X", self.pattern))
        if _NESTED_QUANTIFIER.search(bare_pattern):
            raise ValidationError(
                self.env._(
                    "The barcode pattern %(pattern)s nests one repetition inside another (for instance '(x+x+)+'). "
                    "Such a pattern can take exponentially long to match and would block the server on every scan.",
                    pattern=self.pattern,
                )
            )
        if _has_ambiguous_alternation(bare_pattern):
            raise ValidationError(
                self.env._(
                    "The barcode pattern %(pattern)s repeats a group whose alternatives share a prefix (for instance '(a|aa)+'). "
                    "Such a pattern can take exponentially long to match and would block the server on every scan.",
                    pattern=self.pattern,
                )
            )
