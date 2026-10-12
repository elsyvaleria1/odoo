from odoo import api, fields, models

from odoo.addons.base.models.res_partner import _selection_timezones


class WhatsappTestBase(models.Model):
    _name = "whatsapp.test.base"
    _description = "WhatsApp Base Test"
    _inherit = [
        "mixin.mail.thread",
    ]
    _mail_partner_fields = ("customer_id", "guest_ids")

    name = fields.Char("Name")
    country_id = fields.Many2one("res.country", "Country")
    customer_id = fields.Many2one("res.partner", "Customer")
    guest_ids = fields.Many2many("res.partner")
    phone_ids = fields.Many2many(
        "phone.number",
        string="Phone Numbers",
        compute="_compute_phone_ids",
        readonly=False,
        store=True,
    )
    user_id = fields.Many2one(comodel_name="res.users", string="Salesperson")
    datetime = fields.Datetime()
    selection_id = fields.Many2one("whatsapp.test.selection", "Selection")
    selection_field = fields.Selection(
        [
            ("selection_key_1", "Selection Value 1"),
            ("selection_key_2", "Selection Value 2"),
            ("selection_key_3", "Selection Value 3"),
        ],
        string="Selection Field",
        default="selection_key_1",
    )

    @api.depends("customer_id.phone_ids")
    def _compute_phone_ids(self):
        for record in self.filtered(lambda rec: not rec.phone_ids):
            record.phone_ids = record.customer_id.phone_ids

    def _wa_get_safe_phone_fields(self):
        return super()._wa_get_safe_phone_fields() + [
            "customer_id.phone_ids",
            "guest_ids.phone_ids",
        ]


class WhatsappTestNothread(models.Model):
    _name = "whatsapp.test.nothread"
    _description = "WhatsApp NoThread / NoResponsible"

    name = fields.Char("Name")
    country_id = fields.Many2one("res.country", "Country")
    customer_id = fields.Many2one("res.partner", "Customer")
    phone_ids = fields.Many2many(
        "phone.number",
        string="Phone Numbers",
        compute="_compute_phone_ids",
        readonly=False,
        store=True,
    )
    user_id = fields.Many2one("res.users", string="Salesperson")

    @api.depends("customer_id.phone_ids")
    def _compute_phone_ids(self):
        for record in self.filtered(lambda rec: not rec.phone_ids):
            record.phone_ids = record.customer_id.phone_ids


class WhatsappTestNothreadNoname(models.Model):
    _name = "whatsapp.test.nothread.noname"
    _description = "WhatsApp NoThread / NoResponsible /NoName"
    _rec_name = "customer_id"

    country_id = fields.Many2one("res.country", "Country")
    customer_id = fields.Many2one("res.partner", "Customer")
    phone_ids = fields.Many2many(
        "phone.number",
        string="Phone Numbers",
        compute="_compute_phone_ids",
        readonly=False,
        store=True,
    )
    user_id = fields.Many2one("res.users", string="Salesperson")

    @api.depends("customer_id.phone_ids")
    def _compute_phone_ids(self):
        for record in self.filtered(lambda rec: not rec.phone_ids):
            record.phone_ids = record.customer_id.phone_ids


class WhatsappTestResponsible(models.Model):
    _name = "whatsapp.test.responsible"
    _description = "WhatsApp Responsible Test"
    _inherit = [
        "whatsapp.test.base",
    ]

    user_ids = fields.Many2many("res.users", string="Salespersons")


class WhatsappTestSelection(models.Model):
    _name = "whatsapp.test.selection"
    _description = "WhatsApp Selection Test"

    selection_field = fields.Selection(
        [
            ("selection_key_4", "Selection Value 4"),
            ("selection_key_5", "Selection Value 5"),
            ("selection_key_6", "Selection Value 6"),
        ],
        string="Selection Field",
        default="selection_key_4",
    )


class WhatsappTestTimezone(models.Model):
    _name = "whatsapp.test.timezone"
    _description = "WhatsApp Timezone Test"
    _inherit = [
        "whatsapp.test.base",
    ]

    tz = fields.Selection(_selection_timezones, string="Timezone")
