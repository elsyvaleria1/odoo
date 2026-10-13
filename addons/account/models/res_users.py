from odoo import api, models

AUDIT_SUBKEY = "audit"


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _activity_bucket_subkeys(self, model_name, res_ids):
        if model_name != "account.return":
            return super()._activity_bucket_subkeys(model_name, res_ids)
        returns = (
            self.env["account.return"].browse(res_ids).with_context(active_test=False)
        )
        return {
            account_return.id: AUDIT_SUBKEY
            for account_return in returns
            if account_return.return_type_category == AUDIT_SUBKEY
        }

    @api.model
    def _apply_activity_bucket_subkey(self, group, model_name, subkey, res_ids):
        group = super()._apply_activity_bucket_subkey(
            group, model_name, subkey, res_ids
        )
        if model_name != "account.return":
            return group
        group |= {
            "name": self.env._("Audits")
            if subkey == AUDIT_SUBKEY
            else self.env._("Tax Returns"),
            "view_type": "kanban",
            "domain": [
                ("active", "in", [True, False]),
                ("id", "in", res_ids),
            ],
        }
        return group
