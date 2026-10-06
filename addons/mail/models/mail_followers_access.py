import typing

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog
from odoo.tools.access_scan import (
    get_accessible_query,
    prepare_column_fetcher,
)

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    from odoo.api import DomainType
    from odoo.tools import Query

_debug = DebugLog(__name__)


class MailFollowers(models.Model):
    _inherit = "mail.followers"
    _search_visibility_fields = (
        "res_model",
        "res_id",
        "partner_id",
    )

    _SEARCH_ACCESS_CHUNK_MIN = 30
    _SEARCH_ACCESS_CHUNK_MAX = 8192

    @api.model
    def _search(
        self,
        domain: DomainType,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
        *,
        bypass_access: bool = False,
        **kwargs,
    ) -> Query:
        if self.env.is_superuser() or bypass_access:
            return super()._search(
                domain, offset, limit, order, bypass_access=True, **kwargs
            )
        if not self.env.user._is_internal():
            _debug.logic("search_refused", uid=self.env.uid, reason="not_internal")
            return self.browse()._as_query()

        self.flush_model(["res_model", "res_id", "partner_id"])
        return get_accessible_query(
            self,
            domain,
            offset,
            limit,
            order,
            super()._search,
            fetch=prepare_column_fetcher(
                self, ("id", "res_model", "res_id", "partner_id")
            ),
            allowed=self._get_readable_follower_ids,
            chunk_min=self._SEARCH_ACCESS_CHUNK_MIN,
            chunk_max=self._SEARCH_ACCESS_CHUNK_MAX,
            **kwargs,
        )

    def _check_access(self, operation: str) -> tuple | None:
        result = super()._check_access(operation)
        if not self or operation != "read" or self.env.is_superuser():
            return result

        followers = self - result[0] if result else self
        forbidden = followers - followers._filtered_readable_by_document()
        if not forbidden:
            return result

        def error() -> AccessError:
            models = sorted(set(forbidden.sudo().mapped("res_model")))
            return AccessError(
                self.env._(
                    "You are not allowed to read the followers of a document you "
                    "cannot read (%(models)s).",
                    models=", ".join(models),
                )
            )

        if result:
            return (result[0] + forbidden, result[1])
        return (forbidden, error)

    def _filtered_readable_by_document(self) -> api.Self:
        allowed = self._get_readable_follower_ids(
            (follower.id, follower.res_model, follower.res_id, follower.partner_id.id)
            for follower in self.sudo()
        )
        return self.browse([fol_id for fol_id in self._ids if fol_id in allowed])

    def _get_readable_follower_ids(self, rows: Iterable[tuple]) -> set[int]:
        pid = self.env.user.partner_id.id
        own = set()
        model_ids: dict[str, dict[int, set[int]]] = {}
        for id_, res_model, res_id, partner_id in rows:
            if partner_id == pid:
                own.add(id_)
            elif res_model and res_id:
                model_ids.setdefault(res_model, {}).setdefault(res_id, set()).add(id_)
        allowed = own | self.env["mail.message"]._get_ids_on_readable_documents(
            model_ids
        )
        _debug.logic(
            "readable_by_document",
            own=len(own),
            models=len(model_ids),
            allowed=len(allowed),
        )
        return allowed
