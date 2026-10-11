from collections.abc import Iterator
from typing import Any

from odoo.exceptions import UserError

from odoo.addons.integration.tools import CommError, get_api_client

API_ROOT = "https://api.twilio.com"
API_VERSION = "2010-04-01"
LIST_PAGE_SIZE = 1000


class TwilioError(CommError):
    def __init__(
        self, message: str, *, code: int | None = None, status_code: int | None = None
    ) -> None:
        super().__init__(message, status_code)
        self.code = code


class TwilioClient:
    def __init__(self, config) -> None:
        config.check_singleton()
        self.config = config
        self.env = config.env
        self.company = config.company_id
        self.account_sid = config._get_held_secret("username")
        if not self.account_sid:
            raise UserError(
                self.env._(
                    "%(company)s has no Twilio account configured.",
                    company=self.company.display_name,
                )
            )
        self._client = get_api_client(self.env, "twilio", self.company.id)

    def account_url(self, resource: str = "") -> str:
        path = f"/{API_VERSION}/Accounts/{self.account_sid}"
        return (
            f"{API_ROOT}{path}/{resource}.json"
            if resource
            else f"{API_ROOT}{path}.json"
        )

    def request(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        return self._client.request(method, url, raise_for_status=False, **kwargs)

    def call(self, method: str, resource: str, **kwargs) -> dict[str, Any]:
        url = resource if resource.startswith(API_ROOT) else self.account_url(resource)
        response = self.request(method, url, **kwargs)
        body = response["body"] if isinstance(response["body"], dict) else {}
        if response["status_code"] >= 400:
            raise TwilioError(
                body.get("message") or str(response["status_code"]),
                code=body.get("code"),
                status_code=response["status_code"],
            )
        return body

    def iterate(
        self, resource: str, key: str, params: dict | None = None, max_pages: int = 50
    ) -> Iterator[dict]:
        page = self.call(
            "GET", resource, params={"PageSize": LIST_PAGE_SIZE, **(params or {})}
        )
        for _page_number in range(max_pages):
            yield from page.get(key) or []
            next_page = page.get("next_page_uri")
            if not next_page:
                return
            page = self.call("GET", f"{API_ROOT}{next_page}")

    def download(self, url: str, **kwargs):
        return self._client.request(
            "GET", url, raw=True, raise_for_status=True, **kwargs
        )
