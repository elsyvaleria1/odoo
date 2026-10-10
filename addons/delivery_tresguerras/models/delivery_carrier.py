from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

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
DOCUMENT_HOSTS = {"intranet.tresguerras.com.mx", "www.tresguerras.com.mx"}


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
        answer = _mapping(_mapping(response.json()).get("Respuesta"))
        if _text(answer.get("Error")):
            raise UserError(
                self.env._(
                    "Tres Guerras: %(error)s (%(reference)s).",
                    error=_text(answer["Error"]),
                    reference=reference,
                )
            )
        last = _mapping(answer.get("ultimo_estado"))
        code = _text(last.get("estadoembarque"))
        if not code:
            raise UserError(
                self.env._(
                    "Tres Guerras reports no event for %(reference)s.",
                    reference=reference,
                )
            )
        details = _items(_mapping(answer.get("detalle")).get("item"))
        detail = details[0] if details else {}
        events = [
            {
                "code": _text(event.get("estadoembarque")),
                "text": _text(event.get("estado")),
                "branch": _text(event.get("sucursal")),
                "date": fields.Datetime.to_string(
                    _parse_local_date(event.get("fecha_corta"), event.get("hora"))
                ),
                "received_by": _text(event.get("recibio")),
            }
            for event in _items(_mapping(answer.get("estados")).get("item"))
        ]
        documents = []
        seen = set()
        evidence = _mapping(answer.get("evidencia"))
        for key, kind in (("acuse", "receipt"), ("evidencia", "evidence")):
            for file_format in ("PDF", "IMG"):
                # The app's direct URL avoids the legacy download.php redirect.
                urls = _mapping(_mapping(evidence.get(key)).get(file_format)).get("url")
                if isinstance(urls, str):
                    urls = [urls]
                if urls and not isinstance(urls, list):
                    raise ValueError(
                        "Unexpected document list in the Tres Guerras response."
                    )
                for url in urls or []:
                    url = _document_url(url)
                    if url and url not in seen:
                        seen.add(url)
                        documents.append(
                            {"kind": kind, "format": file_format, "url": url}
                        )
        return {
            "state": STATES.get(code, "other"),
            "code": code,
            "text": _text(last.get("estado")),
            "branch": _text(last.get("sucursal")),
            "date": _parse_local_date(last.get("fecha_corta"), last.get("hora")),
            "kind": KINDS.get(_text(detail.get("BANDERA_EAD"))),
            "estimated": _text(detail.get("entrega_estimada")),
            "received_by": _text(last.get("recibio")),
            "events": sorted(events, key=lambda event: event["date"] or ""),
            "documents": documents,
            "shipment": {
                "service": answer.get("servicio") or "",
                "origin": detail.get("ORIGEN") or "",
                "destination": detail.get("DESTINO") or "",
                "weight": detail.get("PESO") or "",
                "pieces": detail.get("PIEZAS") or "",
                "shipped_on": detail.get("FECHA_DE_EMBARQUE") or "",
            },
        }

    def _is_tracking_document_url(self, url) -> bool:
        if self.tracking_provider == "tresguerras":
            return bool(_document_url(url)) and url.startswith("https://")
        return super()._is_tracking_document_url(url)


def _text(value):
    """Read optional text without accepting compound JSON values."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Unexpected text in the Tres Guerras response.")
    return value.strip()


def _mapping(value):
    """Read an optional object from the carrier's response."""
    if not value:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Unexpected object in the Tres Guerras response.")
    return value


def _items(value):
    """Read the carrier's singleton-or-list collection."""
    if not value:
        return []
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("Unexpected collection in the Tres Guerras response.")
    return value


def _document_url(value):
    """Return an HTTPS document URL on a known carrier host, or None."""
    if (
        not isinstance(value, str)
        or any(ord(char) < 33 for char in value)
        or "\\" in value
    ):
        return None
    try:
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or url.hostname not in DOCUMENT_HOSTS
            or url.username is not None
            or url.password is not None
            or url.port not in {None, 80, 443}
        ):
            return None
    except ValueError:
        return None
    return urlunsplit(("https", url.hostname, url.path, url.query, ""))


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
