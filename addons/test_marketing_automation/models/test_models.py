from odoo import api, fields, models


class MarketingTest(models.Model):
    _name = "marketing.test"
    _description = "MarketAuto: simple thread-enabled model"
    _inherit = ["mixin.mail.thread"]

    name = fields.Char()
    email_from = fields.Char()
    description = fields.Text()
    partner_id = fields.Many2one("res.partner", "Partner")


class MarketingTestPerformance(models.Model):
    _name = "marketing.test.performance"
    _description = "MarketAuto: Model for performance check"
    _inherit = ["mixin.mail.thread.blacklist", "mixin.mail.thread.phone", "mixin.utm"]
    _primary_email = "email_from"
    _order = "id ASC"
    _mail_partner_fields = ("customer_id",)

    name = fields.Char()
    company_id = fields.Many2one("res.company")
    email_from = fields.Char(
        compute="_compute_from_customer", readonly=False, store=True
    )
    phone_ids = fields.Many2many(
        "phone.number",
        "marketing_test_performance_phone_number_rel",
        "record_id",
        "phone_number_id",
        compute="_compute_from_customer",
        readonly=False,
        store=True,
    )
    description = fields.Text()
    customer_id = fields.Many2one("res.partner", "Partner")
    # dummy selection fields to easily write server actions
    selection_field = fields.Selection(
        [("key1", "Key 1"), ("key2", "Key 2"), ("key3", "Key 3")]
    )

    @api.depends("customer_id")
    def _compute_from_customer(self):
        for record in self:
            if not record.email_from and record.customer_id.email:
                record.email_from = record.customer_id.email
            if not record.phone_ids and record.customer_id.phone_ids:
                record.phone_ids = record.customer_id.phone_ids


class MarketingTestUtm(models.Model):
    _name = "marketing.test.utm"
    _description = "MarketAuto: simple thread-enabled model with UTMs"
    _inherit = ["mixin.mail.thread", "mixin.utm"]

    name = fields.Char()
    partner_id = fields.Many2one("res.partner", "Partner")


class MarketingTestSms(models.Model):
    _name = "marketing.test.sms"
    _description = "MarketAuto: blacklist + phone-enabled model"
    _inherit = ["mixin.mail.thread.blacklist", "mixin.mail.thread.phone"]
    _primary_email = "email_from"
    _order = "id ASC"
    _mail_partner_fields = ("customer_id",)

    name = fields.Char()
    active = fields.Boolean(default=True)
    email_from = fields.Char(
        compute="_compute_from_customer", readonly=False, store=True
    )
    phone_ids = fields.Many2many(
        "phone.number",
        "marketing_test_sms_phone_number_rel",
        "record_id",
        "phone_number_id",
        compute="_compute_from_customer",
        readonly=False,
        store=True,
    )
    description = fields.Text()
    customer_id = fields.Many2one("res.partner", "Partner")
    text_trans = fields.Char(translate=True)

    @api.depends("customer_id")
    def _compute_from_customer(self):
        for record in self:
            if not record.email_from and record.customer_id.email:
                record.email_from = record.customer_id.email
            if not record.phone_ids and record.customer_id.phone_ids:
                record.phone_ids = record.customer_id.phone_ids
