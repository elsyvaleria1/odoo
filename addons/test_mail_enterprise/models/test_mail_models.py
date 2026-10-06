from odoo import fields, models


class MailTestActivityBlSmsVoip(models.Model):
    """A model inheriting from most phone- and mail- related mixin in order
    to test activities with a full setup."""

    _name = "mail.test.activity.bl.sms.voip"
    _description = "VOIP SMS Mailing Blacklist Enabled with activities"
    _inherit = [
        "mixin.mail.thread.blacklist",
        "mixin.mail.thread.phone",
        "mixin.mail.activity",
        "mixin.voip.queue",
    ]
    _mailing_enabled = True
    _order = "name asc, id asc"
    _primary_email = "email_from"
    _mail_partner_fields = ("customer_id",)

    name = fields.Char()
    subject = fields.Char()
    customer_id = fields.Many2one("res.partner", "Customer")
    email_from = fields.Char()
    mobile_nbr_ids = fields.Many2many(
        "phone.number",
        "mail_test_activity_bl_sms_voip_mobile_nbr_rel",
        "record_id",
        "phone_number_id",
    )
    opt_out = fields.Boolean()
    phone_nbr_ids = fields.Many2many(
        "phone.number",
        "mail_test_activity_bl_sms_voip_phone_nbr_rel",
        "record_id",
        "phone_number_id",
    )

    def _mailing_get_opt_out_list(self, mailing):
        res_ids = mailing._get_recipients()
        return set(
            self.search(
                [
                    ("id", "in", res_ids),
                    ("opt_out", "=", True),
                ]
            ).mapped("email_normalized")
        )

    def _mailing_get_opt_out_list_sms(self, mailing):
        res_ids = mailing._get_recipients()
        return self.search(
            [
                ("id", "in", res_ids),
                ("opt_out", "=", True),
            ]
        ).ids

    def _get_phone_number_fields(self):
        return ["phone_nbr_ids", "mobile_nbr_ids"]
