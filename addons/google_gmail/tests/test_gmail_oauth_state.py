from odoo.tests import tagged

from odoo.addons.google_gmail.models.mixin_google_gmail import GMAIL
from odoo.addons.mail_oauth2.tests import common


@tagged("post_install", "-at_install")
class TestGmailOAuthState(common.OAuth2StateFlowCase):
    allow_inherited_tests_method = True
    provider = GMAIL
    open_method = "open_google_gmail_uri"
    refresh_token_method = "_get_gmail_refresh_token"
    controller_logger = "odoo.addons.google_gmail.controllers.main"
