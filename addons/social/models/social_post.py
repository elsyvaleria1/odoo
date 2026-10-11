import logging
from collections import defaultdict

from markupsafe import Markup

from odoo import Command, api, fields, models, modules
from odoo.exceptions import UserError, ValidationError
from odoo.libs.json import dumps as json_dumps

_logger = logging.getLogger(__name__)


class SocialPost(models.Model):
    """A social.post represents a post that will be published on multiple social.accounts at once.
    It doesn't do anything on its own except storing the global post configuration (message, images, ...).

    This model inherits from `social.post.template` which contains the common part of both
    (all fields related to the post content like the message, the images...). So we do not
    duplicate the code by inheriting from it. We can generate a `social.post` from a
    `social.post.template` with `action_generate_post`.

    When posted, it actually creates several instances of social.live.posts (one per social.account)
    that will publish their content through the third party API of the social.account."""

    _name = "social.post"
    _inherit = [
        "mixin.mail.thread",
        "mixin.mail.activity",
        "social.post.template",
        "mixin.utm.source",
    ]
    _description = "Social Post"
    _order = "create_date desc"

    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("scheduled", "Scheduled"),
            ("posting", "Posting"),
            ("posted", "Posted"),
        ],
        string="Status",
        default="draft",
        readonly=True,
        required=True,
        help="The post is considered as 'Posted' when all its sub-posts (one per social account) are either 'Failed' or 'Posted'",
    )
    has_post_errors = fields.Boolean(
        string="There are post errors on sub-posts",
        compute="_compute_has_post_errors",
    )
    account_ids = fields.Many2many(domain="[('id', 'in', account_allowed_ids)]")
    account_allowed_ids = fields.Many2many(
        comodel_name="social.account",
        string="Allowed Accounts",
        compute="_compute_account_allowed_ids",
        help="List of the accounts which can be selected for this post.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        domain=lambda self: [("id", "in", self.env.companies.ids)],
    )
    media_ids = fields.Many2many(
        comodel_name="social.media",
        compute="_compute_media_ids",
        store=True,
        help="The social medias linked to the selected social accounts.",
    )
    live_post_ids = fields.One2many(
        comodel_name="social.live.post",
        inverse_name="post_id",
        string="Posts By Account",
        readonly=True,
        help="Sub-posts that will be published on each selected social accounts.",
    )
    live_posts_by_media = fields.Char(
        string="Live Posts by Social Media",
        compute="_compute_live_posts_by_media",
        readonly=True,
        help="Special technical field that holds a dict containing the live posts names by media ids (used for kanban view).",
    )
    post_method = fields.Selection(
        selection=[("now", "Send now"), ("scheduled", "Schedule later")],
        string="When",
        default="now",
        required=True,
        help="Publish your post immediately or schedule it at a later time.",
    )
    scheduled_date = fields.Datetime()
    published_date = fields.Datetime(
        readonly=True,
        help="When the global post was published. The actual sub-posts published dates may be different depending on the media.",
    )
    calendar_date = fields.Datetime(
        compute="_compute_calendar_date",
        store=True,
        readonly=False,
    )
    is_hatched = fields.Boolean(
        string="Hatched",
        compute="_compute_is_hatched",
    )
    utm_campaign_id = fields.Many2one(
        comodel_name="utm.campaign",
        string="Campaign",
        index="btree_not_null",
        domain="[('is_auto_campaign', '=', False)]",
        ondelete="set null",
    )
    source_id = fields.Many2one(readonly=True)
    stream_posts_count = fields.Integer(
        string="Feed Posts Count",
        compute="_compute_stream_posts_count",
    )
    engagement = fields.Integer(
        compute="_compute_post_engagement",
        help="Number of people engagements with the post (Likes, comments...)",
    )
    click_count = fields.Integer(
        string="Number of clicks",
        compute="_compute_click_count",
    )

    @api.constrains("account_ids")
    def _check_account_ids(self) -> None:
        for post in self.sudo():
            if not (post.account_ids <= post.account_allowed_ids):
                raise ValidationError(
                    self.env._(
                        "Selected accounts (%(account_list)s) do not match the selected company (%(company)s)",
                        account_list=(
                            post.account_ids - post.account_allowed_ids
                        ).mapped("name"),
                        company=post.company_id.name,
                    )
                )

    @api.constrains("state", "scheduled_date")
    def _check_scheduled_date(self) -> None:
        if any(
            post.state in ("draft", "scheduled")
            and post.scheduled_date
            and post.scheduled_date < fields.Datetime.now()
            for post in self
        ):
            raise ValidationError(self.env._("You cannot schedule a post in the past."))

    @api.depends("live_post_ids.engagement")
    def _compute_post_engagement(self) -> None:
        results = self.env["social.live.post"]._read_group(
            [("post_id", "in", self.ids)], ["post_id"], ["engagement:sum"]
        )
        engagement_per_post = {
            post.id: engagement_total for post, engagement_total in results
        }
        for post in self:
            post.engagement = engagement_per_post.get(post.id, 0)

    @api.depends("account_allowed_ids")
    def _compute_has_active_accounts(self) -> None:
        for post in self:
            post.has_active_accounts = bool(post.account_allowed_ids)

    @api.depends("live_post_ids")
    def _compute_stream_posts_count(self) -> None:
        for post in self:
            stream_post_domain = post._get_domain_stream_post()
            if stream_post_domain:
                post.stream_posts_count = self.env["social.stream.post"].search_count(
                    stream_post_domain
                )
            else:
                post.stream_posts_count = 0

    @api.depends("company_id")
    def _compute_account_ids(self) -> None:
        super()._compute_account_ids()

    @api.depends("company_id")
    def _compute_account_allowed_ids(self) -> None:
        all_account_allowed_ids = self.env["social.account"].search([])

        for post in self:
            post.account_allowed_ids = all_account_allowed_ids.filtered_domain(
                post._get_domain_company()
            )

    @api.depends("live_post_ids.state")
    def _compute_has_post_errors(self) -> None:
        for post in self:
            post.has_post_errors = any(
                live_post.state == "failed" for live_post in post.live_post_ids
            )

    @api.depends("account_ids.media_id")
    def _compute_media_ids(self) -> None:
        for post in self:
            post.media_ids = post.with_context(active_test=False).account_ids.mapped(
                "media_id"
            )

    @api.depends("state", "post_method", "scheduled_date", "published_date")
    def _compute_calendar_date(self) -> None:
        for post in self:
            if post.state == "posted":
                post.calendar_date = post.published_date
            elif post.post_method == "now":
                post.calendar_date = False
            else:
                post.calendar_date = post.scheduled_date

    @api.depends("live_post_ids.account_id", "live_post_ids.display_name")
    def _compute_live_posts_by_media(self) -> None:
        for post in self:
            accounts_by_media = {media_id: [] for media_id in post.media_ids.ids}
            for live_post in post.live_post_ids.filtered(
                lambda lp: lp.account_id.media_id.ids
            ):
                accounts_by_media[live_post.account_id.media_id.id].append(
                    live_post.display_name
                )
            post.live_posts_by_media = json_dumps(accounts_by_media)

    @api.depends("state")
    def _compute_is_hatched(self) -> None:
        for post in self:
            post.is_hatched = post.state == "draft"

    def _compute_click_count(self) -> None:
        medium_ids = self.account_ids.mapped("utm_medium_id")

        if not self.source_id.ids or not medium_ids.ids:
            for post in self:
                post.click_count = 0
        else:
            query = """
                SELECT COUNT(DISTINCT(click.id)) as click_count, link.source_id
                  FROM link_tracker_click click
            INNER JOIN link_tracker link ON link.id = click.link_id
                 WHERE link.source_id = ANY(%s) AND link.medium_id = ANY(%s)
              GROUP BY link.source_id
            """

            self.env.cr.execute(query, [list(self.source_id.ids), list(medium_ids.ids)])
            click_data = self.env.cr.dictfetchall()
            mapped_data = {
                datum["source_id"]: datum["click_count"] for datum in click_data
            }
            for post in self:
                post.click_count = mapped_data.get(post.source_id.id, 0)

    def _prepare_preview_values(self, media):
        values = super()._prepare_preview_values(media)
        if self._name == "social.post":
            live_posts = self.live_post_ids._filtered_by_media_types([media])
            values["live_post_link"] = (
                live_posts[0].live_post_link if len(live_posts) >= 1 else False
            )
        return values

    @api.depends("display_message", "state")
    def _compute_display_name(self):
        for post in self:
            post.display_name = self._prepare_post_name(
                post.display_message,
                state=post.state if post.state == "draft" else False,
            )

    @api.model
    def default_get(self, fields):

        result = super().default_get(fields)
        default_calendar_date = self.env.context.get("default_calendar_date")
        if default_calendar_date and (
            "post_method" in fields or "scheduled_date" in fields
        ):
            result.update(
                {"post_method": "scheduled", "scheduled_date": default_calendar_date}
            )
        return result

    @api.model_create_multi
    def create(self, vals_list):

        message_fields = ["message"] + list(self._message_fields().values())
        for vals in vals_list:
            if not vals.get("name"):
                new_name = next(
                    (vals.get(field) for field in message_fields if vals.get(field)),
                    self.env._("Post"),
                )
                vals["name"] = self.env["utm.source"]._generate_name(self, new_name)

        for vals in vals_list:
            if vals.get("state") == "posted" and "published_date" in vals:
                vals["calendar_date"] = vals["published_date"]
            elif vals.get("post_method") == "now":
                vals["calendar_date"] = False
            elif "scheduled_date" in vals:
                vals["calendar_date"] = vals["scheduled_date"]

        res = super().create(vals_list)

        cron_trigger_dates = {
            post.scheduled_date for post in res if post.scheduled_date
        }
        if cron_trigger_dates:
            self.env["ir.cron"]._trigger_ref(
                "social.ir_cron_post_scheduled", cron_trigger_dates
            )

        return res

    def write(self, vals):
        if vals.get("calendar_date"):
            if any(post.state not in ("draft", "scheduled") for post in self):
                raise UserError(
                    self.env._(
                        "You cannot reschedule a post that has already been posted."
                    )
                )

            vals["scheduled_date"] = vals["calendar_date"]

        if vals.get("scheduled_date"):
            self.env["ir.cron"]._trigger_ref(
                "social.ir_cron_post_scheduled",
                fields.Datetime.from_string(vals.get("scheduled_date")),
            )

        message_fields = ["message"] + list(self._message_fields().values())
        if set(vals) & set(message_fields):
            new_name = next(
                (vals.get(field) for field in message_fields if vals.get(field)),
                self.env._("Post"),
            )
            vals["name"] = self.env["utm.source"]._generate_name(
                self.env["social.post"], new_name
            )

        return super().write(vals)

    def social_stream_post_action_my(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "social.action_social_stream_post"
        )
        action["name"] = self.env._("Feed Posts")
        action["domain"] = self._get_domain_stream_post()
        action["context"] = {
            "search_default_search_my_streams": True,
            "search_default_group_by_stream": True,
        }
        return action

    def _check_post_access(self) -> None:
        if any(not post.account_ids for post in self):
            raise UserError(
                self.env._(
                    "Please specify at least one account to post into (for post ID(s) %s).",
                    ", ".join([str(post.id) for post in self if not post.account_ids]),
                )
            )
        errors = defaultdict(list)
        message_field_per_media = self._message_fields()
        for post in self:
            for media in post.media_ids.filtered(lambda media: media.max_post_length):
                message_field = message_field_per_media.get(media.media_type)
                if (
                    message_field
                    and len(post[message_field] or "") > media.max_post_length
                ):
                    errors[post].append(
                        self.env._(
                            "%(media_name)s (max %(max_chars)s chars)",
                            media_name=media.name,
                            max_chars=media.max_post_length,
                        )
                    )
        if bool(errors):
            raise ValidationError(
                self.env._(
                    "Due to length restrictions, the following posts cannot be posted:\n %s",
                    "\n".join(
                        [
                            "%s : %s" % (post.display_name, ",".join(err))
                            for post, err in errors.items()
                        ]
                    ),
                )
            )

    def action_schedule(self):
        self._check_post_access()
        self.write({"state": "scheduled"})

    def action_set_draft(self) -> None:
        self._check_post_access()
        self.write({"state": "draft"})

    def action_post(self):
        self._check_post_access()

        self.write({"post_method": "now", "scheduled_date": False})

        self._action_post()

    def action_redirect_to_clicks(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "link_tracker.link_tracker_action"
        )
        action["domain"] = [
            ("source_id", "=", self.source_id.id),
            ("medium_id", "in", self.account_ids.mapped("utm_medium_id").ids),
        ]
        return action

    def _action_post(self) -> None:

        to_post = self.filtered(lambda post: post.state in ("draft", "scheduled"))
        if not to_post:
            return

        for post in to_post:
            post.write(
                {
                    "state": "posting",
                    "published_date": fields.Datetime.now(),
                    "live_post_ids": [
                        Command.create(live_post)
                        for live_post in post._prepare_live_post_values()
                    ],
                }
            )

        if modules.module.current_test:
            to_post._post_live_posts()
            return

        to_post.mapped("live_post_ids.message")
        registry, post_ids = self.env.registry, to_post.ids
        uid, context = self.env.uid, dict(self.env.context)

        @self.env.cr.postcommit.add
        def post_live_posts_after_commit():
            try:
                with registry.cursor() as cr:
                    api.Environment(cr, uid, context)["social.post"].browse(
                        post_ids
                    ).exists()._post_live_posts()
            except Exception:
                _logger.exception("Could not publish the social posts %s", post_ids)

    def _post_live_posts(self) -> None:
        for post in self:
            failed_posts = self.env["social.live.post"]
            for live_post in post.live_post_ids:
                try:
                    live_post._post()
                except Exception:
                    _logger.warning("_action_post failed", exc_info=True)
                    failed_posts |= live_post
            failed_posts.write(
                {"state": "failed", "failure_reason": self.env._("Unknown error")}
            )

    def _prepare_live_post_values(self) -> list:
        self.check_singleton()

        return [
            {
                "post_id": self.id,
                "account_id": account.id,
            }
            for account in self.account_ids
        ]

    @api.model
    def _prepare_post_name(self, message, state=False):
        name = self.env._("Post")
        if message:
            message = message.replace(
                "\n", " "
            )
            if len(message) < 24:
                name = message
            else:
                name = message[:20] + "..."

        if state:
            state_description_values = {
                elem[0]: elem[1]
                for elem in self._fields["state"]._description_selection(self.env)
            }
            state_translated = state_description_values.get(state)
            name += f" ({state_translated})"

        return name

    def _get_domain_company(self):
        self.check_singleton()
        if self.company_id:
            return [
                "|",
                ("company_id", "=", False),
                ("company_id", "=", self.company_id.id),
            ]
        return [
            "|",
            ("company_id", "=", False),
            ("company_id", "in", self.env.companies.ids),
        ]

    def _get_domain_default_accounts(self):
        return self._get_domain_company()

    def _get_domain_stream_post(self):
        return []

    def _check_post_completion(self) -> None:

        posts_to_complete = self.filtered(
            lambda post: all(
                live_post.state in ("posted", "failed")
                for live_post in post.live_post_ids
            )
        )

        for post in posts_to_complete:
            posts_failed = Markup("<br>").join(
                [
                    "  - " + live_post.display_name
                    for live_post in post.live_post_ids
                    if live_post.state == "failed"
                ]
            )

            if posts_failed:
                post._message_log(
                    body=self.env._(
                        "Message posted partially. These are the ones that couldn't be posted:%s",
                        Markup("<br/>") + posts_failed,
                    )
                )
            else:
                post._message_log(body=self.env._("Message posted"))

        if posts_to_complete:
            posts_to_complete.sudo().write({"state": "posted"})

    @api.model
    def _cron_publish_scheduled(self) -> None:

        self.search(
            [
                ("post_method", "=", "scheduled"),
                ("state", "=", "scheduled"),
                ("scheduled_date", "<=", fields.Datetime.now()),
            ]
        )._action_post()
