from odoo import Command, api, fields, models
from odoo.tools import frozendict


class BaseModuleInstallRequest(models.Model):
    _name = "base.module.install.request"
    _inherit = ["mixin.mail.thread"]
    _description = "Module Activation Request"
    _rec_name = "module_id"
    _order = "create_date desc, id desc"
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    module_id = fields.Many2one(
        comodel_name="ir.module.module",
        readonly=True,
        required=True,
        domain=[("state", "=", "uninstalled")],
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.user,
        readonly=True,
        required=True,
    )
    user_ids = fields.Many2many(
        comodel_name="res.users",
        string="Send to:",
        compute="_compute_user_ids",
    )
    body_html = fields.Html(string="Body")

    @api.depends("module_id")
    def _compute_user_ids(self) -> None:
        users = self.env.ref("base.group_system").all_user_ids
        self.user_ids = [Command.set(users.ids)]

    def action_send_request(self) -> dict:
        self.check_singleton()
        self._send_request()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("Your request has been successfully sent"),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _send_request(self):
        """Tell the administrators. `approval_base_install_request` replaces this
        with an approval request wherever the approval engine is installed."""
        mail_template = self.env.ref(
            "base_install_request.mail_template_base_install_request"
        )
        menu_id = self.env.ref("base.menu_apps").id
        for user in self.user_ids:
            render_ctx = dict(
                self.env.context, partner=user.partner_id, menu_id=menu_id
            )
            mail_template.with_context(render_ctx).send_mail(
                self.id,
                force_send=True,
                email_layout_xmlid="mail.mail_notification_light",
            )
