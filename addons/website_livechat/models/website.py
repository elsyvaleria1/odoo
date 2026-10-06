from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    channel_id = fields.Many2one(
        comodel_name="im_livechat.channel",
        string="Website Live Chat Channel",
    )

    def _get_livechat_channel_info(self):
        self.check_singleton()
        if self.channel_id:
            return self.channel_id.sudo()._get_livechat_loader_info()
        return {}
