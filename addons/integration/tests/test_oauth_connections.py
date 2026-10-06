from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestOAuthConnections(TransactionCase):
    """What a feature asks of a vendor's OAuth service: a user's own connection
    to it, the client every connection authorizes with, kept in the vault, and
    tokens authorized before connections existed carried over."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["integration.service"].create(
            {
                "name": "Vendor",
                "code": "vendor_oauth",
                "endpoint_url": "https://api.vendor.test",
                "environment": "production",
                "auth_type": "oauth2",
                "allow_user_credentials": True,
                "oauth_auth_endpoint": "https://login.vendor.test/authorize",
                "oauth_token_endpoint": "https://login.vendor.test/token",
                "oauth_scope": False,
            }
        )
        cls.user = new_test_user(cls.env, login="vendor_user")
        cls.Connection = cls.env["integration.connection"]

    def _authorize(self, connection):
        connection._oauth_store_tokens(
            {"access_token": "access", "refresh_token": "refresh", "expires_in": 60},
            "https://odoo.test/integration/oauth/callback",
        )

    def test_a_user_has_one_personal_connection(self):
        first = self.Connection._personal(self.service, self.user, scope="calendar")

        self.assertEqual(first.user_id, self.user)
        self.assertEqual(first.company_id, self.user.company_id)
        self.assertEqual(first.oauth_scope, "calendar")
        self.assertEqual(self.Connection._personal(self.service, self.user), first)
        self.assertEqual(self.Connection._find_personal(self.service, self.user), first)

    def test_finding_creates_nothing(self):
        self.assertFalse(self.Connection._find_personal(self.service, self.user))
        self.assertFalse(
            self.Connection.sudo().search([("service_id", "=", self.service.id)])
        )

    def test_a_scope_added_later_is_asked_for_again(self):
        connection = self.Connection._personal(self.service, self.user, "calendar")
        self._authorize(connection)
        self.assertTrue(connection._is_oauth_authorized())

        self.Connection._personal(self.service, self.user, scope="mail calendar")

        self.assertEqual(connection.oauth_scope, "calendar mail")
        self.assertTrue(connection.needs_reauthorization)
        self.assertFalse(connection._is_oauth_authorized())

    def test_a_scope_already_granted_changes_nothing(self):
        connection = self.Connection._personal(self.service, self.user, "calendar")
        self._authorize(connection)

        self.Connection._personal(self.service, self.user, scope="calendar")

        self.assertTrue(connection._is_oauth_authorized())

    def test_forgetting_an_authorization_removes_its_tokens(self):
        connection = self.Connection._personal(self.service, self.user)
        self._authorize(connection)
        credential = connection.credential_id

        connection._forget_oauth_authorization()

        self.assertFalse(credential.exists())
        self.assertFalse(connection.credential_id)
        self.assertFalse(connection.oauth_redirect_uri)
        self.assertFalse(connection._is_oauth_authorized())

    def test_the_authorize_url_carries_the_return_path(self):
        connection = self.Connection._personal(self.service, self.user)

        self.assertEqual(
            connection._oauth_authorize_url("/odoo/calendar?view=week"),
            f"/integration/oauth/authorize/{connection.id}"
            "?return_url=%2Fodoo%2Fcalendar%3Fview%3Dweek",
        )

    def test_the_client_is_kept_in_the_vault_for_the_company(self):
        self.assertFalse(self.service._has_oauth_client())

        self.service._set_oauth_client("the-client", "the-secret")

        app = self.service._oauth_app_connection()
        self.assertEqual(app.company_id, self.env.company)
        self.assertEqual(app._oauth_client(), ("the-client", "the-secret"))
        self.assertTrue(self.service._has_oauth_client())
        self.assertEqual(self.service._oauth_client_id(), "the-client")
        personal = self.Connection._personal(self.service, self.user)
        self.assertEqual(personal._oauth_client(), ("the-client", "the-secret"))

    def test_a_client_kept_for_every_company_serves_each(self):
        self.service._set_oauth_client("shared", "shared-secret", company=False)
        other = self.env["res.company"].create({"name": "Other Vendor Company"})

        self.assertEqual(self.service._oauth_client_id(other), "shared")
        self.assertFalse(self.service._oauth_app_connection(other).company_id)

    def test_a_kept_client_is_edited_in_place(self):
        self.service._set_oauth_client("first", "first-secret")
        app = self.service._oauth_app_connection()

        self.service._set_oauth_client("second", None)

        self.assertEqual(self.service._oauth_app_connection(), app)
        self.assertEqual(app._oauth_client(), ("second", "first-secret"))

    def test_a_new_client_needs_its_secret(self):
        with self.assertRaises(ValidationError):
            self.service._set_oauth_client("no-secret", None)

    def test_tokens_from_before_connections_are_adopted(self):
        self.service.oauth_redirect_path = "/integration/oauth/callback"
        credential = self.env["credential.credential"].create(
            {
                "name": "Old tokens",
                "category_id": self.env.ref("credential.credential_category_oauth2").id,
                "oauth_access_token": "old-access",
                "oauth_refresh_token": "old-refresh",
            }
        )

        connection = self.Connection._personal(self.service, self.user, "calendar")
        connection._adopt_credential(credential)

        self.assertEqual(connection.credential_id, credential)
        self.assertEqual(credential.owner_user_id, self.user)
        self.assertTrue(connection._is_oauth_authorized())
        self.assertTrue(
            connection.oauth_redirect_uri.endswith("/integration/oauth/callback")
        )

    def test_a_record_keeps_the_client_and_path_it_was_authorized_with(self):
        partner = self.env["res.partner"].create({"name": "Bound"})
        credential = self.env["credential.credential"].create(
            {
                "name": "Old record tokens",
                "category_id": self.env.ref("credential.credential_category_oauth2").id,
                "oauth_access_token": "old-access",
                "oauth_refresh_token": "old-refresh",
            }
        )
        connection = self.Connection._bound(partner, self.service, "mail")

        connection._adopt_credential(
            credential,
            client={"oauth_client_id": "own", "oauth_client_secret": "own-secret"},
            redirect_path="/old/confirm",
        )

        self.assertEqual(connection._oauth_client(), ("own", "own-secret"))
        self.assertFalse(credential.owner_user_id)
        self.assertTrue(connection.oauth_redirect_uri.endswith("/old/confirm"))
        self.assertEqual(self.Connection._find_bound(partner), connection)
