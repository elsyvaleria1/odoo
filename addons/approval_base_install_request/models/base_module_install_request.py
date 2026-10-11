from odoo import models
from odoo.exceptions import UserError


class BaseModuleInstallRequest(models.Model):
    _name = "base.module.install.request"
    _inherit = ["base.module.install.request", "mixin.approval"]

    def _send_request(self):
        self.action_create_approval_request()

    def action_open_install_review(self) -> dict:
        self.check_singleton()
        if self.approval_state != "approved":
            raise UserError(
                self.env._("This activation request has not been approved.")
            )
        return {
            **self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
                "base_install_request.action_base_module_install_review"
            ),
            "context": {"default_module_id": self.module_id.id},
        }

    def _get_approval_category_xmlid(self) -> str:
        return "approval_base_install_request.approval_category_module_activation"

    def _get_fields_approval_protected(self):
        return ["module_id", "body_html"]

    def _get_approval_reason_html(self):
        return self.body_html or ""

    def _is_approval_acted_on(self) -> bool:
        self.check_singleton()
        return self.module_id.state in ("installed", "to upgrade")

    def _on_approval_approved(self) -> None:
        super()._on_approval_approved()
        for request in self:
            request.message_post(
                body=self.env._(
                    "Activation of %(module)s was approved. An administrator "
                    "installs it from this request.",
                    module=request.module_id.shortdesc,
                ),
                partner_ids=request.user_id.partner_id.ids,
                message_type="notification",
            )
