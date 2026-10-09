import logging
from collections import defaultdict
from datetime import timedelta

import requests

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
# a tracking number is no longer read this long after its transfer was created
TRACKING_WINDOW = timedelta(days=45)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # FIELDS
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

    # ACTION METHODS
    def action_fetch_carrier_tracking(self) -> None:
        self._fetch_carrier_tracking()

    # CRON METHODS
    @api.model
    def _cron_fetch_carrier_tracking(self) -> None:
        self.search(
            [
                ("carrier_id.tracking_provider", "!=", False),
                ("carrier_tracking_ref", "!=", False),
                ("carrier_tracking_state", "!=", "delivered"),
                ("state", "!=", "cancel"),
                ("create_date", ">=", fields.Datetime.now() - TRACKING_WINDOW),
            ]
        )._fetch_carrier_tracking()

    # BUSINESS METHODS
    def _fetch_carrier_tracking(self) -> None:
        """Read each transfer's tracking number from its carrier and record the
        status: one call per carrier and number, each in its own savepoint, so
        one bad number never stops the others."""
        groups = defaultdict(self.browse)
        for picking in self:
            if picking.carrier_id.tracking_provider and picking.carrier_tracking_ref:
                # several numbers in one field: the first one is read
                reference = picking.carrier_tracking_ref.split(",")[0].strip()
                groups[picking.carrier_id, reference] |= picking
        for (carrier, reference), pickings in groups.items():
            try:
                with self.env.cr.savepoint():
                    status = carrier._fetch_tracking_status(reference)
                    pickings._record_carrier_tracking(carrier, status)
            except (UserError, ValueError, requests.RequestException) as error:
                _logger.info(
                    "Tracking %s with %s failed: %s", reference, carrier.name, error
                )
                pickings.write(
                    {
                        "carrier_tracking_error": str(error)[:250],
                        "date_carrier_tracking_sync": fields.Datetime.now(),
                    }
                )

    def _record_carrier_tracking(self, carrier, status) -> None:
        """Write a carrier status on the transfers that share its number, post
        what changed and hand an open transfer the carrier delivered to someone
        who validates it."""
        news = self.filtered(
            lambda picking: (
                (picking.carrier_status_code, picking.date_carrier_status)
                != (status["code"], status["date"])
            )
        )
        delivered = self.filtered(
            lambda picking: (
                status["state"] == "delivered"
                and picking.carrier_tracking_state != "delivered"
                and picking.state not in ("done", "cancel")
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
