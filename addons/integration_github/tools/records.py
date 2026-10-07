from typing import Any

import psycopg


def create_once(model: Any, domain: list, vals: dict[str, Any]) -> Any:
    """Create the record, or find the one a concurrent delivery created first:
    the unique constraint lets one of two simultaneous first deliveries win."""
    try:
        with model.env.cr.savepoint():
            return model.create(vals)
    except psycopg.errors.UniqueViolation:
        model.env.invalidate_all()
        return model.search(domain, limit=1)
