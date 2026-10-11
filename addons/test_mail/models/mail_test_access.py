from odoo import api, fields, models, tools
from odoo.fields import Domain


class MailTestAccess(models.Model):

    _description = "Mail Access Test"
    _name = "mail.test.access"
    _inherit = ["mixin.mail.thread.blacklist"]
    _mail_post_access = "write"
    _order = "id DESC"
    _primary_email = "email_from"
    _mail_partner_fields = ("customer_id",)

    name = fields.Char()
    email_from = fields.Char()
    phone_ids = fields.Many2many(comodel_name="phone.number")
    customer_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
    )
    access = fields.Selection(
        selection=[
            ("public", "public"),
            ("logged", "Logged"),
            ("logged_ro", "Logged readonly for portal"),
            ("followers", "Followers"),
            ("internal", "Internal"),
            ("internal_ro", "Internal readonly"),
            ("admin", "Admin"),
        ],
        default="public",
        name="Access",
    )


class MailTestAccessCusto(models.Model):

    _description = "Mail Access Test with Custo"
    _name = "mail.test.access.custo"
    _inherit = ["mixin.mail.thread.blacklist", "mixin.mail.activity"]
    _mail_post_access = "write"
    _order = "id DESC"
    _primary_email = "email_from"
    _mail_partner_fields = ("customer_id",)

    name = fields.Char()
    email_from = fields.Char()
    phone_ids = fields.Many2many(comodel_name="phone.number")
    customer_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
    )
    is_locked = fields.Boolean()
    is_readonly = fields.Boolean()

    @api.model
    def _mail_operation_domains(self, message_operation):
        if message_operation == "create" and not self.env.user._is_admin():
            return {"read": Domain("is_locked", "=", False)}
        if message_operation == "read":
            return {
                "write": Domain("is_locked", "=", True),
                "read": Domain("is_locked", "=", False),
            }
        return super()._mail_operation_domains(message_operation)


class MailTestAccessPublic(models.Model):

    _description = "Access Test Public"
    _name = "mail.test.access.public"
    _inherit = ["mixin.mail.thread"]
    _mail_partner_fields = ("customer_id",)

    name = fields.Char(string="Name")
    customer_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
    )
    email = fields.Char(string="Email")
    phone_ids = fields.Many2many(comodel_name="phone.number")
    is_locked = fields.Boolean()

    def _mail_get_customer_information(self):
        email_key_to_values = super()._mail_get_customer_information()
        for record in self.filtered("email"):
            if not tools.email_normalize(record.email) and len(self) > 1:
                continue
            values = email_key_to_values.setdefault(record.email, {})
            if not values.get("phone"):
                values["phone"] = record.phone_ids[:1].number
        return email_key_to_values
