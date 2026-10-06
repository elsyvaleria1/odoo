from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    firebase_enable_push_notifications = fields.Boolean(
        related="website_id.firebase_enable_push_notifications",
        string="Enable Web Push Notifications",
        readonly=False,
    )
    firebase_use_own_account = fields.Boolean(
        related="website_id.firebase_use_own_account",
        string="Use your own Firebase account",
        readonly=False,
    )
    firebase_project_id = fields.Char(
        related="website_id.firebase_project_id",
        string="Firebase Project ID",
        readonly=False,
    )
    firebase_web_api_key = fields.Char(
        related="website_id.firebase_web_api_key",
        string="Firebase Web API Key",
        readonly=False,
    )
    firebase_web_app_id = fields.Char(
        related="website_id.firebase_web_app_id",
        string="Firebase Web App ID",
        readonly=False,
    )
    firebase_push_certificate_key = fields.Char(
        related="website_id.firebase_push_certificate_key",
        string="Firebase Push Certificate Key",
        readonly=False,
    )
    firebase_sender_id = fields.Char(
        related="website_id.firebase_sender_id",
        string="Firebase Sender ID",
        readonly=False,
    )
    firebase_admin_key_file = fields.Binary(
        related="website_id.firebase_admin_key_file",
        string="Firebase Admin Key File",
        readonly=False,
    )

    notification_request_title = fields.Char(
        related="website_id.notification_request_title",
        string="Notification Request Title",
        readonly=False,
    )
    notification_request_body = fields.Text(
        related="website_id.notification_request_body",
        string="Notification Request Text",
        readonly=False,
    )
    notification_request_delay = fields.Integer(
        related="website_id.notification_request_delay",
        string="Notification Request Delay (seconds)",
        readonly=False,
    )
    notification_request_icon = fields.Binary(
        related="website_id.notification_request_icon",
        string="Notification Request Icon",
        readonly=False,
    )
