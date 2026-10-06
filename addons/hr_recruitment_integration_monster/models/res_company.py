from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"
    _CREDENTIAL_FIELDS = {
        "hr_recruitment_monster_password": "hr_recruitment_monster_password",
    }

    hr_recruitment_monster_username = fields.Char(
        string="Monster Identifier",
        groups="base.group_system",
    )
    hr_recruitment_monster_password = fields.Char(
        string="Monster Password",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        groups="base.group_system",
    )
