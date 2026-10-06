from odoo.tests import tagged

from odoo.addons.mail_microsoft.models.integration_service import (
    LEGACY_CALLBACK_PATH,
)
from odoo.addons.mail_oauth2.tests.common import OAuthMailServerCase


@tagged("post_install", "-at_install")
class TestOutlookAuthorization(OAuthMailServerCase):
    service_xmlid = "integration_microsoft.service_microsoft"
    authorize_method = "action_mail_microsoft_authorize"
    legacy_path = LEGACY_CALLBACK_PATH
    type_value = "outlook"
    server_values = {
        "smtp_host": "smtp.outlook.com",
        "smtp_encryption": "starttls_strict",
        "smtp_port": 587,
    }
    scope_words = (
        "openid",
        "email",
        "offline_access",
        "https://outlook.office.com/SMTP.Send",
    )
