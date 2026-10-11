from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError


class MailingMailing(models.Model):
    _inherit = "mailing.mailing"

    @api.model
    def default_get(self, fields):
        vals = super().default_get(fields)
        if "subject" in fields and self.env.context.get(
            "default_use_in_marketing_automation", False
        ):
            vals["subject"] = self.env.context.get("default_name")
        return vals

    use_in_marketing_automation = fields.Boolean(
        string="Specific mailing used in marketing campaign",
        default=False,
        help="Marketing campaigns use mass mailings with some specific behavior; this field is used to indicate its statistics may be suspicious.",
    )
    marketing_activity_ids = fields.One2many(
        comodel_name="marketing.activity",
        inverse_name="mass_mailing_id",
        string="Marketing Activities",
        copy=False,
    )

    def convert_links(self):
        res = {}
        done = self.env["mailing.mailing"]
        for mass_mailing in self:
            if self.env.context.get("default_marketing_activity_id"):
                activity = self.env["marketing.activity"].browse(
                    self.env.context["default_marketing_activity_id"]
                )
                vals = {
                    "mass_mailing_id": mass_mailing.id,
                    "campaign_id": activity.campaign_id.utm_campaign_id.id,
                    "source_id": activity.source_id.id,
                    "medium_id": mass_mailing.medium_id.id,
                }
                res[mass_mailing.id] = mass_mailing._shorten_links(
                    mass_mailing.body_html or "",
                    vals,
                    blacklist=["/unsubscribe_from_list", "/view"],
                )
                done |= mass_mailing
        res.update(super(MailingMailing, self - done).convert_links())
        return res

    def _prepare_link_tracker_vals(self) -> ValuesType:
        res = super()._prepare_link_tracker_vals()
        if self.env.context.get("default_marketing_activity_id"):
            activity = self.env["marketing.activity"].browse(
                self.env.context["default_marketing_activity_id"]
            )
            res["campaign_id"] = activity.campaign_id.utm_campaign_id.id
            res["source_id"] = activity.source_id.id
        return res

    def _get_seen_list_extra(self) -> tuple:
        return (
            (
                "LEFT JOIN marketing_trace m ON (s.marketing_trace_id = m.id)"
                " LEFT JOIN marketing_participant mp ON (m.participant_id = mp.id)"
            ),
            "AND (mp.is_test IS NULL OR mp.is_test = false)",
        )

    @api.ondelete(at_uninstall=False)
    def _unlink_if_no_linked_activities(self) -> None:
        protected = self.filtered(lambda m: m.marketing_activity_ids)
        if protected:
            raise UserError(
                self.env._(
                    "Mailings %(mailing_names)s are used in marketing campaigns. You should take care of this before unlinking the mailings.",
                    mailing_names=", ".join(protected.mapped("name")),
                )
            )
