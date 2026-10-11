import dataclasses
import logging
import os
import typing

from odoo import Command
from odoo.fields import Domain
from odoo.tests.common import TransactionCase, new_test_user

_logger = logging.getLogger(__name__)

LETTERS = {"r": "read", "w": "write", "c": "create", "d": "unlink"}
OPERATIONS = ("read", "write", "create", "unlink")
PATHS = ("check", "filter", "explain")


@dataclasses.dataclass(frozen=True)
class Persona:
    groups: tuple[str, ...] = ()
    company: str = "a"
    companies: tuple[str, ...] = ()
    portal: str | None = None
    public: bool = False

    def __init__(
        self, *groups: str, company="a", companies=(), portal=None, public=False
    ):
        object.__setattr__(self, "groups", groups)
        object.__setattr__(self, "company", company)
        object.__setattr__(self, "companies", tuple(companies) or (company,))
        object.__setattr__(self, "portal", portal)
        object.__setattr__(self, "public", public)


@dataclasses.dataclass(frozen=True)
class Cell:
    model: str
    record: str
    expected: dict[str, frozenset[str]]
    note: str = ""
    finding: str = ""
    needs: str = ""
    installed: dict[str, dict[str, tuple[frozenset[str], frozenset[str]]]] = (
        dataclasses.field(default_factory=dict)
    )
    today: dict[str, dict[str, frozenset[str]]] = dataclasses.field(
        default_factory=dict
    )

    def __init__(
        self,
        model: str,
        record: str,
        note: str = "",
        finding: str = "",
        needs: str = "",
        installed: dict[str, dict[str, str]] | None = None,
        today: dict[str, str | dict[str, str]] | None = None,
        **expected: str,
    ):
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "record", record)
        object.__setattr__(self, "note", note)
        object.__setattr__(self, "finding", finding)
        object.__setattr__(self, "needs", needs)
        object.__setattr__(
            self,
            "installed",
            {
                module: {
                    persona: parse_adjustment(spec) for persona, spec in specs.items()
                }
                for module, specs in (installed or {}).items()
            },
        )
        object.__setattr__(
            self,
            "expected",
            {persona: parse_operations(spec) for persona, spec in expected.items()},
        )
        object.__setattr__(
            self,
            "today",
            {
                persona: {
                    path: parse_operations(
                        spec if isinstance(spec, str) else spec.get(path, "")
                    )
                    for path in PATHS
                }
                for persona, spec in (today or {}).items()
            },
        )
        if self.today and not finding:
            raise ValueError(f"{record}: a deviation from the matrix names its finding")


def parse_operations(spec: str) -> frozenset[str]:
    found = set()
    for token in spec.split():
        if token.startswith("?"):
            found.add(token)
        elif set(token) <= set(LETTERS):
            found.update(LETTERS[letter] for letter in token)
        else:
            found.add(token)
    return frozenset(found)


def parse_adjustment(spec: str) -> tuple[frozenset[str], frozenset[str]]:
    added, withdrawn = set(), set()
    for token in spec.split():
        if token.startswith("-"):
            withdrawn |= parse_operations(token[1:])
        else:
            added |= parse_operations(token)
    return frozenset(added), frozenset(withdrawn)


@dataclasses.dataclass
class Verdict:
    check: bool | None
    filter: bool | None
    explain: bool | None
    trace: str


def recompute(explanation: dict) -> bool:
    if not explanation["model_allowed"]:
        return False
    permitted = any(entry["admits"] for entry in explanation["permissions"])
    guarded = all(entry["admits"] for entry in explanation["guards"])
    own = explanation["own_guard"]
    allowed = permitted and guarded and (own is None or own["admits"])
    for parent in explanation["parents"]:
        allowed = allowed and recompute(parent)
    if explanation["requires"] is not None:
        allowed = allowed and recompute(explanation["requires"])
    return allowed


