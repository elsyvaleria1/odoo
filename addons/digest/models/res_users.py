from odoo import Command, api, models
from odoo.tools import str2bool


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users_to_subscribe = users.filtered_domain([("share", "=", False)])
        if not users_to_subscribe:
            return users

        get_param = self.env["ir.config_parameter"].sudo().get_param
        if not str2bool(get_param("digest.default_digest_emails") or "", default=False):
            return users
        default_digest_id = get_param("digest.default_digest_id")
        if not (default_digest_id or "").isdigit():
            return users

        digest = (
            self.env["digest.digest"].sudo().browse(int(default_digest_id)).exists()
        )
        digest.user_ids = [Command.link(user.id) for user in users_to_subscribe]
        return users
