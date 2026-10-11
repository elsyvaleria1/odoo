from odoo import exceptions, fields, models


class WizardGamificationBadgeGrant(models.TransientModel):
    """Wizard for granting a badge to a user."""

    _name = "wizard.gamification.badge.grant"
    _description = "Gamification User Badge Wizard"

    user_id = fields.Many2one(
        comodel_name="res.users",
        required=True,
    )
    badge_id = fields.Many2one(
        comodel_name="gamification.badge",
        required=True,
    )
    comment = fields.Text()

    def action_grant_badge(self) -> bool:
        BadgeUser = self.env["gamification.badge.user"]
        uid = self.env.uid
        for wiz in self:
            if uid == wiz.user_id.id:
                raise exceptions.UserError(
                    self.env._("You can not grant a badge to yourself.")
                )
            BadgeUser.create(
                {
                    "user_id": wiz.user_id.id,
                    "sender_id": uid,
                    "badge_id": wiz.badge_id.id,
                    "comment": wiz.comment,
                }
            )._send_badge()
        return True
