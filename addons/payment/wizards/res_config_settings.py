from odoo import api, fields, models
from odoo.fields import Domain


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    active_provider_id = fields.Many2one(
        comodel_name="payment.provider",
        compute="_compute_active_provider_id",
    )
    has_enabled_provider = fields.Boolean(compute="_compute_has_enabled_provider")
    onboarding_payment_module = fields.Selection(
        selection=[
            ("mercado_pago", "Mercado Pago"),
            ("razorpay", "Razorpay"),
            ("stripe", "Stripe"),
        ],
        compute="_compute_onboarding_payment_module",
    )


    @api.depends("company_id")
    def _compute_active_provider_id(self):
        for config in self:
            active_providers_domain = config._get_domain_active_providers()
            if active_providers := self.env["payment.provider"].search(
                active_providers_domain, limit=1
            ):
                config.active_provider_id = active_providers[0]
            else:
                config.active_provider_id = None

    @api.depends("company_id")
    def _compute_has_enabled_provider(self):
        for config in self:
            enabled_providers_domain = config._get_domain_active_providers(
                enabled_only=True
            )
            config.has_enabled_provider = bool(
                self.env["payment.provider"].search(enabled_providers_domain, limit=1)
            )

    def _get_domain_active_providers(self, enabled_only=False):
        return Domain.AND(
            [
                [
                    ("state", "=", "enabled")
                    if enabled_only
                    else ("state", "!=", "disabled")
                ],
                self.env["payment.provider"]._check_company_domain(self.company_id),
            ]
        )

    @api.depends(
        "company_id.currency_id", "company_id.country_id.is_stripe_supported_country"
    )
    def _compute_onboarding_payment_module(self) -> None:
        for config in self:
            if config.company_id.currency_id.name == "INR":
                config.onboarding_payment_module = "razorpay"
            elif config.company_id.country_id.is_stripe_supported_country:
                config.onboarding_payment_module = "stripe"
            elif config.company_id.country_id.is_mercado_pago_supported_country:
                config.onboarding_payment_module = "mercado_pago"
            else:
                config.onboarding_payment_module = None


    def action_view_active_provider(self) -> dict:
        provider = self.active_provider_id.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "payment.provider",
            "views": [[False, "form"]],
            "res_id": provider.id,
        }

    def _start_payment_onboarding(self, menu_id=None):
        self.check_singleton()
        if not self.onboarding_payment_module:
            return False

        onboarding_module = self.env["ir.module.module"].search(
            [("name", "=", f"payment_{self.onboarding_payment_module}")]
        )
        self._install_modules(onboarding_module)
        new_env = api.Environment(self.env.cr, self.env.uid, self.env.context)

        provider_code = self.onboarding_payment_module
        provider = new_env["payment.provider"].search(
            [
                ("code", "=", provider_code),
                *self.env["payment.provider"]._check_company_domain(self.env.company),
            ],
            limit=1,
        )
        if not provider:
            return False

        return provider.action_start_onboarding(menu_id=menu_id)
