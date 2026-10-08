from typing import Any

from odoo.db import get_or_create_row


def create_once(model: Any, domain: list, vals: dict[str, Any]) -> Any:
    """Create the record, or find the one a concurrent delivery created first.

    When that delivery committed after this transaction's snapshot, the row is
    invisible here: the helper raises a concurrency error, and the request is
    retried on a fresh snapshot -- never a delivery written to nothing."""
    record, _created = get_or_create_row(
        model.env.cr,
        lambda: model.create(vals),
        lambda: model.search(domain, limit=1),
        conflict=f"{model._name} {vals.get('repository')}",
    )
    return record
