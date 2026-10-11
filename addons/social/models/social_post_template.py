import re

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.json import dumps as json_dumps
from odoo.tools import OrderedSet, format_datetime


class SocialPostTemplate(models.Model):

    _name = "social.post.template"
    _description = "Social Post Template"
    _rec_names_search = ["display_message"]

    @api.model
    def default_get(self, fields):
        result = super().default_get(fields)
        if not result.get("message") and self.env.context.get("default_name"):
            result["message"] = self.env.context.get("default_name")
        return result

    message = fields.Text()
    image_ids = fields.Many2many(
        comodel_name="ir.attachment",
        string="Attach Images",
        bypass_search_access=True,
        help="Will attach images to your posts (if the social media supports it).",
    )
    display_message = fields.Char(
        compute="_compute_display_message",
        search="_search_display_message",
    )
    image_urls = fields.Text(
        string="Images URLs",
        compute="_compute_image_urls",
    )
    is_split_per_media = fields.Boolean(string="Split Per Network")
    media_count = fields.Integer(compute="_compute_media_count")
    account_ids = fields.Many2many(
        comodel_name="social.account",
        string="Social Accounts",
        compute="_compute_account_ids",
        store=True,
        readonly=False,
        help="The accounts on which this post will be published.",
    )
    has_active_accounts = fields.Boolean(
        string="Are Accounts Available?",
        compute="_compute_has_active_accounts",
    )

    @api.constrains("message", "image_ids")
    def _check_has_message_or_image(self) -> None:
        for post in self:
            if not post.message and not post.image_ids and not post.is_split_per_media:
                raise UserError(
                    self.env._("Please specify either a message or upload some images.")
                )

    @api.constrains(lambda self: ["image_ids"] + list(self._images_fields().values()))
    def _check_image_ids_mimetype(self) -> None:
        image_fields = ["image_ids"] + list(self._images_fields().values())
        for post in self:
            if any(
                not image.mimetype.startswith("image")
                for field in image_fields
                for image in post[field]
            ):
                raise UserError(
                    self.env._("Uploaded file does not seem to be a valid image.")
                )

    @api.depends("message", "is_split_per_media")
    def _compute_message_by_media(self) -> None:
        message_fields = self._message_fields()
        for post in self:
            for field in message_fields.values():
                if not post[field] or not post.is_split_per_media:
                    post[field] = post.message

    @api.depends("image_ids", "is_split_per_media")
    def _compute_images_by_media(self) -> None:
        images_fields = self._images_fields()
        for post in self:
            for field in images_fields.values():
                if not post[field] or not post.is_split_per_media:
                    post[field] = post.image_ids

    @api.depends(
        lambda self: (
            ["message", "is_split_per_media"] + list(self._message_fields().values())
        )
    )
    def _compute_display_message(self) -> None:
        message_fields = self._message_fields()
        for post in self:
            if not post.is_split_per_media:
                post.display_message = post.message
            else:
                media_types = post.account_ids.mapped("media_type")
                post.display_message = next(
                    (
                        post[message_fields[media_type]]
                        for media_type in media_types
                        if media_type in message_fields
                        and post[message_fields[media_type]]
                    ),
                    False,
                )

    def _search_display_message(self, operator, operand):
        if operator in Domain.NEGATIVE_OPERATORS:
            return NotImplemented
        return Domain.OR(
            Domain(field, operator, operand)
            for field in ("message", *self._message_fields().values())
        )

    @api.depends(lambda self: ["image_ids"] + list(self._images_fields().values()))
    def _compute_image_urls(self) -> None:
        image_fields = ["image_ids"] + list(self._images_fields().values())
        for post in self:
            all_image_ids = OrderedSet(
                [image_id for field in image_fields for image_id in post[field].ids]
            )
            post.image_urls = json_dumps(
                [f"/web/image/{image_id}" for image_id in all_image_ids if image_id]
            )

    @api.depends("account_ids")
    def _compute_media_count(self) -> None:
        for post in self:
            post.media_count = len(set(post.account_ids.mapped("media_type")))

    def _compute_account_ids(self) -> None:
        all_account_ids = self.env["social.account"].sudo().search([])

        for post in self:
            accounts = all_account_ids.filtered_domain(
                post._get_domain_default_accounts()
            )
            post.account_ids = accounts if len(accounts) <= 3 else False

    @api.depends("account_ids")
    def _compute_has_active_accounts(self) -> None:
        has_active_accounts = self.env["social.account"].search_count([], limit=1) > 0
        for post in self:
            post.has_active_accounts = has_active_accounts

    def _prepare_preview_values(self, media):
        self.check_singleton()
        return {
            "published_date": format_datetime(
                self.env, fields.Datetime.now(), tz=self.env.user.tz, dt_format="short"
            ),
        }

    def _set_attachemnt_res_id(self) -> None:
        for post in self:
            if post.image_ids:
                attachments = (
                    self.env["ir.attachment"]
                    .sudo()
                    .browse(post.image_ids.ids)
                    .filtered(
                        lambda a: (
                            a.res_model == self._name
                            and not a.res_id
                            and a.create_uid.id == self.env.uid
                        )
                    )
                )
                if attachments:
                    attachments.write({"res_id": post.id})

    @api.model
    def name_create(self, name):
        record = self.create({"message": name})
        return record.id, record.display_name

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        res._set_attachemnt_res_id()
        return res

    @api.depends("display_message")
    def _compute_display_name(self):
        for record in self:
            name = record.display_message or ""
            record.display_name = name if len(name) <= 50 else f"{name[:47]}..."

    def action_generate_post(self):
        self.check_singleton()
        action = self.env.ref("social.action_social_post").read()[0]
        action.update(
            {
                "views": [[False, "form"]],
                "context": {
                    "default_%s" % key: value
                    for key, value in self._prepare_social_post_values().items()
                },
            }
        )
        return action

    def _prepare_social_post_values(self):
        self.check_singleton()
        return {
            "message": self.message,
            "image_ids": self.image_ids.ids,
            "account_ids": self.account_ids.ids,
            "company_id": False,
            **{field: self[field] for field in self._message_fields().values()},
            **{field: self[field].ids for field in self._images_fields().values()},
        }

    @api.model
    def _prepare_post_content(self, message, media_type, **kw):

        if media_type not in [
            key
            for (key, val) in self.env["social.media"].fields_get(["media_type"])[
                "media_type"
            ]["selection"]
        ]:
            raise ValueError("Unknown media_type %s" % media_type)

        return message or ""

    @api.model
    def _message_fields(self) -> dict:
        return {}

    @api.model
    def _images_fields(self) -> dict:
        return {}

    @api.model
    def _get_fields_post_message_modifying(self):
        return []

    @api.model
    def _extract_url_from_message(self, message):
        if not message:
            return None
        url_regex = re.compile(
            r"""((?:[a-z][\w-]+:(?:/{1,3}|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|(([^\s()<>]+|(([^\s()<>]+)))*))+(?:(([^\s()<>]+|(([^\s()<>]+)))*)|[^\s`!()[]{};:'".,<>?«»“”‘’]))""",
            re.DOTALL,
        )
        urls = url_regex.search(message)
        if urls:
            return urls.group(0)
        return None

    def _get_domain_default_accounts(self):
        return []
