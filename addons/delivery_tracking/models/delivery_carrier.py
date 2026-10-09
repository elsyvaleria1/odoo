from odoo import fields, models


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    # FIELDS
    tracking_provider = fields.Selection(
        selection=[],
        string="Tracking Provider",
        help="Reads the status of this carrier's tracking numbers on a schedule. "
        "Each carrier connector adds itself here.",
    )
    tracking_notify_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Notify on Delivery",
        domain="[('share', '=', False)]",
        help="Gets a to-do when the carrier reports an open transfer as delivered. "
        "Empty: the transfer's responsible.",
    )

    # BUSINESS METHODS
    def _fetch_tracking_status(self, reference) -> dict:
        """The carrier's current status of one tracking number, normalized.

        :param str reference: the tracking number
        :return: ``state`` (a ``carrier_tracking_state`` value), ``code``,
            ``text``, ``branch``, ``date`` (naive UTC datetime or None),
            ``kind`` (``home``, ``pickup`` or None), ``estimated`` and
            ``received_by``
        :rtype: dict
        :raise UserError: the carrier answered with an error or nothing usable
        """
        self.check_singleton()
        fetch = getattr(self, f"_{self.tracking_provider}_fetch_tracking_status", None)
        if not self.tracking_provider or fetch is None:
            raise NotImplementedError(
                f"{self.tracking_provider!r} implements no tracking status reader"
            )
        return fetch(reference)
