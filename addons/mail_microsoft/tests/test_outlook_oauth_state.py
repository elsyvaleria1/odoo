from odoo.tests import tagged

from odoo.addons.mail_microsoft.models.mixin_microsoft_outlook import OUTLOOK
from odoo.addons.mail_oauth2.tests import common


@tagged("post_install", "-at_install")
class TestOutlookOAuthState(common.OAuth2StateFlowCase):
    allow_inherited_tests_method = True
    provider = OUTLOOK
    open_method = "open_microsoft_outlook_uri"
    refresh_token_method = "_get_outlook_refresh_token"
    controller_logger = "odoo.addons.mail_microsoft.controllers.main"
