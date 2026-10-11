import pytz

from odoo import fields

from odoo.addons.insight_telegram.services import catalog

ON_THE_WAY = ("documented", "in_transit", "at_destination", "out_for_delivery", "other")


def _when(ask, value) -> str:
    local = pytz.UTC.localize(value).astimezone(pytz.timezone(ask.tz))
    return f"{ask.format_day(local.date())} {local:%H:%M}"


def _status(picking, reference) -> dict:
    if reference:
        for key, value in (picking.carrier_tracking_details or {}).items():
            if key.upper() == reference:
                return value
        if len(picking._get_carrier_tracking_references()) > 1:
            return {}
    return {
        "state": picking.carrier_tracking_state,
        "text": picking.carrier_status_text,
        "kind": picking.carrier_delivery_kind,
        "branch": picking.carrier_status_branch,
        "date": picking.date_carrier_status,
        "received_by": picking.carrier_received_by,
        "estimated": picking.carrier_estimated_delivery,
    }


def _line(ask, picking, labels, reference=None) -> str:
    status = _status(picking, reference)
    state = labels.get(status.get("state")) or ask.env._("not read yet")
    customer = picking.partner_id.display_name or ask.env._("(none)")
    parts = [
        f"• {reference or picking.carrier_tracking_ref} · {picking.name} · {customer}: **{state}**"
    ]
    if status.get("text"):
        parts.append(status["text"])
    if status.get("kind") == "pickup":
        parts.append(ask.env._("Ocurre"))
    if status.get("branch"):
        parts.append(status["branch"])
    if status.get("date"):
        parts.append(_when(ask, fields.Datetime.to_datetime(status["date"])))
    if status.get("state") == "delivered":
        if status.get("received_by"):
            parts.append(ask.env._("received by %(name)s", name=status["received_by"]))
        if picking.state not in ("done", "cancel"):
            parts.append(ask.env._("not validated in Odoo yet"))
    elif status.get("estimated"):
        parts.append(ask.env._("expected %(date)s", date=status["estimated"]))
    return " · ".join(parts)


def run_tracking(ask):
    Picking = ask.env["stock.picking"]
    labels = dict(
        Picking._fields["carrier_tracking_state"]._description_selection(ask.env)
    )
    domain = [
        ("carrier_tracking_ref", "!=", False),
        ("carrier_id", "!=", False),
        ("state", "!=", "cancel"),
    ]
    domain += ask.filter_domain(
        {
            "company": ("company_id", "res.company", ("name",), None),
            "warehouse": (
                "picking_type_id.warehouse_id",
                "stock.warehouse",
                ("name", "code"),
                None,
            ),
            "partner": ("partner_id", "res.partner", ("name",), None),
        }
    )
    reference = (ask.params.get("reference") or "").strip().upper()
    if reference:
        pickings = Picking.search(
            domain + [("carrier_tracking_ref", "ilike", reference)],
            order="create_date desc",
        ).filtered(
            lambda picking: (
                reference
                in {ref.upper() for ref in picking._get_carrier_tracking_references()}
            )
        )[: catalog.MAX_MATCHES]
        if not pickings:
            raise catalog.NotFound(
                ask.env._(
                    "No transfer carries the tracking number «%(ref)s».", ref=reference
                )
            )
        lines = ["**" + ask.env._("Tracking %(ref)s", ref=reference) + "**"]
        for picking in pickings:
            lines.append(_line(ask, picking, labels, reference))
            lines += _freshness(ask, picking, reference)
        return lines
    on_the_way = Picking.search(
        domain
        + [
            "|",
            ("carrier_tracking_state", "in", ON_THE_WAY),
            ("carrier_tracking_state", "=", False),
        ],
        order="create_date",
    )
    to_validate = Picking.search(
        domain
        + [
            ("carrier_tracking_state", "=", "delivered"),
            ("state", "not in", ("done", "cancel")),
        ],
        order="date_carrier_status",
    )
    lines = [
        "**" + ask.env._("Parcel shipments") + "**",
        ask.env._(
            "On the way: **%(count)s** · delivered by the carrier, not validated: "
            "**%(open)s**",
            count=len(on_the_way),
            open=len(to_validate),
        ),
    ]
    if on_the_way:
        lines.append(ask.env._("On the way, oldest first:"))
        lines += [_line(ask, picking, labels) for picking in on_the_way[: ask.top]]
    if to_validate and not ask.params.get("summary_only"):
        lines.append(ask.env._("Delivered by the carrier, to validate in Odoo:"))
        lines += [_line(ask, picking, labels) for picking in to_validate[: ask.top]]
    lines += _freshness(ask, on_the_way | to_validate)
    return lines


def _freshness(ask, pickings, reference=None) -> list:
    if not pickings:
        return []
    reads = [date for date in pickings.mapped("date_carrier_tracking_sync") if date]
    if any(pickings.mapped("carrier_tracking_error")):
        if reads:
            return [
                ask.env._(
                    "(last update attempt %(when)s; an update failed, showing saved data)",
                    when=_when(ask, max(reads)),
                )
            ]
        return [ask.env._("(an update failed; showing saved data)")]
    if not reads or (reference and not _status(pickings, reference).get("state")):
        return [ask.env._("(carrier status has not been read yet)")]
    lines = [ask.env._("(carrier status read %(when)s)", when=_when(ask, min(reads)))]
    if len(reads) != len(pickings):
        lines.append(ask.env._("(some shipments have not been read yet)"))
    return lines


catalog.QUERIES["tracking"] = catalog.Query(
    "tracking",
    "Parcel shipments sent with a carrier (paquetería, guía, número de guía, "
    "talón, rastreo de guía, Tres Guerras, embarque, Ocurre): where one shipment "
    "is by its tracking number (put it in reference, e.g. TOL01583026), what a "
    "customer has on the way, or every parcel still on the way, waiting at the "
    "destination branch (Ocurre) or delivered by the carrier and not validated. "
    "Not vehicles nor GPS.",
    run_tracking,
    (),
    ("company", "warehouse", "partner"),
    periodic=False,
    requires="stock.picking",
)
