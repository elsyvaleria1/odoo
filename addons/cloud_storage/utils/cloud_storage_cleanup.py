"""Shared helpers for standalone cloud cleanup scripts; no Odoo server import."""

import logging
import xmlrpc.client
from collections.abc import Iterable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from itertools import batched

import requests

_logger = logging.getLogger(__name__)


def filter_unreferenced_blob_urls(
    blob_urls: Iterable[str],
    *,
    odoo_url: str,
    database: str,
    username: str,
    password: str,
    batch_size: int = 1000,
) -> Iterator[str]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least one")
    with xmlrpc.client.ServerProxy(
        f"{odoo_url}/xmlrpc/2/common"
    ) as common:
        uid = common.authenticate(database, username, password, {})
    if not uid:
        raise ValueError("Odoo authentication failed; no blobs were selected")
    with xmlrpc.client.ServerProxy(
        f"{odoo_url}/xmlrpc/2/object"
    ) as models:
        for batch in batched(blob_urls, batch_size, strict=False):
            attachments = models.execute_kw(
                database,
                uid,
                password,
                "ir.attachment",
                "search_read",
                [[("type", "=", "cloud_storage"), ("url", "in", list(batch))], ["url"]],
            )
            if not isinstance(attachments, list):
                raise ValueError("The attachment lookup did not return a list")
            referenced_urls: set[str] = set()
            for attachment in attachments:
                if not isinstance(attachment, dict) or not isinstance(
                    attachment.get("url"), str
                ):
                    raise ValueError(
                        "The attachment lookup returned an invalid URL row"
                    )
                referenced_urls.add(attachment["url"])
            for blob_url in batch:
                if blob_url not in referenced_urls:
                    yield blob_url


def remove_blob_urls(
    blob_urls: Iterable[str],
    *,
    headers: Mapping[str, str],
    success_status: int,
    max_workers: int | None = None,
) -> int:

    def remove_blob(blob_url: str) -> bool:
        response = requests.delete(
            blob_url, headers=headers, timeout=5
        )
        if response.status_code == success_status:
            _logger.info("%s is deleted", blob_url)
            return True
        if response.status_code == 404:
            _logger.debug("%s has already been deleted", blob_url)
        else:
            _logger.warning("%s cannot be deleted:\n%s", blob_url, response.text)
        return False

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        deleted_count = sum(executor.map(remove_blob, blob_urls))
    _logger.info("%d blobs are deleted by the script", deleted_count)
    return deleted_count
