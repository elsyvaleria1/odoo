import logging
from datetime import UTC, datetime
from pprint import pformat
from typing import Self

from requests.auth import HTTPBasicAuth

from odoo.libs import guarded_http, netguard

str_type = (str, type(None))
_logger = logging.getLogger(__name__)


class AvataxClient:
    def __init__(
        self,
        app_name=None,
        app_version=None,
        machine_name=None,
        environment=None,
        timeout_limit=None,
    ) -> None:
        if not all(
            isinstance(i, str_type) for i in [app_name, machine_name, environment]
        ):
            raise ValueError("Input(s) must be string or none type object")
        self.base_url = "https://sandbox-rest.avatax.com"
        self.is_production = environment and environment.lower() == "production"
        if self.is_production:
            self.base_url = "https://rest.avatax.com"
        self.auth = None
        self.app_name = app_name
        self.app_version = app_version
        self.machine_name = machine_name
        self.client_id = f"{app_name}; {app_version}; Python SDK; 18.5; {machine_name};"
        self.client_header = {"X-Avalara-Client": self.client_id}
        self.timeout_limit = timeout_limit

    def add_credentials(self, username=None, password=None) -> Self:
        if not all(isinstance(i, str_type) for i in [username, password]):
            raise ValueError("Input(s) must be string or none type object")
        if username and not password:
            self.client_header["Authorization"] = "Bearer " + username
        else:
            self.auth = HTTPBasicAuth(username, password)
        return self

    def request(self, method, endpoint, params, json):
        start = str(datetime.now(UTC))
        url = f"{self.base_url}/api/v2/{endpoint}"
        with guarded_http.guarded_session(netguard.PUBLIC_ONLY) as session:
            response = session.request(
                method,
                url,
                auth=self.auth,
                headers=self.client_header,
                timeout=self.timeout_limit or 1200,
                params=params,
                json=json,
            ).json()
        end = str(datetime.now(UTC))
        if hasattr(self, "logger"):
            self.logger(
                f"{method}\nstart={start}\nend={end}\nargs={pformat(url)}\nparams={pformat(params)}\njson={pformat(json)}\n"
                f"response={pformat(response)}"
            )
        return response

    def create_transaction(self, model, include=None):
        return self.request(
            "POST",
            "transactions/createoradjust",
            params=include,
            json={"createTransactionModel": model},
        )

    def commit_transaction(self, companyCode, transactionCode):
        return self.request(
            "POST",
            f"companies/{companyCode}/transactions/{transactionCode}/commit",
            params=None,
            json={"commit": True},
        )

    def uncommit_transaction(self, companyCode, transactionCode):
        return self.request(
            "POST",
            f"companies/{companyCode}/transactions/{transactionCode}/uncommit",
            params=None,
            json=None,
        )

    def void_transaction(self, companyCode, transactionCode):
        return self.request(
            "POST",
            f"companies/{companyCode}/transactions/{transactionCode}/void",
            params=None,
            json={"code": "DocVoided"},
        )

    def ping(self):
        return self.request("GET", "utilities/ping", params=None, json=None)

    def resolve_address(self, model=None):
        return self.request("POST", "addresses/resolve", params=None, json=model)

    def list_entity_use_codes(self, include=None):
        return self.request(
            "GET", "definitions/entityusecodes", params=include, json=None
        )
