import base64
import logging
from itertools import batched

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.json import loads as json_loads
from odoo.libs.web import urljoin as url_join
from odoo.tools import iap

_logger = logging.getLogger(__name__)

try:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import service_account
except ImportError:
    service_account = None


class SocialAccount(models.Model):
    _inherit = "social.account"

    website_id = fields.Many2one(
        comodel_name="website",
        ondelete="cascade",
        help="This firebase configuration will only be used for the specified website",
    )
    firebase_use_own_account = fields.Boolean(
        related="website_id.firebase_use_own_account",
        string="Use your own Firebase account",
    )
    firebase_project_id = fields.Char(
        related="website_id.firebase_project_id",
        string="Firebase Project ID",
    )
    firebase_web_api_key = fields.Char(
        related="website_id.firebase_web_api_key",
        string="Firebase Web API Key",
    )
    firebase_web_app_id = fields.Char(
        related="website_id.firebase_web_app_id",
        string="Firebase Web App ID",
    )
    firebase_push_certificate_key = fields.Char(
        related="website_id.firebase_push_certificate_key",
        string="Firebase Push Certificate Key",
    )
    firebase_sender_id = fields.Char(
        related="website_id.firebase_sender_id",
        string="Firebase Sender ID",
    )
    firebase_admin_key_file = fields.Binary(
        related="website_id.firebase_admin_key_file",
        string="Firebase Admin Key File",
    )

    notification_request_title = fields.Char(
        related="website_id.notification_request_title",
        string="Notification Request Title",
    )
    notification_request_body = fields.Text(
        related="website_id.notification_request_body",
        string="Notification Request Text",
    )
    notification_request_delay = fields.Integer(
        related="website_id.notification_request_delay",
        string="Notification Request Delay (seconds)",
    )
    notification_request_icon = fields.Binary(
        related="website_id.notification_request_icon",
        string="Notification Request Icon",
    )

    _website_unique = models.Constraint(
        "unique(website_id)",
        "There is already a configuration for this website.",
    )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_push_notification_account(self) -> None:
        if not self.env.user.has_group("base.group_system") and any(
            account.website_id for account in self
        ):
            raise UserError(self.env._("You can't delete a Push Notification account."))

    def _firebase_send_message(self, data, visitors) -> None:
        visitors = visitors.filtered(lambda visitor: visitor.push_subscription_ids)
        if self.firebase_use_own_account:
            self._firebase_send_message_from_configuration(data, visitors)
        else:
            self._firebase_send_message_from_iap(data, visitors)

    def _firebase_send_message_from_configuration(self, data, visitors):

        if not visitors:
            return [], []

        if not self.firebase_admin_key_file:
            raise UserError(
                self.env._("Firebase Admin Key File is missing from the configuration.")
            )

        tokens = visitors.mapped("push_subscription_ids.push_token")
        if service_account:
            firebase_data = json_loads(
                base64.b64decode(self.firebase_admin_key_file).decode()
            )
            firebase_credentials = (
                service_account.Credentials.from_service_account_info(
                    firebase_data,
                    scopes=["https://www.googleapis.com/auth/firebase.messaging"],
                )
            )
            firebase_credentials.refresh(google_requests.Request())
            auth_token = firebase_credentials.token

            for token in tokens:
                self.env["ir.egress"].request(
                    "POST",
                    f"https://fcm.googleapis.com/v1/projects/{firebase_data['project_id']}/messages:send",
                    purpose="firebase",
                    json={
                        "message": {
                            "token": token,
                            "notification": {
                                "title": data["title"],
                                "body": data["body"],
                                "image": data["icon"],
                            },
                            "data": {"target_url": data["target_url"]},
                        }
                    },
                    headers={"authorization": f"Bearer {auth_token}"},
                    timeout=5,
                )
        else:
            raise UserError(
                self.env._(
                    'You have to install "google_auth>=1.18.0" to be able to send push notifications.'
                )
            )

        return tokens

    def _firebase_send_message_from_iap(self, data, visitors) -> list:
        social_iap_endpoint = self.env.registry.settings.get(
            self.env,
            "social.social_iap_endpoint",
            self.env["social.media"]._DEFAULT_SOCIAL_IAP_ENDPOINT,
        )
        batch_size = 100

        tokens = visitors.mapped("push_subscription_ids.push_token")
        data.update(
            {
                "db_uuid": self.env.registry.settings.get(
                    self.env, "database.uuid", False
                )
            }
        )
        for tokens_batch in (
            list(b) for b in batched(tokens, batch_size, strict=False)
        ):
            batch_data = dict(data)
            batch_data["tokens"] = tokens_batch
            iap.jsonrpc(
                url_join(
                    social_iap_endpoint,
                    "/iap/social_push_notifications/firebase_send_message",
                ),
                params=batch_data,
                env=self.env,
            )

        return []
