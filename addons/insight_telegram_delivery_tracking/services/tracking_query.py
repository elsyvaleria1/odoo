import pytz

from odoo.addons.insight_telegram.services import catalog

ON_THE_WAY = ("documented", "in_transit", "at_destination", "out_for_delivery", "other")


def _when(ask, value) -> str:
    """A stored UTC datetime as the owner reads it: "8 oct 2026 16:09"."""
    local = pytz.UTC.localize(value).astimezone(pytz.timezone(ask.tz))
    return f"{ask.format_day(local.date())} {local:%H:%M}"


def _line(ask, picking, labels) -> str:
    state = labels.get(picking.carrier_tracking_state) or ask.env._("not read yet")
    customer = picking.partner_id.display_name or ask.env._("(none)")
    parts = [
        f"• {picking.carrier_tracking_ref} · {picking.name} · {customer}: **{state}**"
    ]
    if picking.carrier_delivery_kind == "pickup":
        parts.append(ask.env._("Ocurre"))
    if picking.carrier_status_branch:
        parts.append(picking.carrier_status_branch)
    if picking.date_carrier_status:
        parts.append(_when(ask, picking.date_carrier_status))
    if picking.carrier_tracking_state == "delivered":
        if picking.carrier_received_by:
            parts.append(
                ask.env._("received by %(name)s", name=picking.carrier_received_by)
            )
        if picking.state not in ("done", "cancel"):
            parts.append(ask.env._("not validated in Odoo yet"))
    elif picking.carrier_estimated_delivery:
        parts.append(
            ask.env._("expected %(date)s", date=picking.carrier_estimated_delivery)
        )
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
            limit=catalog.MAX_MATCHES,
        )
        if not pickings:
            raise catalog.NotFound(
                ask.env._(
                    "No transfer carries the tracking number «%(ref)s».", ref=reference
                )
            )
        lines = ["**" + ask.env._("Tracking %(ref)s", ref=reference) + "**"]
        lines += [_line(ask, picking, labels) for picking in pickings]
        lines += _freshness(ask, pickings)
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


def _freshness(ask, pickings) -> list:
    """When the carrier status was last read, so a stale answer says so."""
    reads = [date for date in pickings.mapped("date_carrier_tracking_sync") if date]
    if not reads:
        return []
    return [ask.env._("(carrier status read %(when)s)", when=_when(ask, max(reads)))]


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
