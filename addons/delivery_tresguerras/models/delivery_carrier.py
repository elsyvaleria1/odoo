from datetime import datetime

import pytz

from odoo import fields, models
from odoo.exceptions import UserError

TRACKING_URL = "https://intranet.tresguerras.com.mx/WS/AppMobile/wsTraV2.php"
TIMEZONE = "America/Mexico_City"
# the carrier's event code (estadoembarque) mapped to carrier_tracking_state;
# 05 and 09 are the destination branch holding it, for pickup or home delivery
STATES = {
    "01": "documented",
    "02": "in_transit",
    "03": "in_transit",
    "04": "in_transit",
    "12": "in_transit",
    "13": "in_transit",
    "14": "in_transit",
    "05": "at_destination",
    "09": "at_destination",
    "06": "out_for_delivery",
    "07": "delivered",
}
KINDS = {"S": "home", "O": "pickup"}


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    # FIELDS
    tracking_provider = fields.Selection(
        selection_add=[("tresguerras", "Tres Guerras")],
        ondelete={"tresguerras": "set null"},
    )

    # BUSINESS METHODS
    def _tresguerras_fetch_tracking_status(self, reference) -> dict:
        response = self.env["ir.egress"].request(
            "GET",
            TRACKING_URL,
            purpose="delivery_tresguerras",
            max_bytes=1_000_000,
            params={"rastreo": reference},
            timeout=(10, 30),
            allow_redirects=False,
        )
        if response.status_code != 200:
            raise UserError(
                self.env._(
                    "Tres Guerras answered HTTP %(status)s for %(reference)s.",
                    status=response.status_code,
                    reference=reference,
                )
            )
        answer = response.json().get("Respuesta") or {}
        if (answer.get("Error") or "").strip():
            raise UserError(
                self.env._(
                    "Tres Guerras: %(error)s (%(reference)s).",
                    error=answer["Error"].strip(),
                    reference=reference,
                )
            )
        last = answer.get("ultimo_estado") or {}
        code = (last.get("estadoembarque") or "").strip()
        if not code:
            raise UserError(
                self.env._(
                    "Tres Guerras reports no event for %(reference)s.",
                    reference=reference,
                )
            )
        detail = (answer.get("detalle") or {}).get("item") or {}
        if isinstance(detail, list):
            detail = detail[0] if detail else {}
        return {
            "state": STATES.get(code, "other"),
            "code": code,
            "text": (last.get("estado") or "").strip(),
            "branch": (last.get("sucursal") or "").strip(),
            "date": _parse_local_date(last.get("fecha_corta"), last.get("hora")),
            "kind": KINDS.get((detail.get("BANDERA_EAD") or "").strip()),
            "estimated": (detail.get("entrega_estimada") or "").strip(),
            "received_by": (last.get("recibio") or "").strip(),
        }


def _parse_local_date(day, hour):
    """The carrier's local "dd/mm/yyyy" and "hh:mm" as a naive UTC datetime,
    or None when either is missing or malformed."""
    try:
        local = datetime.strptime(f"{day} {hour}", "%d/%m/%Y %H:%M")
    except TypeError, ValueError:
        return None
    return (
        pytz.timezone(TIMEZONE)
        .localize(local)
        .astimezone(pytz.UTC)
        .replace(tzinfo=None)
    )
