from odoo import api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)

        providers_sudo = (
            self.env["payment.provider"]
            .sudo()
            .search(
                [
                    ("company_id", "=", self.env.user.company_id.id),
                    ("module_state", "=", "installed"),
                ]
            )
        )
        loaded = self.env.registry.loaded_modules
        providers_sudo = providers_sudo.filtered(lambda p: p.module_id.name in loaded)
        for company in companies:
            if company.parent_id:
                continue

            for provider_sudo in providers_sudo:
                provider_sudo.copy({"company_id": company.id})

        return companies
