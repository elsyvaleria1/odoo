from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.web import urljoin as url_join

_debug = DebugLog(__name__)


class EventTrack(models.Model):
    _inherit = "event.track"

    firebase_enable_push_notifications = fields.Boolean(
        string="Enable Web Push Notifications",
        compute="_compute_firebase_enable_push_notifications",
    )
    push_reminder = fields.Boolean(
        compute="_compute_push_reminder",
        store=True,
        readonly=False,
        help="Check this if you want to send a push notification reminder to everyone that has favorited this track.",
    )
    push_reminder_delay = fields.Integer(
        compute="_compute_push_reminder_delay",
        store=True,
        readonly=False,
        help="How many minutes before the start of the talk do you want to send the reminder?",
    )
    push_reminder_posts = fields.One2many(
        comodel_name="social.post",
        inverse_name="event_track_id",
        string="Push Reminders",
        groups="social.group_social_manager",
    )

    @api.depends("event_id")
    def _compute_firebase_enable_push_notifications(self) -> None:
        current_website = self.env["website"].get_current_website()
        for track in self:
            website = track.event_id.website_id or current_website
            track.firebase_enable_push_notifications = (
                website.firebase_enable_push_notifications
            )

    @api.depends("event_id", "firebase_enable_push_notifications")
    def _compute_push_reminder(self) -> None:
        for track in self:
            if track.firebase_enable_push_notifications and not track.push_reminder:
                track.push_reminder = True
            elif (
                not track.firebase_enable_push_notifications or not track.push_reminder
            ):
                track.push_reminder = False

    @api.depends("push_reminder")
    def _compute_push_reminder_delay(self) -> None:
        for track in self:
            if track.push_reminder:
                track.push_reminder_delay = 15
            else:
                track.push_reminder_delay = 0

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        res.filtered(
            lambda track: track.push_reminder and track.is_track_upcoming
        )._create_or_update_reminder()
        return res

    def write(self, vals):
        push_reminder_tracks = self.filtered(lambda track: track.push_reminder)
        res = super().write(vals)

        if vals.keys() & {
            "name",
            "date",
            "push_reminder",
            "push_reminder_delay",
            "wishlisted_by_default",
        }:
            self.filtered(
                lambda track: track.push_reminder and track.is_track_upcoming
            )._create_or_update_reminder()

        if vals.get("push_reminder") is False and push_reminder_tracks:
            self.env["social.post"].search(
                [("event_track_id", "in", push_reminder_tracks.ids)]
            ).unlink()

        return res

    def action_edit_reminder(self):
        self.check_singleton()

        if not self.push_reminder_posts:
            _debug.logic("push_reminder_refused", reason="none_exist", track=self.id)
            raise UserError(
                self.env._("There are no push reminders associated with this track")
            )

        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "social.action_social_post"
        )
        action["views"] = [[False, "form"]]
        action["res_id"] = self.push_reminder_posts[0].id
        return action

    def _create_or_update_reminder(self) -> None:

        push_social_accounts = (
            self.env["social.account"]
            .sudo()
            .search(
                [
                    (
                        "media_id",
                        "=",
                        self.env.ref(
                            "social_push_notifications.social_media_push_notifications"
                        ).id,
                    )
                ]
            )
        )
        push_account_by_website = {
            account.website_id: account for account in push_social_accounts
        }

        existing_reminders = (
            self.env["social.post"].sudo().search([("event_track_id", "in", self.ids)])
        )
        existing_reminder_per_track = {
            social_post.event_track_id: social_post
            for social_post in existing_reminders
        }

        current_website = self.env["website"].get_current_website()
        posts_to_create = []
        for track in self:
            social_account = push_account_by_website.get(
                track.event_id.website_id or current_website
            )
            if not social_account:
                continue

            base_url = track.event_id.get_base_url()
            post_values = {
                "message": self.env._(
                    "Your favorite track '%(track)s' will start in %(delay)s minutes!",
                    track=track.name,
                    delay=track.push_reminder_delay,
                ),
                "push_notification_title": self.env._("Your track is about to start!"),
                "push_notification_target_url": url_join(base_url, track.website_url),
                "push_notification_image": track.website_image or False,
                "account_ids": [Command.link(social_account.id)],
                "post_method": "scheduled",
                "state": "scheduled",
                "use_visitor_timezone": False,
                "scheduled_date": track.date
                - relativedelta(minutes=track.push_reminder_delay),
                "event_track_id": track.id,
            }

            if track.wishlisted_by_default:
                post_values["visitor_domain"] = str(
                    [
                        "&",
                        "&",
                        ["has_push_notifications", "=", True],
                        ["event_registered_ids", "in", track.event_id.ids],
                        ["event_track_push_enabled_ids", "in", track.ids],
                    ]
                )
            else:
                post_values["visitor_domain"] = str(
                    [
                        "&",
                        ["has_push_notifications", "=", True],
                        ["event_track_wishlisted_ids", "in", track.ids],
                    ]
                )

            if existing_reminder_per_track.get(track):
                existing_reminder_per_track.get(track).update(post_values)
            else:
                posts_to_create.append(post_values)

        if posts_to_create:
            self.env["social.post"].sudo().create(posts_to_create)
