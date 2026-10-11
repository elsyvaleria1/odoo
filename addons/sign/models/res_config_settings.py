from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    sign_terms = fields.Html(
        related="company_id.sign_terms",
        string="Sign Terms & Conditions",
        readonly=False,
    )
    sign_terms_html = fields.Html(
        related="company_id.sign_terms_html",
        string="Sign Terms & Conditions as a Web page",
        readonly=False,
    )
    sign_terms_type = fields.Selection(
        related="company_id.sign_terms_type",
        readonly=False,
    )
    sign_preview_ready = fields.Boolean(
        string="Display sign preview button",
        compute="_compute_sign_terms_preview",
    )

    use_sign_terms = fields.Boolean(
        string="Sign Default Terms & Conditions",
        default=False,
        config_parameter="sign.use_sign_terms",
    )

    group_manage_template_access = fields.Boolean(
        string="Manage template access",
        implied_group="sign.manage_template_access",
    )

    module_sign_emsigner = fields.Boolean(string="Sign with Aadhaar eSign")

    signing_certificate_id = fields.Many2one(
        comodel_name="certificate.certificate",
        related="company_id.signing_certificate_id",
        string="Signing certificate",
        readonly=False,
    )

    @api.depends("sign_terms_type")
    def _compute_sign_terms_preview(self) -> None:
        for setting in self:
            setting.sign_preview_ready = (
                self.env.company.sign_terms_type == "html"
                and setting.sign_terms_type == "html"
            )

    def action_update_sign_terms(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Update Terms & Conditions"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "res.company",
            "view_id": self.env.ref("sign.res_company_view_form_sign_terms", False).id,
            "target": "new",
            "res_id": self.company_id.id,
        }
