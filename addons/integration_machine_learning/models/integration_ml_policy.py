from odoo import api, fields, models
from odoo.exceptions import UserError


class IntegrationMlPolicy(models.Model):
    _name = "integration.ml.policy"
    _description = "Machine-Learning Data Policy"
    _order = "company_id, purpose_id"
    _check_company_auto = True

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
    )
    purpose_id = fields.Many2one(
        comodel_name="integration.ml.purpose",
        index=True,
        required=True,
        ondelete="cascade",
    )
    provider_ids = fields.Many2many(
        comodel_name="integration.ml.provider",
        string="Allowed vendors",
        help="The vendors this company lets data of this purpose reach. Empty: none.",
    )
    approved_by_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
    )
    approved_at = fields.Datetime(readonly=True)
    note = fields.Text()

    _company_purpose_uniq = models.Constraint(
        "unique(company_id, purpose_id)",
        "A company has one policy per purpose.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([{**vals, **self._approval_vals()} for vals in vals_list])

    def write(self, vals):
        if "provider_ids" in vals:
            vals = {**vals, **self._approval_vals()}
        return super().write(vals)

    def _approval_vals(self) -> dict:
        return {"approved_by_id": self.env.uid, "approved_at": fields.Datetime.now()}

    @api.model
    def _allowed_providers(self, company_id: int, key: str, providers):
        Purpose = self.env["integration.ml.purpose"]
        lineage = Purpose._lineage(key)
        policies = self.sudo().search(
            [("company_id", "=", company_id), ("purpose_id.key", "in", lineage)]
        )
        by_key = {policy.purpose_id.key: policy for policy in policies}
        governing = next((by_key[k] for k in lineage if k in by_key), None)
        if governing is not None:
            return providers & governing.provider_ids
        if Purpose._is_sensitive(key):
            return providers.browse()
        return providers

    @api.model
    def _check_allowed(self, company, purpose: str, provider=None) -> None:
        Purpose = self.env["integration.ml.purpose"]
        if provider:
            Purpose._get_or_create_by_key(purpose)
            allowed = bool(self._allowed_providers(company.id, purpose, provider))
        else:
            allowed = not Purpose._is_sensitive(purpose)
        if not allowed:
            raise UserError(
                self.env._(
                    "The data policy of %(company)s lets no %(purpose)s request "
                    "reach %(vendor)s.",
                    company=company.name,
                    purpose=purpose,
                    vendor=provider.with_privilege(
                        "integration_machine_learning.privilege_route_ml",
                        reason="a refusal names the vendor it keeps the data from",
                    ).name
                    if provider
                    else self.env._("this vendor"),
                )
            )
