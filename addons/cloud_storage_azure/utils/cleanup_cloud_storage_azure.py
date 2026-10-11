import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import requests
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloud_storage" / "utils"))
from cloud_storage_cleanup import filter_unreferenced_blob_urls, remove_blob_urls

odoo_url = "http://localhost:8069"
odoo_db = "odoo_db"
odoo_username = "admin"
odoo_password = "admin"

X_MS_VERSION = "2023-11-03"
azure_container_name = "container_name"
azure_account_name = "account_name"
azure_tenant_id = "tenant_id"
azure_client_id = "client_id"
azure_client_secret = "client_secret"

_logger = logging.getLogger()


def get_blob_urls(
    container_name: str, token: str, batch_size: int = 1000
) -> Iterator[str]:
    cloud_storage_blobs_num = 0
    url = f"https://{azure_account_name}.blob.core.windows.net/{container_name}?restype=container&comp=list"
    headers = {
        "Authorization": f"Bearer {token}",
        "x-ms-version": X_MS_VERSION,
        "Content-Type": "application/xml",
    }
    params = {
        "maxresults": batch_size,
    }

    while True:
        response = requests.get(  # noqa: E8518 -- a standalone script run outside the server, with no ir.egress to reach
            url, headers=headers, params=params, timeout=5
        )
        response_xml = etree.fromstring(response.content)
        for blob in response_xml.findall(".//Blob"):
            cloud_storage_blobs_num += 1
            yield f"https://{azure_account_name}.blob.core.windows.net/{container_name}/{quote(blob.find('Name').text)}"

        params["marker"] = response_xml.find("NextMarker").text
        if params["marker"] is None:
            break

    _logger.info("The cloud storage container has %d blobs", cloud_storage_blobs_num)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token_response = requests.post(  # noqa: E8518 -- standalone operator script; no server-side ir.egress
        f"https://login.microsoftonline.com/{azure_tenant_id}/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": azure_client_id,
            "client_secret": azure_client_secret,
            "resource": "https://storage.azure.com/",
        },
        timeout=5,
    )
    token_response.raise_for_status()
    token = token_response.json()["access_token"]
    candidates = filter_unreferenced_blob_urls(
        get_blob_urls(azure_container_name, token),
        odoo_url=odoo_url,
        database=odoo_db,
        username=odoo_username,
        password=odoo_password,
    )
    remove_blob_urls(
        candidates,
        headers={
            "Authorization": f"Bearer {token}",
            "x-ms-version": X_MS_VERSION,
            "Content-Type": "application/xml",
        },
        success_status=202,
    )


if __name__ == "__main__":
    main()
