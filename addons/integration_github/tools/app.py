import base64
import json
import time
from typing import Any, NamedTuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from odoo.addons.integration.tools.api_client import get_api_client

APP_CATEGORY = "github_app"
# GitHub refuses an app JWT that lives longer than ten minutes, and one issued in
# its future: it is dated a minute back for clock drift and expires in nine.
_JWT_BACKDATE = 60
_JWT_LIFETIME = 540


class InstallationToken(NamedTuple):
    token: str
    expires_at: str
    repositories: tuple[str, ...]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def app_jwt(
    app_id: str | int, private_key_pem: str, *, now: float | None = None
) -> str:
    """The RS256 JWT that authenticates a GitHub App as itself."""
    key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("a GitHub App key is an RSA private key")
    issued = int(now if now is not None else time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iat": issued - _JWT_BACKDATE,
        "exp": issued + _JWT_LIFETIME,
        "iss": str(app_id),
    }
    signing_input = ".".join(
        _b64(json.dumps(part, separators=(",", ":")).encode())
        for part in (header, claims)
    )
    signature = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64(signature)}"


def mint_installation_token(
    env: Any,
    credential: Any,
    repositories: list[str] | None,
    permissions: dict[str, str] | None,
) -> InstallationToken:
    """An installation token of the App ``credential``: limited to
    ``repositories`` (names within the installation's account) and
    ``permissions`` when given, the whole installation otherwise. GitHub lets it
    live an hour.

    The call is signed with the App's own JWT, and not logged: the answer is the
    token.
    """
    secrets = credential._use_secret_payload("integration_github:app_token")
    missing = {"app_id", "private_key", "installation_id"} - secrets.keys()
    if missing:
        raise ValueError(f"the GitHub App credential lacks {sorted(missing)}")
    scope: dict[str, Any] = {}
    if repositories is not None:
        scope["repositories"] = repositories
    if permissions is not None:
        scope["permissions"] = permissions
    client = get_api_client(
        env(context={**env.context, "github_app_jwt": True}),
        "github",
        credential.company_id.id or None,
        credential_id=credential.id,
    )
    body = client.post(
        f"/app/installations/{secrets['installation_id']}/access_tokens",
        json=scope,
        headers={"Accept": "application/vnd.github+json"},
        skip_logging=True,
    )["body"]
    return InstallationToken(
        body["token"],
        body["expires_at"],
        tuple(repo["full_name"] for repo in body.get("repositories", ())),
    )
