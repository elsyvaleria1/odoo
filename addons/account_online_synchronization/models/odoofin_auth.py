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
        # We don't sign request that still don't have a client_id/refresh_token
        if not self.client_id or not self.refresh_token:
            return request
        # craft the message (timestamp|url path|client_id|access_token|query params|body content)
        msg_timestamp = int(time.time())
        parsed_url = urlsplit(request.path_url)

        body = request.body
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        body = json_loads(body)

        # The odoofin proxy verifies this signature, so the serialized query
        # params must match the historical (werkzeug url_decode/MultiDict)
        # form exactly: blank values kept, first value wins on repeated keys.
        query_params = {}
        for key, value in parse_qsl(parsed_url.query, keep_blank_values=True):
            query_params.setdefault(key, value)

        message = "%s|%s|%s|%s|%s|%s" % (
            msg_timestamp,  # timestamp
            parsed_url.path,  # url path
            self.client_id,
            self.access_token,
            json.dumps(query_params, sort_keys=True),  # url query params sorted by key
            json.dumps(body, sort_keys=True),
        )  # http request body

        h = hmac.new(
            base64.b64decode(self.refresh_token),
            message.encode("utf-8"),
            digestmod=hashlib.sha256,
        )

        # OdooFin checks the integrity of the request on reception and raises Forbidden
        # when the signature doesn't match.
        request.headers.update(
            {
                "odoofin-client-id": self.client_id,
                "odoofin-access-token": self.access_token,
                "odoofin-signature": base64.b64encode(h.digest()),
                "odoofin-timestamp": msg_timestamp,
            }
        )
        return request
