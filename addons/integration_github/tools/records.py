from typing import Any

from odoo.db import get_or_create_row


def create_once(model: Any, domain: list, vals: dict[str, Any]) -> Any:
    record, _created = get_or_create_row(
        model.env.cr,
        lambda: model.create(vals),
        lambda: model.search(domain, limit=1),
        conflict=f"{model._name} {vals.get('repository')}",
    )
    return record
