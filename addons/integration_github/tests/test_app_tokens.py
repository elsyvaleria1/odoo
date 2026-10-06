import base64
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from odoo.exceptions import ValidationError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.libs.secret import Secret
from odoo.tests import TransactionCase, tagged

from odoo.addons.integration_github.models import integration_connection
from odoo.addons.integration_github.tools import (
    app_jwt,
    get_github_client,
    mint_installation_token,
)


def _pem(key) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _authorization(call) -> str:
    value = call.kwargs["headers"]["Authorization"]
    return value.reveal() if isinstance(value, Secret) else value


def _unb64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


@tagged("post_install", "-at_install", "integration_github", "github")
class TestAppTokens(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        service = cls.env.ref("integration_github.service_github")
        cls.credential = cls.env["credential.credential"].create(
            {
                "name": "GitHub App",
                "endpoint_id": service.id,
                "company_id": cls.env.company.id,
                "environment": service.environment,
                "category_id": cls.env.ref(
                    "integration_github.credential_category_github_app"
                ).id,
                "credential_data": json_dumps(
                    {
                        "app_id": "12345",
                        "private_key": _pem(cls.key),
                        "installation_id": "42",
                    }
                ),
            }
        )

    def test_the_jwt_is_rs256_signed_by_the_app_and_short_lived(self):
        token = app_jwt("12345", _pem(self.key), now=1_000_000)
        header, claims, signature = token.split(".")
        self.assertEqual(json_loads(_unb64(header)), {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(
            json_loads(_unb64(claims)),
            {"iat": 999_940, "exp": 1_000_540, "iss": "12345"},
        )
        self.key.public_key().verify(
            _unb64(signature),
            f"{header}.{claims}".encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

    def test_only_an_rsa_key_signs(self):
        with self.assertRaises(ValueError):
            app_jwt("1", _pem(ec.generate_private_key(ec.SECP256R1())))

    @patch("requests.Session.request")
    def test_a_token_is_minted_for_the_named_repositories_and_not_logged(self, request):
        response = Mock(status_code=201, headers={"content-type": "application/json"})
        response.json.return_value = {
            "token": "ghs_minted",
            "expires_at": "2026-10-06T23:00:00Z",
            "repositories": [{"full_name": "Agro-Marin/agromarin"}],
        }
        request.return_value = response
        Exchange = self.env["integration.exchange"]
        before = Exchange.search_count([])
        minted = mint_installation_token(
            self.env,
            self.credential,
            ["agromarin"],
            {"contents": "write", "pull_requests": "write"},
        )
        self.assertEqual(minted.token, "ghs_minted")
        self.assertEqual(minted.repositories, ("Agro-Marin/agromarin",))
        call = request.call_args
        self.assertTrue(
            call.kwargs["url"].endswith("/app/installations/42/access_tokens")
        )
        self.assertTrue(_authorization(call).startswith("Bearer eyJ"))
        self.assertEqual(
            call.kwargs["json"],
            {
                "repositories": ["agromarin"],
                "permissions": {"contents": "write", "pull_requests": "write"},
            },
        )
        self.env.flush_all()
        self.assertEqual(Exchange.search_count([]), before)

    def test_an_incomplete_app_credential_is_refused(self):
        with self.assertRaises(ValidationError):
            self.credential.credential_data = json_dumps({"app_id": "1"})

    @patch("requests.Session.request")
    def test_an_app_credential_calls_github_with_an_installation_token(self, request):
        integration_connection._tokens.clear()
        self.addCleanup(integration_connection._tokens.clear)
        minted = Mock(status_code=201, headers={"content-type": "application/json"})
        minted.json.return_value = {
            "token": "ghs_installation",
            "expires_at": "2999-01-01T00:00:00Z",
        }
        user = Mock(status_code=200, headers={"content-type": "application/json"})
        user.json.return_value = {"login": "agro-marin[bot]"}
        request.side_effect = [minted, user, user]
        client = get_github_client(self.env)
        client.get_user("agro-marin[bot]")
        client.get_user("agro-marin[bot]")
        mint, first, second = request.call_args_list
        self.assertTrue(mint.kwargs["url"].endswith("/access_tokens"))
        self.assertTrue(_authorization(mint).startswith("Bearer eyJ"))
        self.assertEqual(mint.kwargs["json"], {}, "the whole installation")
        for call in (first, second):
            self.assertEqual(_authorization(call), "Bearer ghs_installation")
