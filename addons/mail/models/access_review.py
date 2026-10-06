from odoo import models


class AccessReviewCampaign(models.Model):
    _inherit = "access.review.campaign"

    def action_start(self) -> bool:
        result = super().action_start()
        self.item_ids.filtered(
            lambda item: item.decision == "pending"
        )._schedule_reviews()
        return result


class AccessReviewItem(models.Model):
    _name = "access.review.item"
    _inherit = ["access.review.item", "mixin.mail.activity"]

    def _schedule_reviews(self) -> None:
        # the access administrators have the reviews in the Access menu; any
        # other reviewer (a link's owner, a named reviewer) is told each item
        # to decide, due by the review's deadline
        administrators = self.env.ref("base.group_erp_manager").all_user_ids
        by_reviewer: dict[models.BaseModel, list[int]] = {}
        for item in self:
            for reviewer in item.reviewer_ids - administrators:
                by_reviewer.setdefault(reviewer, []).append(item.id)
        for reviewer, item_ids in by_reviewer.items():
            for campaign, items in self.browse(item_ids).grouped("campaign_id").items():
                items.activity_schedule(
                    "mail.mail_activity_data_todo",
                    date_deadline=campaign.date_deadline,
                    summary=self.env._(
                        "Keep or revoke: %(review)s", review=campaign.name
                    ),
                    user_id=reviewer.id,
                )

    def _decide(self, decision: str, note: str | None) -> None:
        pending = self.filtered(lambda item: item.decision == "pending")
        super()._decide(decision, note)
        pending.activity_unlink(["mail.mail_activity_data_todo"])
