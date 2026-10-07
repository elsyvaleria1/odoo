__all__ = [
    "get_accessible_ids",
    "get_inaccessible_owners",
    "prepare_document_access_error",
    "stable_order",
]

import typing
from collections.abc import Callable, Collection, Generator, Iterable, Sequence
from typing import Any

from odoo.exceptions import AccessError, MissingError
from odoo.libs.collections import OrderedSet
from odoo.libs.debug_log import DebugLog
from odoo.orm.domain import Domain
from odoo.orm.parsing import parse_order
from odoo.tools.query import Query

if typing.TYPE_CHECKING:
    from odoo import api, models
    from odoo.api import DomainType

_debug = DebugLog(__name__)


def prepare_document_access_error(
    records: models.BaseModel, operation: str
) -> AccessError:
    return AccessError(
        records.env._(
            "The requested operation cannot be completed due to security "
            "restrictions. Please contact your system administrator.\n\n"
            "(Document type: %(type)s, Operation: %(operation)s)\n\n"
            "Records: %(records)s, User: %(user)s",
            type=records._description,
            operation=operation,
            records=records.ids[:6],
            user=records.env.uid,
        )
    )


def stable_order(order: str | None, tiebreak: str = "id ASC") -> str | None:
    if not order:
        return order
    terms = parse_order(order)
    # an order that does not parse is the ORM's to refuse, not this helper's
    if terms is None or any(term.field == "id" for term in terms):
        return order
    return f"{order}, {tiebreak}"


def _seek_operator(order: str | None) -> str | None:
    terms = parse_order(order) if order else None
    if not terms or terms[0].field != "id" or terms[0].property or terms[0].func:
        return None
    return "<" if terms[0].desc else ">"


def get_accessible_ids(
    model: models.BaseModel,
    domain: DomainType,
    offset: int,
    limit: int | None,
    order: str | None,
    base_search: Callable[..., Query],
    *,
    fetch: Callable[[Query], Sequence[Sequence[Any]]],
    allowed: Callable[[Sequence[Sequence[Any]]], Iterable[int]],
    chunk_min: int,
    chunk_max: int,
    tiebreak: str = "id ASC",
    keyset: bool = False,
    **kwargs,
) -> list[int]:
    scan_order = stable_order(order or model._order, tiebreak)
    # paging past the last id seen costs one index seek per pass, so an
    # unbounded scan can afford to page; an OFFSET would rescan every page
    seek = _seek_operator(scan_order) if keyset else None

    if limit is None or limit is False:
        target = None
    elif limit is True:
        target = offset + 1
    elif limit == 0:
        return []
    else:
        target = offset + limit
    if target is None:
        chunk = chunk_max if seek else None
    else:
        chunk = min(max(target, chunk_min), chunk_max)

    ordered: list[int] = []
    seen: set[int] = set()
    sql_offset = 0
    scan_domain = domain
    passes = 0  # debuglog
    scanned = 0  # debuglog
    while True:
        query = base_search(
            scan_domain, offset=sql_offset, limit=chunk, order=scan_order, **kwargs
        )
        rows = fetch(query)
        chunk_allowed = set(allowed(rows))
        for row in rows:
            id_ = row[0]
            if id_ in chunk_allowed and id_ not in seen:
                seen.add(id_)
                ordered.append(id_)

        got = len(rows)
        scanned += got  # debuglog
        passes += 1  # debuglog
        if chunk is None or got < chunk:
            break
        if target is not None and len(ordered) >= target:
            break
        if seek:
            scan_domain = Domain(domain) & Domain("id", seek, rows[-1][0])
        else:
            sql_offset += got
        chunk = min(chunk * 2, chunk_max)

    _debug.perf.count(
        "access_scan",
        model=model._name,
        target=target,
        passes=passes,
        scanned=scanned,
        allowed=len(ordered),
        last_chunk=chunk,
        seek=bool(seek),
    )
    return ordered[offset:target]


def get_inaccessible_owners(
    env: api.Environment,
    model_and_ids: dict[Any, Collection[int]],
    operation: str,
) -> Generator[tuple[str, int]]:
    if env.su:
        return
    for res_model, res_ids in model_and_ids.items():
        res_ids = OrderedSet(filter(None, res_ids))
        if not res_model or not res_ids:
            continue
        if res_model not in env:
            _debug.logic(
                "comodel_unknown",
                model=res_model,
                operation=operation,
                count=len(res_ids),
            )
            for res_id in res_ids:
                yield res_model, res_id
            continue
        if res_model == "res.users" and env.uid in res_ids:
            res_ids = OrderedSet(rid for rid in res_ids if rid != env.uid)
            if not res_ids:
                continue
        records = env[res_model].browse(res_ids)
        try:
            records = records._filtered_access(operation)
        except MissingError:
            _debug.logic("comodel_records_missing", model=res_model)
            records = records.exists()._filtered_access(operation)
        res_ids.difference_update(records._ids)
        _debug.perf.count(
            "comodel_access_checked",
            model=res_model,
            operation=operation,
            inaccessible=len(res_ids),
        )
        for res_id in res_ids:
            yield res_model, res_id
