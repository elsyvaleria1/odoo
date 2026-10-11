import markupsafe

from odoo import fields, models, tools

from odoo.addons.base.models.access_link import LinkLoginRequired, LinkRefused
from odoo.addons.rating.models.rating_data import RATING_CHANGE_WINDOW


class MixinMailThread(models.AbstractModel):
    _inherit = "mixin.mail.thread"

    rating_ids = fields.One2many(
        comodel_name="rating.rating",
        inverse_name="res_id",
        string="Ratings",
        domain=lambda self: [("res_model", "=", self._get_reference_model_name())],
        bypass_search_access=True,
        classification="base.internal",
    )


    def unlink(self):
        record_ids = self.ids
        result = super().unlink()
        self.env["rating.rating"].sudo().search(
            [
                ("res_model", "=", self._get_reference_model_name()),
                ("res_id", "in", record_ids),
            ]
        ).unlink()
        return result

    def _get_message_create_ignore_field_names(self):
        return super()._get_message_create_ignore_field_names() | {"rating_id"}


    def _rating_apply_get_default_subtype_id(self):
        return self.env["ir.model.data"]._xmlid_to_res_id("mail.mt_comment")

    def _rating_get_operator(self):
        if "user_id" in self and self.user_id.partner_id:
            return self.user_id.partner_id
        return self.env["res.partner"]

    def _rating_get_partner(self):
        if "partner_id" in self and self.partner_id:
            return self.partner_id
        return self.env["res.partner"]


    def _rating_get_access_token(self, partner=None):
        self.check_access("read")
        if not partner:
            partner = self._rating_get_partner()
        rated_partner = self._rating_get_operator()
        rating = next(
            (
                r
                for r in self.rating_ids.sudo()
                if r.partner_id.id == partner.id and not r.consumed
            ),
            None,
        )
        if not rating:
            rating = (
                self.env["rating.rating"]
                .sudo()
                .create(
                    {
                        "partner_id": partner.id,
                        "rated_partner_id": rated_partner.id,
                        "res_model_id": self.env["ir.model"]._get_id(
                            self._get_reference_model_name()
                        ),
                        "res_id": self.id,
                        "is_internal": False,
                    }
                )
            )
        return rating.access_token or rating._issue_link()


    def rating_send_request(self, template, lang=False, force_send=True) -> None:
        if lang:
            template = template.with_context(lang=lang)
        self.with_context(mail_notify_force_send=force_send).message_post_with_source(
            template,
            email_layout_xmlid="mail.mail_notification_light",
            force_send=force_send,
            subtype_xmlid="mail.mt_note",
        )

    def rating_apply(
        self,
        rate,
        token=None,
        rating=None,
        feedback=None,
        subtype_xmlid=None,
        notify_delay_send=False,
    ):
        if rate < 0 or rate > 5:
            raise ValueError(
                f"Wrong rating value. A rate should be between 0 and 5 (received {rate})."
            )
        if token:
            try:
                rating = (
                    self.env["access.link"]
                    ._resolve(token, model="rating.rating", role="comment", action=None)
                    .record
                )
            except LinkRefused, LinkLoginRequired:
                rating = self.env["rating.rating"]
        if not rating:
            raise ValueError("Invalid token or rating.")

        rating.write({"rating": rate, "feedback": feedback, "consumed": True})
        if isinstance(self, self.env.registry["mixin.mail.thread"]):
            if subtype_xmlid is None:
                subtype_id = self._rating_apply_get_default_subtype_id()
            else:
                subtype_id = False
            feedback = tools.plaintext2html(feedback or "", with_paragraph=False)

            scheduled_datetime = (
                fields.Datetime.now() + RATING_CHANGE_WINDOW
                if notify_delay_send
                else None
            )
            rating_body = markupsafe.Markup(
                "<img src='%s' alt=':%s/5' style='width:18px;height:18px;float:left;margin-right: 5px;'/>%s"
            ) % (rating.rating_image_url, rate, feedback)

            if rating.message_id:
                self._message_update_content(
                    rating.message_id,
                    body=rating_body,
                    scheduled_date=scheduled_datetime,
                    strict=False,
                )
            else:
                self.message_post(
                    author_id=rating.partner_id.id
                    or None,
                    body=rating_body,
                    rating_id=rating.id,
                    scheduled_date=scheduled_datetime,
                    subtype_id=subtype_id,
                    subtype_xmlid=subtype_xmlid,
                )
        return rating

    def _message_post_prepare_values(self, post_values) -> None:
        super()._message_post_prepare_values(post_values)
        rating_id = post_values.pop("rating_id", False)
        if rating_value := post_values.pop("rating_value", False):
            rating_id = (
                self.env["rating.rating"]
                .sudo()
                .create(
                    {
                        "rating": float(rating_value),
                        "feedback": tools.html2plaintext(post_values.get("body", "")),
                        "res_model_id": self.env["ir.model"]._get_id(
                            self._get_reference_model_name()
                        ),
                        "res_id": self.id,
                        "consumed": True,
                        "partner_id": self.env.user.partner_id.id,
                    }
                )
                .id
            )
        if rating_id:
            post_values["rating_id"] = rating_id

    def _message_post_batch_per_record_keys(self):
        return super()._message_post_batch_per_record_keys() | {"rating_id"}

    def _message_post_after_hook(self, message, msg_values):
        rating = self.env["rating.rating"].browse(msg_values.get("rating_id")).sudo()
        same_author = rating.partner_id and rating.partner_id == message.author_id
        if (
            same_author
            and rating.res_model == message.model
            and rating.res_id == message.res_id
        ):
            rating.message_id = message.id
        super()._message_post_after_hook(message, msg_values)

    def _get_allowed_message_params(self):
        return super()._get_allowed_message_params() | {"rating_value"}

    def _message_update_content(
        self, message, /, *, body=None, rating_value=None, **kwargs
    ):
        if rating_value:
            message.rating_id.rating = rating_value
            if body is not None:
                message.rating_id.feedback = tools.html2plaintext(body)
        elif rating_value is False:
            rating_ids = message.rating_ids
            rating_ids.message_id = False
            rating_ids.unlink()
        return super()._message_update_content(message, body=body, **kwargs)
