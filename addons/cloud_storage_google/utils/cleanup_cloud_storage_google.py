import json
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloud_storage" / "utils"))
from cloud_storage_cleanup import filter_unreferenced_blob_urls, remove_blob_urls

odoo_url = "http://localhost:8069"
odoo_db = "odoo_db"
odoo_username = "admin"
odoo_password = "admin"

GOOGLE_CLOUD_STORAGE_ENDPOINT = "https://storage.googleapis.com"
google_cloud_bucket_name = "bucket_name"
google_cloud_account_info = r"""account_info"""

_logger = logging.getLogger(__name__)


def get_blob_urls(
    bucket_name: str, token: str, batch_size: int = 1000
) -> Iterator[str]:
    cloud_storage_blobs_num = 0
    url = f"https://www.googleapis.com/storage/v1/b/{bucket_name}/o"
    params = {
        "maxResults": batch_size,
        "fields": "items(name), nextPageToken",
    }
    headers = {"Authorization": f"Bearer {token}"}

    while True:
        response = requests.get(  # noqa: E8518 -- a standalone script run outside the server, with no ir.egress to reach
            url, params=params, headers=headers, timeout=5
        )
        data = response.json()
        for blob in data.get("items", []):
            cloud_storage_blobs_num += 1
            yield f"{GOOGLE_CLOUD_STORAGE_ENDPOINT}/{bucket_name}/{quote(blob['name'])}"

        params["pageToken"] = data.get("nextPageToken")
        if params["pageToken"] is None:
            break

    _logger.info("The cloud storage container has %d blobs.", cloud_storage_blobs_num)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(google_cloud_account_info)
    ).with_scopes(["https://www.googleapis.com/auth/devstorage.full_control"])
    credentials.refresh(Request())
    candidates = filter_unreferenced_blob_urls(
        get_blob_urls(google_cloud_bucket_name, credentials.token),
        odoo_url=odoo_url,
        database=odoo_db,
        username=odoo_username,
        password=odoo_password,
    )
    remove_blob_urls(
        candidates,
        headers={"Authorization": f"Bearer {credentials.token}"},
        success_status=204,
    )


if __name__ == "__main__":
    main()
