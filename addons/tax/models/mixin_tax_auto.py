from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MixinTaxAuto(models.AbstractModel):
    _name = "mixin.tax.auto"
    _description = "Automatic Taxes Tracking"

    _NO_TAXES_KEY = "-"

    tax_ids_auto_key = fields.Char(  # noqa: E8520 -- a sorted list of tax ids, not a secret
        string="Automatic Taxes Key",
        copy=True,
        help="The taxes the line would get automatically, as a sorted key. "
        "Compared with tax_ids to detect manual overrides.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line, vals in zip(lines, vals_list, strict=False):
            if "tax_ids" in vals and not line.tax_ids_auto_key:
                line.tax_ids_auto_key = line._tax_key(line._auto_taxes())
        return lines

    @classmethod
    def _tax_key(cls, taxes):
        return (
            ",".join(str(tax_id) for tax_id in sorted(taxes.ids)) or cls._NO_TAXES_KEY
        )

    def _auto_taxes(self):
        raise NotImplementedError(f"{self._name} must implement _auto_taxes()")

    def _apply_auto_taxes(self, auto_taxes) -> None:
        self.check_singleton()
        old_key = self.tax_ids_auto_key
        auto_key = self._tax_key(auto_taxes)
        if old_key and self._tax_key(self.tax_ids) != old_key:
            self.tax_ids_auto_key = auto_key
            _debug.logic(
                "taxes_kept_manual",
                line=self,
                manual=self.tax_ids,
                was_auto_key=old_key,
                now_auto=auto_taxes,
            )
            return
        self.tax_ids = auto_taxes
        self.tax_ids_auto_key = auto_key
