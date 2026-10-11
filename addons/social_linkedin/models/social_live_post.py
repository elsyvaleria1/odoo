import contextlib
import logging
import re
from itertools import batched
from urllib.parse import urlparse

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.mail.tools import link_preview

_logger = logging.getLogger(__name__)

_THUMBNAIL_MAX_BYTES = 10 * 1024 * 1024


class SocialLivePost(models.Model):
    _inherit = "social.live.post"

    linkedin_post_id = fields.Char(string="Actual LinkedIn ID of the post")

    def _compute_live_post_link(self) -> None:
        linkedin_live_posts = self._filtered_by_media_types(["linkedin"]).filtered(
            lambda post: post.state == "posted"
        )
        super(SocialLivePost, (self - linkedin_live_posts))._compute_live_post_link()

        for post in linkedin_live_posts:
            post.live_post_link = (
                "https://www.linkedin.com/feed/update/%s" % post.linkedin_post_id
            )

    def _refresh_statistics(self):
        super()._refresh_statistics()
        accounts = self.env["social.account"].search([("media_type", "=", "linkedin")])

        for account in accounts:
            linkedin_post_ids = (
                self.env["social.live.post"]
                .sudo()
                .search(
                    [
                        ("account_id", "=", account.id),
                        ("linkedin_post_id", "!=", False),
                    ],
                    order="create_date DESC",
                    limit=1000,
                )
            )
            if not linkedin_post_ids:
                continue

            linkedin_post_ids = {
                post.linkedin_post_id: post for post in linkedin_post_ids
            }

            session = self.env["ir.egress"].session(purpose="social_linkedin")

            for batch_linkedin_post_ids in batched(linkedin_post_ids, 50, strict=False):
                response = account._linkedin_request(
                    "socialMetadata",
                    session=session,
                    object_ids=batch_linkedin_post_ids,
                )

                if not response.ok or "results" not in response.json():
                    account._action_disconnect_accounts(response.json())
                    _logger.error(
                        "Error when fetching LinkedIn stats: %r.", response.text
                    )
                    break

                for urn, stats in response.json()["results"].items():
                    if not urn or not stats or urn not in batch_linkedin_post_ids:
                        continue

                    like_count = sum(
                        like.get("count", 0)
                        for like in stats.get("reactionSummaries", {}).values()
                    )
                    comment_count = stats.get("commentSummary", {}).get("count", 0)
                    linkedin_post_ids[urn].update(
                        {"engagement": like_count + comment_count}
                    )

    def _post(self):
        linkedin_live_posts = self._filtered_by_media_types(["linkedin"])
        super(SocialLivePost, (self - linkedin_live_posts))._post()

        linkedin_live_posts._post_linkedin()

    def _post_linkedin(self) -> None:
        for live_post in self:
            url_in_message = self.env["social.post"]._extract_url_from_message(
                live_post.message
            )

            data = {
                "author": live_post.account_id.linkedin_account_urn,
                "commentary": self._format_to_linkedin_little_text(live_post.message),
                "distribution": {"feedDistribution": "MAIN_FEED"},
                "lifecycleState": "PUBLISHED",
                "visibility": "PUBLIC",
            }

            if live_post.image_ids:
                try:
                    images_urn = [
                        live_post.account_id._linkedin_upload_image(
                            image_id.with_context(bin_size=False).raw
                        )
                        for image_id in live_post.image_ids
                    ]
                except UserError as e:
                    live_post.write({"state": "failed", "failure_reason": str(e)})
                    continue

                if len(images_urn) == 1:
                    data["content"] = {"media": {"id": images_urn[0]}}
                else:
                    data["content"] = {
                        "multiImage": {
                            "images": [{"id": image_urn} for image_urn in images_urn],
                        }
                    }

            elif url_in_message:
                tracker_code = urlparse(url_in_message).path.split("/r/")[-1]
                link_tracker = self.env["link.tracker"].search(
                    [
                        ("link_code_ids.code", "=", tracker_code),
                        ("source_id", "=", live_post.post_id.source_id.id),
                    ],
                    limit=1,
                )
                original_url = link_tracker.url or url_in_message
                data["content"] = {
                    "article": {
                        "source": url_in_message,
                        "title": link_tracker.title or original_url,
                    },
                }

                preview = (
                    link_preview.get_link_preview_from_url(
                        original_url, link_preview.get_link_preview_session(self.env)
                    )
                    or {}
                )
                if image_url := preview.get("og_image"):
                    with contextlib.suppress(Exception):
                        image_response = self.env["ir.egress"].request(
                            "GET",
                            image_url,
                            purpose="linkedin_thumbnail",
                            timeout=3,
                            max_bytes=_THUMBNAIL_MAX_BYTES,
                        )
                        if image_response.ok:
                            image_urn = self.account_id._linkedin_upload_image(
                                image_response.content
                            )
                            data["content"]["article"]["thumbnail"] = image_urn

            response = live_post.account_id._linkedin_request("posts", json=data)

            post_id = response.headers.get("x-restli-id")
            if response.ok and post_id:
                values = {
                    "state": "posted",
                    "failure_reason": False,
                    "linkedin_post_id": post_id,
                }
            else:
                try:
                    response_json = response.json()
                except ValueError:
                    response_json = {}
                values = {
                    "state": "failed",
                    "failure_reason": response_json.get(
                        "message", self.env._("unknown")
                    ),
                }

                if response_json.get("serviceErrorCode") == 65600:
                    self.account_id._action_disconnect_accounts(response)

            live_post.write(values)

    def _format_to_linkedin_little_text(self, input_string):
        pattern = r"[\(\)\<\>\{\}\[\]\_\|\*\~\#\@]"
        return re.sub(pattern, lambda match: rf"\{match.group(0)}", input_string)
