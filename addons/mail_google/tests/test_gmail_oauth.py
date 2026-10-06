from odoo.tests import tagged

from odoo.addons.mail_google.models.integration_service import LEGACY_CALLBACK_PATH
from odoo.addons.mail_oauth2.tests.common import OAuthMailServerCase


@tagged("post_install", "-at_install")
class TestGmailAuthorization(OAuthMailServerCase):
    service_xmlid = "integration_google.service_google"
    authorize_method = "action_mail_google_authorize"
    legacy_path = LEGACY_CALLBACK_PATH
    type_value = "gmail"
    server_values = {
        "smtp_host": "smtp.gmail.com",
        "smtp_encryption": "starttls_strict",
        "smtp_port": 587,
    }
    scope_words = ("https://mail.google.com/", "openid", "email")
