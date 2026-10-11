from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain


class WebsiteVisitor(models.Model):
    _inherit = "website.visitor"

    push_subscription_ids = fields.One2many(
        comodel_name="website.visitor.push.subscription",
        inverse_name="website_visitor_id",
        string="Push Subscriptions",
    )
    has_push_notifications = fields.Boolean(string="Push Notifications Enabled")

    _has_push_notifications_index = models.UniqueIndex(
        "(id) WHERE has_push_notifications IS TRUE"
    )

    def action_send_push_notification(self):
        if all(visitor.has_push_notifications for visitor in self):
            push_media = self.env["social.media"].search(
                [("media_type", "=", "push_notifications")]
            )
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "social.action_social_post"
            )
            action["views"] = [[False, "form"]]
            action["context"] = {
                "default_visitor_domain": "[('has_push_notifications', '!=', False), ('id', 'in', %s)]"
                % self.ids,
                "default_account_ids": push_media.account_ids.ids,
            }
            return action
        else:
            raise UserError(
                self.env._("Some selected visitors do not allow push notifications.")
            )

    def _get_domain_inactive_visitors(self):
        return super()._get_domain_inactive_visitors() & Domain(
            "has_push_notifications", "=", False
        )

    def _merge_visitor(self, target):
        self.push_subscription_ids.write({"website_visitor_id": target.id})
        self.write({"has_push_notifications": False})
        return super()._merge_visitor(target)

    def _register_push_subscription(self, push_token):
        self.check_singleton()

        if push_token:
            self.env["website.visitor.push.subscription"].search(
                [("push_token", "=", push_token)]
            ).unlink()

            return self.env["website.visitor.push.subscription"].create(
                {"website_visitor_id": self.id, "push_token": push_token}
            )
        return None
