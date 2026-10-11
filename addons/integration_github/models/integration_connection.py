import threading
import time

from odoo import models
from odoo.libs.debug_log import DebugLog
from odoo.libs.secret import Secret

from ..tools.app import APP_CATEGORY, app_jwt, mint_installation_token

_debug = DebugLog(__name__)

_TOKEN_MARGIN = 300
_tokens: dict[tuple[int, str], tuple[str, float]] = {}
_tokens_lock = threading.Lock()


class IntegrationConnection(models.Model):
    _inherit = "integration.connection"

    def _get_auth_headers(self) -> dict[str, str | Secret]:
        credential = self.credential_id
        if not credential or credential.category_id.code != APP_CATEGORY:
            return super()._get_auth_headers()
        if self.env.context.get("github_app_jwt"):
            secrets = credential._use_secret_payload("integration_github:app_jwt")
            token = app_jwt(secrets["app_id"], secrets["private_key"])
        else:
            token = self._github_installation_token()
        return {"Authorization": Secret.of(token).prefixed("Bearer ")}

    def _github_installation_token(self) -> str:
        credential = self.credential_id
        key = (credential.id, str(credential.write_date))
        with _tokens_lock:
            cached = _tokens.get(key)
        if cached and cached[1] - _TOKEN_MARGIN > time.time():
            return cached[0]
        minted = mint_installation_token(self.env, credential, None, None)
        expires = _epoch(minted.expires_at)
        with _tokens_lock:
            _tokens[key] = (minted.token, expires)
        _debug.logic("github.installation_token_minted", credential=credential.id)
        return minted.token


def _epoch(stamp: str) -> float:
    return time.mktime(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
