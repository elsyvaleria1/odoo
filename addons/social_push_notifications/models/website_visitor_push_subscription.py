from odoo import api, fields, models


class WebsiteVisitorPushSubscription(models.Model):
    """Contains the char push_token of a website.visitor's push subscription.
    Push subscriptions are created when a visitor accepts to receive 'Web Push Notifications' on its
    browser.
    This token is used by the firebase service to send notifications to that browser.

    A visitor can have multiple push subscriptions if they use several devices / browsers.
    (push_subscriptions are 'merged' onto the main visitor, see website.visitor#_merge_visitor for
    more information.)"""

    _name = "website.visitor.push.subscription"
    _description = "Push Subscription for a Website Visitor"
    _log_access = False
    _rec_name = "website_visitor_id"

    website_visitor_id = fields.Many2one(
        comodel_name="website.visitor",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    push_token = fields.Char(
        string="Push Subscription",
        readonly=True,
        required=True,
    )

    _push_token_uniq = models.Constraint(
        "unique (push_token)",
        "Push token can't be duplicated!",
    )

    @api.model_create_multi
    def create(self, vals_list):

        subscriptions = super().create(vals_list)
        subscriptions.website_visitor_id.write({"has_push_notifications": True})
        return subscriptions

    def unlink(self):

        website_visitor_ids = self.website_visitor_id
        result = super().unlink()

        remaining_subscriptions = self.search(
            [("website_visitor_id", "in", website_visitor_ids.ids)]
        )
        (
            website_visitor_ids - remaining_subscriptions.mapped("website_visitor_id")
        ).write({"has_push_notifications": False})

        return result
