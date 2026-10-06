from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    sdd_mandate_ids = fields.One2many(
        comodel_name="sdd.mandate",
        inverse_name="partner_id",
        help="Every mandate belonging to this partner.",
    )
    sdd_count = fields.Integer(
        string="SDD count",
        compute="_compute_sdd_count",
    )

    def _compute_sdd_count(self) -> None:
        sdd_data = (
            self.env["sdd.mandate"]
            .with_privilege(
                "account_sepa_direct_debit.privilege_count_sdd_mandates",
                reason="the mandates counted on a partner, for any reader of it",
            )
            ._read_group(
                domain=[("partner_id", "in", self.ids)],
                groupby=["partner_id"],
                aggregates=["__count"],
            )
        )
        mapped_data = {partner.id: count for partner, count in sdd_data}
        for partner in self:
            partner.sdd_count = mapped_data.get(partner.id, 0)

    def _get_account_statistics_count(self):
        return super()._get_account_statistics_count() + self.sdd_count

    def action_view_ssd_mandates(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "account_sepa_direct_debit.account_sepa_direct_debit_mandate_tree_act"
        )
        action["context"] = {
            "default_partner_id": self.id,
            "search_default_account_sdd_mandate_active_filter": 1,
        }
        action["domain"] = [("partner_id", "=", self.id)]
        return action
