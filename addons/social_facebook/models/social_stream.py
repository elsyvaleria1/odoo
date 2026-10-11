import re

import dateutil.parser

from odoo import Command, api, models
from odoo.libs.json import dumps as json_dumps
from odoo.libs.web import urljoin as url_join


class SocialStream(models.Model):
    _inherit = "social.stream"

    FACEBOOK_REACTIONS = {"LIKE", "LOVE", "HAHA", "WOW", "SAD", "ANGRY", "CARE"}
    FACEBOOK_REACTIONS_FIELDS = ",".join(
        {
            f"reactions.type({reaction}).limit(0).summary(1).as({reaction})"
            for reaction in FACEBOOK_REACTIONS
        }
    )

    def _apply_default_name(self) -> None:
        facebook_streams = self.filtered(lambda s: s.media_id.media_type == "facebook")
        super(SocialStream, (self - facebook_streams))._apply_default_name()

        for stream in facebook_streams:
            stream.write(
                {
                    "name": "%s: %s"
                    % (stream.stream_type_id.name, stream.account_id.name)
                }
            )

    def _sync_stream_data(self):
        if self.media_id.media_type != "facebook":
            return super()._sync_stream_data()

        if self.stream_type_id.stream_type == "facebook_page_posts":
            return self._sync_page_posts("published_posts")
        elif self.stream_type_id.stream_type == "facebook_page_mentions":
            return self._sync_page_posts("tagged")
        return None

    def _sync_page_posts(self, endpoint_name) -> bool:
        self.check_singleton()

        facebook_fields = [
            "id",
            "message",
            "from",
            "shares",
            "likes.limit(1).summary(true)",
            "comments.limit(10).summary(true){message,from,like_count}",
            "attachments",
            "created_time",
            "message_tags",
            self.FACEBOOK_REACTIONS_FIELDS,
        ]
        if endpoint_name == "published_posts":
            facebook_fields.append("insights.metric(post_media_view)")

        posts_endpoint_url = url_join(
            self.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED,
            f"{self.account_id.facebook_account_id}/{endpoint_name}",
        )
        result = self.env["ir.egress"].request(
            "GET",
            posts_endpoint_url,
            purpose="social_facebook",
            params={
                "access_token": self.account_id.facebook_access_token,
                "fields": ",".join(facebook_fields),
            },
            timeout=5,
        )

        result_posts = result.json().get("data")
        if not result_posts:
            self.account_id._action_disconnect_accounts(result.json())
            return False

        facebook_post_ids = [post.get("id") for post in result_posts]
        existing_posts = self.env["social.stream.post"].search(
            [("stream_id", "=", self.id), ("facebook_post_id", "in", facebook_post_ids)]
        )
        existing_posts_by_facebook_post_id = {
            post.facebook_post_id: post for post in existing_posts
        }

        posts_to_create = []
        for post in result_posts:
            reactions = {
                reaction: count
                for reaction in self.env["social.stream"].FACEBOOK_REACTIONS
                if (
                    count := post.get(reaction, {})
                    .get("summary", {})
                    .get("total_count", 0)
                )
            }

            values = {
                "stream_id": self.id,
                "message": self._format_facebook_message(
                    post.get("message"), post.get("message_tags")
                ),
                "author_name": post.get("from", {}).get("name", ""),
                "facebook_author_id": post.get("from", {}).get("id"),
                "published_date": dateutil.parser.parse(
                    post.get("created_time"), ignoretz=True
                ),
                "facebook_shares_count": post.get("shares", {}).get("count"),
                "facebook_likes_count": sum(reactions.values()),
                "facebook_reactions_count": json_dumps(reactions),
                "facebook_user_likes": post.get("likes", {})
                .get("summary", {})
                .get("has_liked"),
                "facebook_comments_count": post.get("comments", {})
                .get("summary", {})
                .get("total_count"),
                "facebook_reach": post.get("insights", {})
                .get("data", [{}])[0]
                .get("values", [{}])[0]
                .get("value"),
                "facebook_post_id": post.get("id"),
                "facebook_is_event_post": post.get("attachments", {})
                .get("data", [{}])[0]
                .get("type")
                == "event",
            }

            attachments = self._extract_facebook_attachments(post)
            existing_post = existing_posts_by_facebook_post_id.get(post.get("id"))
            if existing_post:
                if attachments.get("stream_post_image_ids"):
                    values["stream_post_image_ids"] = [Command.clear()] + attachments[
                        "stream_post_image_ids"
                    ]
                existing_post.sudo().write(values)
            elif attachments or values["message"]:
                values.update(attachments)
                posts_to_create.append(values)

        stream_posts = self.env["social.stream.post"].sudo().create(posts_to_create)
        return any(
            stream_post.stream_id.create_uid.id == self.env.uid
            for stream_post in stream_posts
        )

    @api.model
    def _extract_facebook_attachments(self, post):
        result = {}

        for attachment in post.get("attachments", {}).get("data", []):
            if attachment.get("type") == "share":
                result.update(
                    {
                        "link_title": attachment.get("title"),
                        "link_description": attachment.get("description"),
                        "link_url": attachment.get("url"),
                    }
                )

                if attachment.get("media"):
                    result.update(
                        {
                            "link_image_url": attachment.get("media")
                            .get("image")
                            .get("src")
                        }
                    )
            elif attachment.get("type") == "album":
                images = []
                images_urls = []
                for sub_image in attachment.get("subattachments", {}).get("data", []):
                    image_url = sub_image.get("media").get("image").get("src")
                    images.append({"image_url": image_url})
                    images_urls.append(image_url)

                if images:
                    result.update(
                        {
                            "stream_post_image_ids": [
                                Command.create(attachment) for attachment in images
                            ],
                        }
                    )
            elif attachment.get("type") in ["photo", "animated_image_video"]:
                image_src = attachment.get("media", {}).get("image", {}).get("src")
                if image_src:
                    result.update(
                        {
                            "stream_post_image_ids": [
                                Command.create({"image_url": image_src})
                            ]
                        }
                    )

            elif attachment.get("type") == "event":
                result.update(
                    {
                        "link_title": attachment.get("title"),
                        "link_description": attachment.get("description"),
                        "link_url": attachment.get("target", {}).get("url", ""),
                    }
                )

                image_src = attachment.get("media", {}).get("image", {}).get("src")
                if image_src:
                    result.update(
                        {
                            "stream_post_image_ids": [
                                Command.create({"image_url": image_src})
                            ]
                        }
                    )

        return result

    @api.model
    def _format_facebook_message(self, message, tags):
        if not message:
            return message

        def remove_forged_tags(message):
            return re.sub(r"\B@\[", "@ [", message)

        tags = [tag for tag in tags or [] if not tag.get("name", "").startswith("#")]

        message_index = 0
        message_with_tags = ""
        for tag in tags or []:
            no_space_name = re.sub(r"\s+", "-", re.sub(r"\s*-\s*", "-", tag["name"]))
            forged_tag = "@[%s] %s" % (tag["id"], no_space_name)
            message_with_tags += (
                remove_forged_tags(message[message_index : tag["offset"]]) + forged_tag
            )
            message_index = tag["offset"] + tag["length"]

        message_with_tags += remove_forged_tags(message[message_index:])

        return message_with_tags
