import logging
import urllib.parse

import dateutil.parser

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.web import urljoin as url_join

from odoo.addons.social_facebook.models.social_stream import SocialStream

_logger = logging.getLogger(__name__)


class SocialStreamPost(models.Model):
    _inherit = "social.stream.post"

    FACEBOOK_COMMENT_FIELDS = f"id,from.fields(id,name,picture),message,message_tags,created_time,attachment,comments.fields(id,from.fields(id,name,picture),message,created_time,attachment,user_likes,like_count,{SocialStream.FACEBOOK_REACTIONS_FIELDS}),user_likes,like_count,{SocialStream.FACEBOOK_REACTIONS_FIELDS}"

    facebook_post_id = fields.Char(
        string="Facebook Post ID",
        index=True,
    )
    facebook_author_id = fields.Char(string="Facebook Author ID")
    facebook_likes_count = fields.Integer(string="Likes")
    facebook_reactions_count = fields.Char(string="Reactions Count")
    facebook_user_likes = fields.Boolean(string="User Likes")
    facebook_comments_count = fields.Integer(string="Comments")
    facebook_shares_count = fields.Integer(string="Shares")
    facebook_reach = fields.Integer(string="Reach")

    facebook_is_event_post = fields.Boolean(string="Is event post")

    def _compute_author_link(self) -> None:
        facebook_posts = self._filtered_by_media_types(["facebook"])
        super(SocialStreamPost, (self - facebook_posts))._compute_author_link()

        for post in facebook_posts:
            post.author_link = "/social_facebook/redirect_to_profile/%s/%s?name=%s" % (
                post.account_id.id,
                post.facebook_author_id,
                urllib.parse.quote(post.author_name),
            )

    def _compute_post_link(self) -> None:
        facebook_posts = self._filtered_by_media_types(["facebook"])
        super(SocialStreamPost, (self - facebook_posts))._compute_post_link()

        for post in facebook_posts:
            post.post_link = "https://www.facebook.com/%s" % post.facebook_post_id

    def _compute_is_author(self) -> None:
        facebook_posts = self._filtered_by_media_types(["facebook"])
        super(SocialStreamPost, (self - facebook_posts))._compute_is_author()

        for post in facebook_posts:
            post.is_author = (
                post.facebook_author_id == post.account_id.facebook_account_id
            )

    def _facebook_remove_comment(self, comment_id) -> bool:
        self.env["ir.egress"].request(
            "DELETE",
            url_join(self.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED, comment_id),
            purpose="social_facebook",
            data={"access_token": self.stream_id.account_id.facebook_access_token},
            timeout=5,
        )

        return True

    def _facebook_get_comments(self, next_records_token=False, count=20) -> dict:
        self.check_singleton()

        comments_endpoint_url = url_join(
            self.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED,
            "%s/comments" % self.facebook_post_id,
        )
        params = {
            "fields": self.FACEBOOK_COMMENT_FIELDS,
            "access_token": self.stream_id.account_id.facebook_access_token,
            "summary": 1,
            "limit": count,
            "order": "reverse_chronological",
        }
        if next_records_token:
            params["after"] = next_records_token

        result = self.env["ir.egress"].request(
            "GET", comments_endpoint_url, purpose="social_facebook", params=params
        )
        result_json = result.json()

        if not result.ok:
            _logger.warning(
                "An error occurred while fetching the comment: %s", result.text
            )

            error_message = self.env._("An error occurred.")

            if result_json.get("error"):
                error_code = result_json["error"].get("code")
                error_subcode = result_json["error"].get("error_subcode")
                if error_code == 100 and error_subcode == 33:
                    error_message = self.env._(
                        "Post not found. It could be because the post has been deleted on the Social Platform."
                    )

            raise UserError(error_message)

        for comment in result_json.get("data"):
            comment.update(self._format_facebook_comment(comment))

            inner_comments = comment.get("comments", {}).get("data") or []

            if not inner_comments:
                comment["comments"] = {"data": []}
            for inner_comment in inner_comments:
                inner_comment.update(self._format_facebook_comment(inner_comment))

        return {
            "comments": result_json.get("data"),
            "summary": result_json.get("summary"),
            "nextRecordsToken": result_json.get("paging").get("cursors").get("after")
            if result_json.get("paging")
            else None,
        }

    def _facebook_comment_post(
        self, endpoint_url, message, existing_attachment_id=None, attachment=None
    ):
        params = {
            "message": message,
            "access_token": self.stream_id.account_id.facebook_access_token,
            "fields": self.FACEBOOK_COMMENT_FIELDS,
        }

        if existing_attachment_id:
            params.update({"attachment_id": existing_attachment_id})

        extracted_url = self.env["social.post"]._extract_url_from_message(message)
        if extracted_url and not attachment and not existing_attachment_id:
            params.update({"link": extracted_url})

        result = (
            self.env["ir.egress"]
            .request(
                "POST",
                endpoint_url,
                purpose="social_facebook",
                data=params,
                files={"source": ("source", attachment.read(), attachment.content_type)}
                if attachment
                else None,
                timeout=15,
            )
            .json()
        )
        result["likes"] = {"summary": {"total_count": result.get("like_count", 0)}}

        inner_comments = result.get("comments", {}).get("data", [])
        for inner_comment in inner_comments:
            inner_comment["likes"] = {
                "summary": {"total_count": inner_comment.get("like_count", 0)}
            }

        result.setdefault("comments", {"data": []})
        return result

    def _facebook_like(self, object_id, like) -> None:
        params = {"access_token": self.stream_id.account_id.facebook_access_token}
        comments_like_endpoint_url = url_join(
            self.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED,
            "%s/likes" % (object_id),
        )
        if like:
            self.env["ir.egress"].request(
                "POST",
                comments_like_endpoint_url,
                purpose="social_facebook",
                data=params,
                timeout=5,
            )
        else:
            self.env["ir.egress"].request(
                "DELETE",
                comments_like_endpoint_url,
                purpose="social_facebook",
                data=params,
            )

    @api.model
    def _format_facebook_published_date(self, comment):
        return self.env["social.stream.post"]._format_published_date(
            dateutil.parser.parse(comment.get("created_time"), ignoretz=True)
        )

    def _get_matching_post(self):
        self.check_singleton()

        if self.account_id.media_type == "facebook" and self.facebook_post_id:
            return (
                self.env["social.live.post"]
                .search([("facebook_post_id", "=", self.facebook_post_id)], limit=1)
                .post_id
            )
        else:
            return super()._get_matching_post()

    def _format_facebook_comment(self, comment):
        comment = {
            **comment,
            "formatted_created_time": self._format_facebook_published_date(comment),
            "message": self.stream_id._format_facebook_message(
                comment.get("message"), comment.get("message_tags")
            ),
            "reactions": {
                reaction: comment.get(reaction, {})
                .get("summary", {})
                .get("total_count", 0)
                for reaction in self.env["social.stream"].FACEBOOK_REACTIONS
            },
        }
        if "from" not in comment:
            comment["from"] = {"name": self.env._("Unknown")}
        if comment.get("attachment", {}).get("type") == "sticker":
            comment["attachment"]["type"] = "photo"
        return comment
