import logging
from datetime import timedelta

import requests
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.formatting import format_datetime

_logger = logging.getLogger(__name__)

TRACKING_STATES = [
    ("documented", "Documented"),
    ("in_transit", "In Transit"),
    ("at_destination", "At Destination"),
    ("out_for_delivery", "Out for Delivery"),
    ("delivered", "Delivered"),
    ("other", "Other"),
]
TRACKING_WINDOW = timedelta(days=45)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    carrier_tracking_provider = fields.Selection(
        related="carrier_id.tracking_provider",
    )
    carrier_tracking_state = fields.Selection(
        selection=TRACKING_STATES,
        string="Carrier Status",
        copy=False,
        readonly=True,
        help="Where the carrier last reported the shipment, read on a schedule "
        "from its tracking number.",
    )
    carrier_delivery_kind = fields.Selection(
        selection=[("home", "Home Delivery"), ("pickup", "Pickup at Branch")],
        string="Carrier Service",
        copy=False,
        readonly=True,
    )
    carrier_status_code = fields.Char(
        string="Carrier Event Code",
        copy=False,
        readonly=True,
    )
    carrier_status_text = fields.Char(
        string="Carrier Last Event",
        copy=False,
        readonly=True,
    )
    carrier_status_branch = fields.Char(
        string="Carrier Branch",
        copy=False,
        readonly=True,
    )
    date_carrier_status = fields.Datetime(
        string="Carrier Event Date",
        copy=False,
        readonly=True,
    )
    carrier_estimated_delivery = fields.Char(
        string="Estimated Delivery",
        copy=False,
        readonly=True,
    )
    carrier_received_by = fields.Char(
        string="Received By",
        copy=False,
        readonly=True,
    )
    date_carrier_tracking_sync = fields.Datetime(
        string="Carrier Status Read On",
        copy=False,
        readonly=True,
    )
    carrier_tracking_error = fields.Char(
        string="Carrier Status Error",
        copy=False,
        readonly=True,
    )
    carrier_tracking_details = fields.Json(
        string="Carrier Tracking Details",
        copy=False,
        readonly=True,
    )
    carrier_tracking_details_html = fields.Html(
        string="Shipment History and Documents",
        compute="_compute_carrier_tracking_details_html",
    )

    def write(self, vals):
        if not {"carrier_id", "carrier_tracking_ref"}.intersection(vals):
            return super().write(vals)
        changed = self.filtered(
            lambda picking: (
                ("carrier_id" in vals and vals["carrier_id"] != picking.carrier_id.id)
                or (
                    "carrier_tracking_ref" in vals
                    and vals["carrier_tracking_ref"] != picking.carrier_tracking_ref
                )
            )
        )
        if not changed:
            return super().write(vals)
        reset = dict.fromkeys(
            (
                "carrier_tracking_state",
                "carrier_delivery_kind",
                "carrier_status_code",
                "carrier_status_text",
                "carrier_status_branch",
                "date_carrier_status",
                "carrier_estimated_delivery",
                "carrier_received_by",
                "date_carrier_tracking_sync",
                "carrier_tracking_error",
                "carrier_tracking_details",
                "carrier_validation_error",
            ),
            False,
        )
        super(StockPicking, changed).write(vals | reset)
        changed.activity_unlink(
            ["delivery_tracking.mail_activity_type_carrier_validation"]
        )
        return (
            super(StockPicking, self - changed).write(vals) if self - changed else True
        )

    @api.depends(
        "carrier_tracking_details",
        "carrier_id.tracking_provider",
        "carrier_tracking_ref",
    )
    @api.depends_context("lang", "tz")
    def _compute_carrier_tracking_details_html(self):
        for picking in self:
            content = []
            details = picking.carrier_tracking_details or {}
            for reference in picking._get_carrier_tracking_references():
                if reference not in details:
                    continue
                status = details[reference]
                content.append(
                    Markup("<h4>%s</h4><p>%s</p>") % (reference, status["text"])
                )
                shipment = status.get("shipment") or {}
                labels = (
                    ("service", self.env._("Service")),
                    ("origin", self.env._("Origin")),
                    ("destination", self.env._("Destination")),
                    ("weight", self.env._("Weight (kg)")),
                    ("pieces", self.env._("Packages")),
                    ("shipped_on", self.env._("Shipped On")),
                )
                content.extend(
                    Markup("<p><strong>%s:</strong> %s</p>") % (label, shipment[key])
                    for key, label in labels
                    if shipment.get(key)
                )
                events = status.get("events") or []
                if events:
                    content.append(
                        Markup(
                            '<div class="table-responsive"><table class="table table-sm"><thead><tr>%s</tr></thead><tbody>'
                        )
                        % Markup("").join(
                            Markup("<th>%s</th>") % label
                            for label in (
                                self.env._("Date"),
                                self.env._("Event"),
                                self.env._("Branch"),
                                self.env._("Received By"),
                            )
                        )
                    )
                    content.extend(
                        Markup("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>")
                        % (
                            format_datetime(self.env, event["date"])
                            if event.get("date")
                            else "",
                            event.get("text", ""),
                            event.get("branch", ""),
                            event.get("received_by", ""),
                        )
                        for event in events
                    )
                    content.append(Markup("</tbody></table></div>"))
                else:
                    content.append(
                        Markup("<p>%s</p>")
                        % self.env._("The carrier returned no movement history.")
                    )
                documents = [
                    doc
                    for doc in status.get("documents", [])
                    if picking.carrier_id._is_tracking_document_url(doc.get("url"))
                ]
                content.append(Markup("<h5>%s</h5>") % self.env._("Carrier Documents"))
                if not documents:
                    content.append(
                        Markup("<p>%s</p>")
                        % self.env._(
                            "The carrier has not published documents for this shipment."
                        )
                    )
                for index, document in enumerate(documents, 1):
                    label = (
                        self.env._("Receipt")
                        if document["kind"] == "receipt"
                        else self.env._("Delivery Evidence")
                    )
                    content.append(
                        Markup(
                            '<p><a href="%s" target="_blank" rel="noopener noreferrer">%s %s (%s)</a></p>'
                        )
                        % (
                            document["url"],
                            label,
                            index,
                            document["format"],
                        )
                    )
            picking.carrier_tracking_details_html = Markup("").join(content) or (
                Markup("<p>%s</p>")
                % self.env._(
                    "Refresh tracking to consult the shipment history and documents."
                )
            )

    def action_fetch_carrier_tracking(self) -> None:
        self.check_access("write")
        self._fetch_carrier_tracking()

    @api.model
    def _cron_fetch_carrier_tracking(self) -> None:
        pending = self.search(
            [
                ("carrier_id.tracking_provider", "!=", False),
                ("carrier_tracking_ref", "!=", False),
                ("carrier_tracking_state", "!=", "delivered"),
                ("state", "!=", "cancel"),
                ("create_date", ">=", fields.Datetime.now() - TRACKING_WINDOW),
            ]
        )
        delivered = self.search(
            [
                ("picking_type_id.code", "=", "outgoing"),
                ("picking_type_id.auto_validation_carrier_ids", "!=", False),
                ("carrier_tracking_state", "=", "delivered"),
                ("state", "=", "assigned"),
            ]
        ).filtered(lambda picking: picking._is_carrier_auto_validation_enabled())
        # Failed reads must recover before cached delivery can close a transfer.
        retry = delivered.filtered(
            lambda picking: (
                picking.carrier_tracking_error
                or not all(
                    (picking.carrier_tracking_details or {})
                    .get(reference, {})
                    .get("state")
                    == "delivered"
                    for reference in picking._get_carrier_tracking_references()
                )
            )
        )
        (pending | retry)._fetch_carrier_tracking()
        (delivered - retry)._complete_carrier_deliveries()

    def _fetch_carrier_tracking(self) -> None:
        groups = {}
        for picking in self:
            if picking.carrier_id.tracking_provider and picking.carrier_tracking_ref:
                for reference in picking._get_carrier_tracking_references():
                    groups[picking.carrier_id, reference] = None
        results, errors = {}, {}
        for key in groups:
            carrier, reference = key
            try:
                with self.env.cr.savepoint():
                    status = carrier._fetch_tracking_status(reference)
                    results[carrier, reference] = status | {
                        "date": fields.Datetime.to_string(status["date"]),
                    }
            except (UserError, ValueError, requests.RequestException) as error:
                _logger.info(
                    "Tracking %s with %s failed: %s", reference, carrier.name, error
                )
                errors[carrier, reference] = str(error)
        for picking in self:
            carrier = picking.carrier_id
            references = picking._get_carrier_tracking_references()
            if not carrier.tracking_provider or not references:
                continue
            details = {
                key: value
                for key, value in (picking.carrier_tracking_details or {}).items()
                if key in references
            }
            updated = False
            for reference in references:
                if (carrier, reference) in results:
                    details[reference] = results[carrier, reference]
                    updated = True
            with self.env.cr.savepoint():
                if updated:
                    picking._record_carrier_tracking(
                        carrier,
                        picking._aggregate_carrier_tracking(details, references),
                    )
                picking.write(
                    {
                        "carrier_tracking_details": details,
                        "carrier_tracking_error": "; ".join(
                            f"{reference}: {errors[carrier, reference]}"
                            for reference in references
                            if (carrier, reference) in errors
                        )[:250]
                        or False,
                        "date_carrier_tracking_sync": fields.Datetime.now(),
                    }
                )
        self._complete_carrier_deliveries()

    def _get_carrier_tracking_references(self) -> list[str]:
        self.check_singleton()
        return list(
            dict.fromkeys(
                ref.strip()
                for ref in (self.carrier_tracking_ref or "").split(",")
                if ref.strip()
            )
        )

    def _aggregate_carrier_tracking(self, details, references) -> dict:
        order = [
            "other",
            "documented",
            "in_transit",
            "at_destination",
            "out_for_delivery",
            "delivered",
        ]
        reference = min(details, key=lambda ref: order.index(details[ref]["state"]))
        status = details[reference].copy()
        status["date"] = fields.Datetime.to_datetime(status["date"])
        if len(references) > 1:
            status["text"] = self.env._(
                "%(reference)s: %(event)s (%(count)s tracking numbers)",
                reference=reference,
                event=status["text"],
                count=len(references),
            )
        if len(details) != len(references):
            status.update(state="other", code="", date=None, received_by="")
            status["text"] = self.env._(
                "Waiting for the status of all tracking numbers."
            )
        return status

    def _record_carrier_tracking(self, carrier, status) -> None:
        news = self.filtered(
            lambda picking: (
                (picking.carrier_status_code or "", picking.date_carrier_status or None)
                != (status["code"], status["date"])
            )
        )
        delivered = self.filtered(
            lambda picking: (
                status["state"] == "delivered"
                and picking.carrier_tracking_state != "delivered"
                and picking.state not in ("done", "cancel")
                and not picking._is_carrier_auto_validation_enabled()
            )
        )
        self.write(
            {
                "carrier_tracking_state": status["state"],
                "carrier_status_code": status["code"],
                "carrier_status_text": status["text"],
                "carrier_status_branch": status["branch"],
                "date_carrier_status": status["date"],
                "carrier_delivery_kind": status["kind"],
                "carrier_estimated_delivery": status["estimated"],
                "carrier_received_by": status["received_by"],
                "date_carrier_tracking_sync": fields.Datetime.now(),
                "carrier_tracking_error": False,
            }
        )
        for picking in news:
            picking.message_post(
                body=self.env._(
                    "%(carrier)s · %(code)s %(event)s · %(branch)s · %(date)s",
                    carrier=carrier.name,
                    code=status["code"],
                    event=status["text"],
                    branch=status["branch"],
                    date=format_datetime(self.env, status["date"])
                    if status["date"]
                    else "",
                )
            )
        for picking in delivered:
            user = carrier.tracking_notify_user_id or picking.user_id
            if user:
                picking.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=self.env._(
                        "%(carrier)s delivered it: validate the transfer",
                        carrier=carrier.name,
                    ),
                    user_id=user.id,
                )