def describe(explanation: dict) -> str:
    admitting = [e["name"] for e in explanation["permissions"] if e["admits"]]
    refusing = [e["name"] for e in explanation["guards"] if not e["admits"]]
    parts = []
    if not explanation["model_allowed"]:
        parts.append("no permission on the model")
    parts.append(f"admitted by {admitting or 'no permission'}")
    if refusing:
        parts.append(f"refused by {refusing}")
    own = explanation["own_guard"]
    if own is not None and not own["admits"]:
        parts.append("refused by the model's own condition")
    parts.extend(
        f"parent {parent['field']}: {describe(parent)}"
        for parent in explanation["parents"]
        if not recompute(parent)
    )
    if explanation["requires"] is not None and not recompute(explanation["requires"]):
        parts.append(f"requires {explanation['requires']['operation']}")
    return "; ".join(parts)


class AccessMatrixCase(TransactionCase):

    personas: typing.ClassVar[dict[str, Persona]] = {}
    cells: typing.ClassVar[tuple[Cell, ...]] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.test_access_matrix = cls._test_access_matrix

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.companies = {
            "a": env.ref("base.main_company"),
            "b": env["res.company"].create({"name": f"{cls.__name__} B"}),
        }
        cls.partners = {}
        for persona in cls.personas.values():
            if persona.portal and persona.portal not in cls.partners:
                cls.partners[persona.portal] = env["res.partner"].create(
                    {"name": persona.portal, "is_company": True}
                )
        cls.users = {
            name: cls._persona_user(name, persona)
            for name, persona in cls.personas.items()
        }
        cls.records = cls.build()
        empty = sorted(
            name
            for name, record in cls.records.items()
            if record is not None and not record
        )
        if empty:
            raise AssertionError(f"the build left these records empty: {empty}")

    @classmethod
    def _persona_user(cls, name: str, persona: Persona):
        companies = [cls.companies[key] for key in persona.companies]
        values = {
            "company_id": cls.companies[persona.company].id,
            "company_ids": [Command.set([company.id for company in companies])],
        }
        if persona.public:
            return cls.env.ref("base.public_user")
        if persona.portal:
            contact = cls.env["res.partner"].create(
                {"name": name, "parent_id": cls.partners[persona.portal].id}
            )
            return new_test_user(
                cls.env,
                login=f"matrix_{name}",
                groups="base.group_portal",
                partner_id=contact.id,
                **values,
            )
        return new_test_user(
            cls.env,
            login=f"matrix_{name}",
            groups=",".join(("base.group_user", *persona.groups)),
            **values,
        )

    @classmethod
    def build(cls) -> dict:
        return {}

    def _principal(self, persona_name: str):
        persona = self.personas[persona_name]
        return self.env(
            user=self.users[persona_name],
            context=dict(
                self.env.context,
                allowed_company_ids=[
                    self.companies[key].id for key in persona.companies
                ],
                active_test=False,
            ),
        )

    def _installed(self, module: str) -> bool:
        return bool(
            self.env["ir.module.module"].search_count(
                [("name", "=", module), ("state", "=", "installed")]
            )
        )

    def _operations(self, model_name: str) -> tuple[str, ...]:
        verbs = self.env.registry.model_verbs.get(model_name, {})
        return OPERATIONS + tuple(sorted(verbs))

    def ask(self, persona_name: str, record, operation: str) -> Verdict:
        env = self._principal(persona_name)
        target = env[record._name].browse(record.id)
        errors = []

        def answer(question):
            env.invalidate_all()
            env.transaction.access_memo.clear()
            try:
                with self.env.cr.savepoint():
                    return question()
            except Exception as error:
                errors.append(f"{type(error).__name__}: {error}".splitlines()[0])
                return None

        policy = env.registry.access_policy

        def filtered():
            if not policy.model_allowed(env, record._name, operation):
                return False
            if operation == "read":
                return bool(env[record._name].search_count([("id", "=", record.id)]))
            domain = policy.record_domain(env, record._name, operation)
            return bool(
                env[record._name]
                .sudo()
                .with_context(active_test=False)
                .search_count(domain & Domain("id", "=", record.id))
            )

        check = answer(lambda: target.has_access(operation))
        found = answer(filtered)
        explanation = answer(
            lambda: env["ir.access"]._explain_record(target, operation)
        )
        return Verdict(
            check=check,
            filter=found,
            explain=None if explanation is None else recompute(explanation),
            trace="; ".join(errors) if errors else describe(explanation),
        )

    def observed(self) -> str:
        reverse = {operation: letter for letter, operation in LETTERS.items()}
        lines = []
        for name, record in self.records.items():
            if record is None:
                continue
            specs = []
            for persona_name in self.personas:
                allowed = [
                    operation
                    for operation in self._operations(record._name)
                    if self.ask(persona_name, record, operation).check
                ]
                letters = "".join(reverse[o] for o in allowed if o in reverse)
                verbs = [o for o in allowed if o not in reverse]
                if allowed:
                    specs.append(
                        f'{persona_name}="{" ".join([letters, *verbs]).strip()}"'
                    )
            lines.append(f'Cell("{record._name}", "{name}", {", ".join(specs)}),')
        return "\n".join(lines)

    def _test_access_matrix(self):
        if os.environ.get("ACCESS_MATRIX_OBSERVE"):
            _logger.info(
                "observed access matrix of %s:\n%s",
                type(self).__name__,
                self.observed(),
            )
        self.assertTrue(self.cells, "a matrix without cells tests nothing")
        problems = []
        open_findings: set[str] = set()
        cells = 0
        for cell in self.cells:
            adjusted = [
                adjustment
                for adjustments in cell.installed.values()
                for adjustment in adjustments.items()
            ]
            unknown = {*cell.expected, *(name for name, _ in adjusted)} - set(
                self.personas
            )
            self.assertFalse(unknown, f"{cell.record}: unknown persona(s) {unknown}")
            record = self.records.get(cell.record)
            if record is None and cell.needs:
                _logger.info(
                    "%s: %s not asked, it needs %s",
                    type(self).__name__,
                    cell.record,
                    cell.needs,
                )
                continue
            self.assertTrue(record, f"no record {cell.record!r} was built")
            self.assertEqual(record._name, cell.model, cell.record)
            operations = self._operations(cell.model)
            unknown_ops = set().union(
                *cell.expected.values(),
                *(
                    operations_of_pair
                    for module, adjustments in cell.installed.items()
                    if self._installed(module)
                    for pair in adjustments.values()
                    for operations_of_pair in pair
                ),
            ) - set(operations)
            self.assertFalse(
                unknown_ops, f"{cell.record}: not operations {unknown_ops}"
            )
            for persona_name in self.personas:
                intended = cell.expected.get(persona_name, frozenset())
                for module, adjustments in cell.installed.items():
                    if persona_name in adjustments and self._installed(module):
                        added, withdrawn = adjustments[persona_name]
                        intended = (intended | added) - withdrawn
                expected = dict.fromkeys(PATHS, intended)
                if persona_name in cell.today:
                    expected = cell.today[persona_name]
                    open_findings.add(f"{cell.finding} ({cell.model} {cell.record})")
                for operation in operations:
                    cells += 1
                    verdict = self.ask(persona_name, record, operation)
                    wanted = {
                        path: None
                        if f"?{operation}" in expected[path]
                        else operation in expected[path]
                        for path in PATHS
                    }
                    got = {path: getattr(verdict, path) for path in PATHS}
                    if got == wanted:
                        continue
                    problems.append(
                        f"{cell.model} {cell.record} {persona_name} {operation}: "
                        f"matrix={operation in intended} "
                        + " ".join(f"{path}={got[path]}" for path in PATHS)
                        + (
                            f" (today's deviation expects {wanted})"
                            if persona_name in cell.today
                            else ""
                        )
                        + f" -- {verdict.trace}"
                        + (f" [{cell.note}]" if cell.note else "")
                    )
        if open_findings:
            _logger.info(
                "%s: %d cell(s) deviate from the matrix by open findings: %s",
                type(self).__name__,
                len(open_findings),
                "; ".join(sorted(open_findings)),
            )
        _logger.info(
            "%s: %d access cells asked, %d disagree",
            type(self).__name__,
            cells,
            len(problems),
        )
        if problems:
            self.fail(
                f"{len(problems)} of {cells} access cells disagree:\n"
                + "\n".join(problems)
            )
