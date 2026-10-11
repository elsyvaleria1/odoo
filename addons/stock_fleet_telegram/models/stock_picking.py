import re

from odoo import api, models
from odoo.libs.text import similarity_ratio
from odoo.tools import remove_accents

_OUT_NAME_RE = re.compile(r"\b([A-Z0-9]{1,8})\s*/\s*OUT((?:\s*/\s*\d+)+)\b")
_CUSTOMER_MATCH_RATIO = 0.6


def _normalize_name(name) -> str:
    return " ".join(remove_accents(name or "").lower().split())


def _compact(text) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def out_names_in_text(text) -> list[str]:
    names = (
        f"{code}/OUT{re.sub(r'\s', '', numbers)}"
        for code, numbers in _OUT_NAME_RE.findall((text or "").upper())
    )
    return list(dict.fromkeys(names))


class StockPicking(models.Model):
    _inherit = "stock.picking"

    @api.model
    def _find_delivery_orders_by_name(self, names):
        names = [name for name in names if name]
        if not names:
            return self.browse()
        return self.search(
            [("name", "in", names), ("picking_type_code", "=", "outgoing")]
        )

    def _get_customer_partners(self):
        self.check_singleton()
        partner = self.partner_id
        return partner | partner.commercial_partner_id

    def _customer_in_text(self, text) -> bool:
        partners = self._get_customer_partners()
        compact = _compact(text)
        if any(
            len(vat) >= 12 and vat in compact
            for vat in (_compact(p.vat) for p in partners)
        ):
            return True
        lines = [_normalize_name(line) for line in (text or "").splitlines()]
        names = {_normalize_name(p.name) for p in partners if p.name}
        return any(
            name in line or similarity_ratio(line, name) >= _CUSTOMER_MATCH_RATIO
            for line in lines
            if line
            for name in names
        )

    def _telegram_delivery_blocker(self, user) -> str:
        self.check_singleton()
        batch = self.batch_id
        if not batch:
            return self.env._("it is not on a trip")
        if not batch.date_departure:
            return self.env._("trip %(trip)s has not departed", trip=batch.display_name)
        if batch.date_return:
            return self.env._(
                "trip %(trip)s is already closed", trip=batch.display_name
            )
        if batch.operator_id.user_id != user:
            return self.env._(
                "only the driver of trip %(trip)s marks it delivered",
                trip=batch.display_name,
            )
        return ""
