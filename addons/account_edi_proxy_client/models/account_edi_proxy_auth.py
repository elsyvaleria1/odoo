import base64
import hashlib
import hmac
import json
import time
from typing import Literal
from urllib.parse import parse_qs, urlsplit

import requests

from odoo.libs.json import loads as json_loads


class OdooEdiProxyAuth(requests.auth.AuthBase):

    def __init__(
        self, user=False, auth_type: Literal["hmac", "asymmetric"] = "hmac"
    ) -> None:
        self.id_client = (user and user.id_client) or False
        self.auth_type = auth_type
        self.refresh_token = (user and user.sudo().refresh_token) or False
        self.private_key = (user and user.sudo().private_key_id) or False

    def __get_payload(self, request, msg_timestamp) -> str:
        parsed_url = urlsplit(request.path_url)

        body = request.body
        if isinstance(body, bytes):
            body = body.decode()
        body = json_loads(body)

        query_dict = {
            k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed_url.query).items()
        }

        return "%s|%s|%s|%s|%s" % (
            msg_timestamp,
            parsed_url.path,
            self.id_client,
            json.dumps(query_dict, sort_keys=True),
            json.dumps(body, sort_keys=True),
        )

    def __sign_request_with_token(self, message):
        h = hmac.new(
            base64.b64decode(self.refresh_token),
            message.encode(),
            digestmod=hashlib.sha256,
        )

        return h.hexdigest()

    def __sign_with_private_key(self, message):
        return self.private_key._sign(message.encode(), formatting="base64").decode()

    def __call__(self, request):
        if not self.id_client:
            return request

        timestamp = int(time.time())
        request.headers.update(
            {
                "odoo-edi-client-id": self.id_client,
                "odoo-edi-timestamp": timestamp,
            }
        )
        message = self.__get_payload(request, timestamp)

        if self.auth_type == "asymmetric" and self.private_key:
            request.headers.update(
                {
                    "odoo-edi-signature": self.__sign_with_private_key(message),
                    "odoo-edi-signature-type": "asymmetric",
                }
            )
        elif self.refresh_token:
            request.headers.update(
                {
                    "odoo-edi-signature": self.__sign_request_with_token(message),
                    "odoo-edi-signature-type": "hmac",
                }
            )

        return request
