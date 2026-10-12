import base64
import json
import secrets
from hashlib import sha256
from urllib.parse import urlsplit

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import SQL

from odoo.addons.auth_passkey._vendor.webauthn import (
    base64url_to_bytes,
    verify_authentication_response,
)

UP, UV = 0x01, 0x04


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class SoftwarePasskey:
    def __init__(self, env, user):
        self.key = ec.generate_private_key(ec.SECP256R1())
        numbers = self.key.public_key().public_numbers()
        cose = cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )
        self.credential_id = b64url(secrets.token_bytes(16))
        self.user = user
        self.record = (
            env["auth.passkey.key"]
            .with_user(user)
            .sudo()
            .create({"name": "software", "credential_identifier": self.credential_id})
        )
        env.cr.execute(
            SQL(
                "UPDATE auth_passkey_key SET public_key = %s WHERE id = %s",
                base64.urlsafe_b64encode(cose).decode(),
                self.record.id,
            )
        )
        self.record.invalidate_recordset()

    def sign(
        self, challenge: str, origin: str, sign_count: int = 1, flags: int = UP | UV
    ):
        rp_id = urlsplit(origin).hostname
        authenticator_data = (
            sha256(rp_id.encode()).digest()
            + bytes([flags])
            + sign_count.to_bytes(4, "big")
        )
        client_data = json.dumps(
            {
                "type": "webauthn.get",
                "challenge": challenge,
                "origin": origin,
                "crossOrigin": False,
            }
        ).encode()
        signature = self.key.sign(
            authenticator_data + sha256(client_data).digest(),
            ec.ECDSA(hashes.SHA256()),
        )
        return {
            "id": self.credential_id,
            "rawId": self.credential_id,
            "type": "public-key",
            "response": {
                "authenticatorData": b64url(authenticator_data),
                "clientDataJSON": b64url(client_data),
                "signature": b64url(signature),
                "userHandle": b64url(str(self.user.id).encode()),
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }


@tagged("at_install", "-post_install")
class TestPasskeyProof(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="passkey_giver")
        cls.other_user = new_test_user(cls.env, login="passkey_other")
        cls.passkey = SoftwarePasskey(cls.env, cls.user)
        cls.other_passkey = SoftwarePasskey(cls.env, cls.other_user)
        cls.method = cls.env.ref("auth_passkey_proof.proof_method_passkey")
        cls.subject = cls.env["res.partner"].create({"name": "Handover subject"})
        cls.facts = {"amount": "1500.00", "currency": "MXN"}
        base_url = urlsplit(cls.env["auth.passkey.key"].get_base_url())
        cls.origin = f"{base_url.scheme}://{base_url.netloc}"

    def _issue(self, user=None):
        return (
            self.env["proof.challenge"]
            .with_user(user or self.user)
            ._issue(self.subject, "test.handover", self.facts, self.method)
        )

    def _options(self, params):
        return params["methods"][0]["options"]

    def _redeem(self, params, credential, user=None):
        return (
            self.env["proof.challenge"]
            .with_user(user or self.user)
            ._redeem(
                params["token"],
                "passkey",
                {"credential": credential},
                self.subject,
                "test.handover",
                self.facts,
            )
        )

    def test_options_ask_the_users_own_passkey_with_verification(self):
        params = self._issue()

        options = self._options(params)

        self.assertEqual(options["userVerification"], "required")
        self.assertEqual(
            [credential["id"] for credential in options["allowCredentials"]],
            [self.passkey.credential_id],
        )
        self.assertEqual(options["rpId"], urlsplit(self.origin).hostname)

    def test_passkey_proof_is_recorded_as_a_signature(self):
        params = self._issue()
        credential = self.passkey.sign(self._options(params)["challenge"], self.origin)

        evidence = self._redeem(params, credential)

        self.assertEqual(evidence.method_code, "passkey")
        self.assertEqual(evidence.strength, "cryptographic")
        self.assertEqual(evidence.payload["credential_id"], self.passkey.credential_id)
        self.assertEqual(
            evidence.payload["signature"], credential["response"]["signature"]
        )
        self.assertEqual(evidence.payload["sign_count"], 1)
        self.assertEqual(self.passkey.record.sudo().sign_count, 1)

    def test_the_evidence_alone_proves_the_signature_over_the_figures(self):
        params = self._issue()
        evidence = self._redeem(
            params, self.passkey.sign(self._options(params)["challenge"], self.origin)
        ).sudo()
        payload = evidence.payload

        expected = sha256(f"{evidence.nonce}:{evidence.digest}".encode()).digest()
        verification = verify_authentication_response(
            credential={
                "id": payload["credential_id"],
                "rawId": payload["credential_id"],
                "type": "public-key",
                "response": {
                    "authenticatorData": payload["authenticator_data"],
                    "clientDataJSON": payload["client_data_json"],
                    "signature": payload["signature"],
                    "userHandle": payload["user_handle"],
                },
            },
            expected_challenge=expected,
            expected_origin=payload["origin"],
            expected_rp_id=payload["rp_id"],
            credential_public_key=base64url_to_bytes(payload["public_key"]),
            credential_current_sign_count=0,
            require_user_verification=True,
        )

        self.assertEqual(b64url(expected), payload["challenge"])
        self.assertEqual(verification.new_sign_count, 1)

    def test_another_users_passkey_is_refused(self):
        params = self._issue()
        credential = self.other_passkey.sign(
            self._options(params)["challenge"], self.origin
        )

        with self.assertRaisesRegex(UserError, "did not confirm"):
            self._redeem(params, credential)

    def test_a_signature_over_another_challenge_is_refused(self):
        params = self._issue()
        other = self._issue()
        credential = self.passkey.sign(self._options(other)["challenge"], self.origin)

        with self.assertRaisesRegex(UserError, "did not confirm"):
            self._redeem(params, credential)

    def test_a_passkey_used_without_user_verification_is_refused(self):
        params = self._issue()
        credential = self.passkey.sign(
            self._options(params)["challenge"], self.origin, flags=UP
        )

        with self.assertRaisesRegex(UserError, "did not confirm"):
            self._redeem(params, credential)

    def test_a_sign_count_going_back_is_refused(self):
        self.env.cr.execute(
            SQL(
                "UPDATE auth_passkey_key SET sign_count = 10 WHERE id = %s",
                self.passkey.record.id,
            )
        )
        params = self._issue()
        credential = self.passkey.sign(
            self._options(params)["challenge"], self.origin, sign_count=5
        )

        with self.assertRaisesRegex(UserError, "did not confirm"):
            self._redeem(params, credential)

    def test_another_origin_is_refused(self):
        params = self._issue()
        credential = self.passkey.sign(
            self._options(params)["challenge"], "https://phishing.example"
        )

        with self.assertRaisesRegex(UserError, "did not confirm"):
            self._redeem(params, credential)

    def test_a_user_without_a_passkey_is_not_offered_the_method(self):
        newcomer = new_test_user(self.env, login="passkey_newcomer")

        with self.assertRaisesRegex(UserError, "no way set up"):
            self._issue(user=newcomer)
