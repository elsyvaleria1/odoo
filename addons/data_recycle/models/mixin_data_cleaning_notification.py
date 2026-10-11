from odoo import api, fields, models
from odoo.tools.date_utils import get_timedelta, time_unit_selection


class MixinDataCleaningNotification(models.AbstractModel):

    _name = "mixin.data.cleaning.notification"
    _description = "Data Cleaning Notification"

    _cleaning_mode_field = None

    notify_user_ids = fields.Many2many(
        comodel_name="res.users",
        string="Notify Users",
        default=lambda self: self.env.user,
        domain=lambda self: self._domain_notify_user_ids(),
        help="List of users to notify when there are new records to review",
    )
    notify_interval = fields.Integer(
        string="Notify",
        default=1,
    )
    notify_unit = fields.Selection(
        selection=time_unit_selection("day", "week", "month"),
        string="Notify Frequency Period",
        default="week",
    )
    last_notification = fields.Datetime(readonly=True)

    _check_notify_interval = models.Constraint(
        "CHECK(notify_interval > 0)",
        "The notification frequency should be greater than 0",
    )

    @api.model
    def _domain_notify_user_ids(self) -> list:
        return [("all_group_ids", "in", self.env.ref("base.group_system").id)]

    def _notify_pending_records(self) -> None:
        mode_field = self._cleaning_mode_field
        if not mode_field:
            raise NotImplementedError(
                "%s inherits mixin.data.cleaning.notification without setting "
                "_cleaning_mode_field" % self._name
            )
        for rule in self.filtered(lambda r: r[mode_field] == "manual"):
            if not rule.notify_user_ids or not rule.notify_interval:
                continue
            delta = get_timedelta(rule.notify_interval, rule.notify_unit)
            if (
                rule.last_notification
                and rule.last_notification + delta >= fields.Datetime.now()
            ):
                continue
            if rule._send_notification():
                rule.last_notification = fields.Datetime.now()

    def _send_notification(self):
        self.check_singleton()
        records_count = self._get_count_pending()
        partner_ids = self.notify_user_ids.partner_id.ids
        if not records_count or not partner_ids:
            return False
        self.env["mixin.mail.thread"].sudo().message_notify(
            body=self._get_notification_body(records_count),
            model=self._name,
            partner_ids=partner_ids,
            res_id=self.id,
            subject=self._get_notification_subject(),
        )
        return True


    def _get_count_pending(self):
        raise NotImplementedError

    def _get_notification_body(self, records_count):
        raise NotImplementedError

    def _get_notification_subject(self):
        raise NotImplementedError
