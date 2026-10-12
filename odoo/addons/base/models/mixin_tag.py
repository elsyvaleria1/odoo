import re

from psycopg.errors import UniqueViolation

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, remove_accents

_debug = DebugLog(__name__)

_CODE_SEPARATORS = re.compile(r"[^A-Z0-9]+")
_CODE_PROBE_WINDOW = 16
_CODE_CLAIM_ATTEMPTS = 5
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
        self.flush_model(["code"])
        bases = [self._name_to_code(tag.name) or "TAG" for tag in pending]
        taken = set(self.env.context.get("mixin_tag_taken_codes", ()))
        probed: dict[str, int] = {}
        self._probe_codes(taken, probed, dict.fromkeys(bases, _CODE_PROBE_WINDOW))
        suffixed = 0
        for tag, base in zip(pending, bases, strict=True):
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
            tag.code = candidate
        _debug.logic(
            "codes_generated",
            model=self._name,
            pending=len(pending),
            taken=len(taken),
            suffixed=suffixed,
        )

    @api.model_create_multi
    def create(self, vals_list):
        if all(vals.get("code") for vals in vals_list):
            return super().create(vals_list)
        given = {vals["code"] for vals in vals_list if vals.get("code")}
        taken = set(given)
        for attempt in range(1, _CODE_CLAIM_ATTEMPTS):
            try:
                return self._create_claiming_codes(vals_list, taken)
            except UniqueViolation as error:
                lost = self._lost_code(error)
                if lost is None or lost in taken:
                    raise
                _debug.logic(
                    "code_claim_lost", model=self._name, code=lost, attempt=attempt
                )
                taken.add(lost)
        return self._create_claiming_codes(vals_list, taken)

    def _create_claiming_codes(self, vals_list, taken: set[str]):
        claiming = self.with_context(mixin_tag_taken_codes=frozenset(taken))
        with self.env.cr.savepoint():
            tags = super(MixinTag, claiming).create(vals_list)
        return tags.with_env(self.env)

    def _lost_code(self, error: UniqueViolation) -> str | None:
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
