import re

from psycopg.errors import UniqueViolation

from odoo import api, fields, models
from odoo.exceptions import ConcurrencyError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, remove_accents

_debug = DebugLog(__name__)

_CODE_SEPARATORS = re.compile(r"[^A-Z0-9]+")
_CODE_PROBE_WINDOW = 16
_CODE_CLASH_KEY = re.compile(r"\(code\)=\(([^)]*)\)")


class MixinTag(models.AbstractModel):
    _name = "mixin.tag"
    _inherit = ["mixin.catalog", "mixin.color"]
    _description = "Tag (coloured label with a stable code)"
    _order = "name, id"

    name = fields.Char(string="Tag Name")
    active = fields.Boolean(help="Archive a tag to hide it without deleting it.")
    color = fields.Integer(
        default=lambda self: self._default_color(),
        aggregator=False,
    )
    code = fields.Char(
        compute="_compute_code",
        precompute=True,
        store=True,
        index="btree",
        copy=False,
        readonly=False,
        help="Stable identifier for imports, filters and data files. Unlike the "
        "name it is never translated, so it means the same thing to every "
        "reader.",
    )
    _code_uniq = models.Constraint(
        "unique(code)",
        "A tag with this code already exists.",
    )

    @api.depends("name")
    def _compute_code(self) -> None:
        pending = self.filtered(lambda tag: not tag.code and tag.name)
        self.filtered(lambda tag: not tag.code and not tag.name).code = False
        if not pending:
            _debug.logic(
                "codes_kept", model=self._name, tags=len(self), reason="none_pending"
            )
            return
        codes = self._derive_codes([tag.name for tag in pending], set())
        for tag, code in zip(pending, codes, strict=True):
            tag.code = code

    @api.model_create_multi
    def create(self, vals_list):
        vals_list, derived = self._with_derived_codes(vals_list)
        if not derived:
            return super().create(vals_list)
        try:
            return super().create(vals_list)
        except UniqueViolation as error:
            clash = self._code_clash(error)
            if clash not in derived:
                raise
            _debug.logic("code_claim_lost", model=self._name, code=clash)
            raise ConcurrencyError(
                f"{self._name} code {clash} was claimed by a concurrent transaction"
            ) from error

    def _with_derived_codes(self, vals_list) -> tuple[list, set[str]]:
        if all("code" in vals for vals in vals_list):
            return vals_list, set()
        defaults = self.default_get(["code", "name"])
        if "code" in defaults:
            return vals_list, set()
        default_name = defaults.get("name")
        names = {
            index: name
            for index, vals in enumerate(vals_list)
            if "code" not in vals and (name := vals.get("name", default_name))
        }
        if not names:
            return vals_list, set()
        codes = self._derive_codes(
            list(names.values()),
            {vals["code"] for vals in vals_list if vals.get("code")},
        )
        vals_list = list(vals_list)
        for index, code in zip(names, codes, strict=True):
            vals_list[index] = {**vals_list[index], "code": code}
        return vals_list, set(codes)

    def _derive_codes(self, names: list[str], taken: set[str]) -> list[str]:
        self.flush_model(["code"])
        bases = [self._name_to_code(name) or "TAG" for name in names]
        probed: dict[str, int] = {}
        self._probe_codes(taken, probed, dict.fromkeys(bases, _CODE_PROBE_WINDOW))
        codes = []
        suffixed = 0
        for base in bases:
            suffix = 1
            while True:
                if suffix > probed[base]:
                    self._probe_codes(
                        taken, probed, {base: suffix + _CODE_PROBE_WINDOW - 1}
                    )
                candidate = base if suffix == 1 else f"{base}_{suffix}"
                if candidate not in taken:
                    break
                suffix += 1
            suffixed += suffix > 1
            taken.add(candidate)
            codes.append(candidate)
        _debug.logic(
            "codes_generated",
            model=self._name,
            pending=len(codes),
            taken=len(taken),
            suffixed=suffixed,
        )
        return codes

    def _code_clash(self, error: UniqueViolation) -> str | None:
        if error.diag.constraint_name != self._code_uniq.get_full_name(self):
            return None
        clash = _CODE_CLASH_KEY.search(error.diag.message_detail or "")
        return clash and clash[1]

    def _probe_codes(
        self, taken: set[str], probed: dict[str, int], upto: dict[str, int]
    ) -> None:
        candidates = [
            base if suffix == 1 else f"{base}_{suffix}"
            for base, last in upto.items()
            for suffix in range(probed.get(base, 0) + 1, last + 1)
        ]
        taken.update(
            code
            for [code] in self.env.execute_query(
                SQL(
                    "SELECT code FROM %s WHERE code = ANY(%s)",
                    SQL.identifier(self._table),
                    candidates,
                )
            )
        )
        probed.update(upto)

    @api.model
    def _name_to_code(self, name):
        letters = remove_accents(name or "").upper()
        return _CODE_SEPARATORS.sub("_", letters).strip("_")[:64]
