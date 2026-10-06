from typing import Any

from werkzeug.exceptions import BadRequest

from odoo import models
from odoo.fields import Domain
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

from odoo.addons.mail.controllers.utils import needaction_thread_fields, to_record_ids
from odoo.addons.mail.controllers.webclient import WebclientController
from odoo.addons.mail.tools.discuss import Store

_debug = DebugLog(__name__)


class MessagingMenuController(WebclientController):
    @classmethod
    def _get_menu_tab_domain(cls, tab_id: str) -> Domain:
        partner_id = request.env.user.partner_id.id
        match tab_id:
            case "bookmark":
                return Domain("starred_partner_ids", "in", [partner_id])
            case "notification":
                return Domain("notification_ids.res_partner_id", "=", partner_id)
            case _:
                return Domain.FALSE

    @classmethod
    def _get_menu_tab_filter_domain(cls, tab_id: str, filter_id: str) -> Domain:
        if tab_id == "notification" and filter_id == "notification_unread":
            return Domain("needaction", "=", True)
        return Domain.FALSE

    @classmethod
    def _get_menu_tab_full_domain(
        cls, model_name: str, tab_id: Any, filter_ids: Any = ()
    ) -> Domain:
        if not isinstance(tab_id, str):
            raise BadRequest(f"Invalid messaging menu tab {tab_id!r}")
        domain = cls._get_menu_tab_domain(tab_id)
        if domain.is_false():
            raise BadRequest(f"Unknown messaging menu tab {tab_id}")
        if isinstance(filter_ids, str) or not isinstance(filter_ids, (list, tuple)):
            raise BadRequest(f"Invalid messaging menu filters {filter_ids!r}")
        for filter_id in filter_ids:
            filter_domain = (
                cls._get_menu_tab_filter_domain(tab_id, filter_id)
                if isinstance(filter_id, str)
                else Domain.FALSE
            )
            if filter_domain.is_false():
                raise BadRequest(
                    f"Unknown messaging menu filter {filter_id} for tab {tab_id}"
                )
            domain &= filter_domain
        try:
            domain.optimize(request.env[model_name])
        except ValueError:
            raise BadRequest(
                f"Messaging menu tab {tab_id} does not list {model_name}"
            ) from None
        return domain

    @classmethod
    def _get_menu_counter_domain_by_tab_id(
        cls, model_name: str, filter_id_by_tab_id: Any
    ) -> dict[str, Domain]:
        if not isinstance(filter_id_by_tab_id, dict):
            raise BadRequest("Invalid messaging menu counters request")
        return {
            tab_id: cls._get_menu_tab_full_domain(
                model_name, tab_id, [filter_id] if filter_id else ()
            )
            for tab_id, filter_id in filter_id_by_tab_id.items()
        }

    @classmethod
    def _get_menu_load_more_domain(cls, model_name: str, params: dict) -> Domain:
        domain = cls._get_menu_tab_full_domain(
            model_name, params.get("tab_id"), params.get("filter_ids") or ()
        )
        if exclude_ids := to_record_ids(params.get("exclude_ids")):
            domain &= Domain("id", "not in", exclude_ids)
        return domain

    @staticmethod
    def _add_menu_tab_counters(
        store: Store,
        candidates: models.BaseModel,
        domain_by_tab_id: dict[str, Domain],
    ) -> None:
        for tab_id, domain in domain_by_tab_id.items():
            counter_ids = candidates.filtered_domain(domain).ids
            _debug.logic(
                "messaging_menu_counter",
                model=candidates._name,
                tab=tab_id,
                count=len(counter_ids),
            )
            store.add_model_values(
                "MessagingMenuTab", {"id": tab_id, "init_counter_ids": counter_ids}
            )

    @classmethod
    def _add_menu_tab_presence(
        cls, store: Store, model_name: str, params: dict, tab_ids: Any
    ) -> None:
        presence_tab_ids = params.get("presence_tab_ids") or []
        if not isinstance(presence_tab_ids, list) or not all(
            isinstance(tab_id, str) for tab_id in presence_tab_ids
        ):
            raise BadRequest("Invalid messaging menu counters request")
        presence_tab_ids = sorted(set(presence_tab_ids).intersection(tab_ids))
        if not presence_tab_ids:
            return
        model = request.env[model_name]
        request.env.cr.execute(
            SQL(
                "SELECT %s",
                SQL(", ").join(
                    SQL(
                        "EXISTS(%s)",
                        model._search(
                            cls._get_menu_tab_full_domain(model_name, tab_id)
                        ).select(),
                    )
                    for tab_id in presence_tab_ids
                ),
            )
        )
        for tab_id, has_records in zip(
            presence_tab_ids, request.env.cr.fetchone(), strict=True
        ):
            store.add_model_values(
                "MessagingMenuTab", {"id": tab_id, "has_records": has_records}
            )

    @staticmethod
    def _get_filter_id_by_tab_id(params: Any, record_type: str) -> Any:
        if not isinstance(params, dict):
            raise BadRequest("Invalid messaging menu counters request")
        by_record_type = params.get("filter_id_by_tab_id_by_record_type")
        if not isinstance(by_record_type, dict):
            raise BadRequest("Invalid messaging menu counters request")
        return by_record_type.get(record_type)

    @classmethod
    def _process_request_for_logged_in_user(
        cls, store: Store, name: str, params: Any
    ) -> None:
        super()._process_request_for_logged_in_user(store, name, params)
        if name == "/mail/messaging_menu/mail.message/load_more":
            cls._messaging_menu_message_load_more(store, params)

    @classmethod
    def _messaging_menu_message_load_more(cls, store: Store, params: Any) -> None:
        if not isinstance(params, dict):
            raise BadRequest("Invalid messaging menu load more request")
        message_model = request.env["mail.message"]
        limit = message_model._clamp_fetch_limit(params.get("limit"))
        messages = message_model._message_fetch(
            domain=cls._get_menu_load_more_domain("mail.message", params),
            search_term=params.get("search_term"),
            limit=limit,
        )["messages"]
        _debug.logic(
            "messaging_menu_load_more",
            model="mail.message",
            tab=params.get("tab_id"),
            fetched=len(messages),
            limit=limit,
        )
        store.add(
            messages,
            extra_fields=needaction_thread_fields(),
            add_followers=True,
        )
        store.resolve_data_request(is_fully_loaded=len(messages) < limit)
