import base64
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, urlsplit

import requests

from odoo.libs.json import loads as json_loads


class OdooFinAuth(requests.auth.AuthBase):
    """Signature helper adding the OdooFin authentication headers to a request."""

    def __init__(self, record=None) -> None:
        self.access_token = (record and record.access_token) or False
        self.refresh_token = (record and record.refresh_token) or False
        self.client_id = (record and record.client_id) or False

    def __call__(self, request):
        if not self.client_id or not self.refresh_token:
            return request
        msg_timestamp = int(time.time())
        parsed_url = urlsplit(request.path_url)

        body = request.body
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        body = json_loads(body)

        query_params = {}
        for key, value in parse_qsl(parsed_url.query, keep_blank_values=True):
            query_params.setdefault(key, value)

        message = "%s|%s|%s|%s|%s|%s" % (
            msg_timestamp,
            parsed_url.path,
            self.client_id,
            self.access_token,
            json.dumps(query_params, sort_keys=True),
            json.dumps(body, sort_keys=True),
        )

        h = hmac.new(
            base64.b64decode(self.refresh_token),
            message.encode("utf-8"),
            digestmod=hashlib.sha256,
        )

        request.headers.update(
            {
                "odoofin-client-id": self.client_id,
                "odoofin-access-token": self.access_token,
                "odoofin-signature": base64.b64encode(h.digest()),
                "odoofin-timestamp": msg_timestamp,
            }
        )
        return request
