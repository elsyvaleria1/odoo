from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    hr_referral_level_id = fields.Many2one(
        comodel_name="hr.referral.level",
        groups="hr.group_hr_user",
    )
    hr_referral_onboarding_page = fields.Boolean(groups="hr.group_hr_user")
    referral_point_ids = fields.One2many(
        comodel_name="hr.referral.points",
        inverse_name="ref_user_id",
    )
    utm_source_id = fields.Many2one(
        comodel_name="utm.source",
        string="Source",
        ondelete="restrict",
    )

    @api.model
    def action_complete_onboarding(self, complete) -> None:
        if not self.env.user:
            return
        self.env.user.hr_referral_onboarding_page = bool(complete)

    def _clean_responsibles(self) -> None:
        reward_responsible_group = self.env.ref(
            "hr_referral.group_hr_referral_reward_responsible_user",
            raise_if_not_found=False,
        )
        if not self or not reward_responsible_group:
            return
        res = self.env["hr.referral.reward"]._read_group(
            [("gift_manager_id", "in", self.ids)], ["gift_manager_id"]
        )
        responsibles_to_remove_ids = set(self.ids) - {
            gift_manager.id for [gift_manager] in res
        }
        self.env["res.users.grant"].with_privilege(
            "hr_referral.privilege_grant_reward_responsible",
            reason="no longer the gift manager of a reward",
        )._revoke(self.browse(responsibles_to_remove_ids), reward_responsible_group)

    def _create_missing_utm_source(self) -> None:
        users_without_utm_source = self.filtered(lambda user: not user.utm_source_id)
        utm_source = self.env["utm.source"].create(
            [
                {"name": self.env["utm.source"]._generate_name(user, user.name)}
                for user in users_without_utm_source
            ]
        )
        for user, source in zip(users_without_utm_source, utm_source, strict=True):
            user.sudo().utm_source_id = source
