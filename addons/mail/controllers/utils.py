import typing
from typing import Any

from odoo import http, models
from odoo.http import NotFound, request
from odoo.libs.debug_log import DebugLog
from odoo.tools import file_open

from odoo.addons.mail.tools.discuss import (
    Store,
    StoreFieldSpec,
    to_record_id,
)
from odoo.addons.mail.tools.discuss import (
    to_record_ids as to_record_ids,  # noqa: PLC0414 -- Explicit public re-export for callers of this module.
)
from odoo.addons.mail.tools.paging import (
    clamp_limit as clamp_limit,  # noqa: PLC0414 -- Explicit public re-export for callers of this module.
)

if typing.TYPE_CHECKING:
    from odoo.addons.mail.models.discuss.discuss_channel import DiscussChannel
    from odoo.addons.mail.models.discuss.discuss_channel_member import (
        DiscussChannelMember,
    )

_debug = DebugLog(__name__)


def get_channel_or_404(channel_id: Any) -> DiscussChannel:
    channel = request.env["discuss.channel"].search(
        [("id", "=", to_record_id(channel_id))]
    )
    if not channel:
        raise NotFound
    return channel


def get_self_member(channel_id: Any) -> DiscussChannelMember:
    return request.env["discuss.channel.member"].search(
        [("channel_id", "=", to_record_id(channel_id)), ("is_self", "=", True)]
    )


def get_self_member_or_404(channel_id: Any) -> DiscussChannelMember:
    member = get_self_member(channel_id)
    if not member:
        raise NotFound
    return member


def message_fetch_response(
    *,
    thread: models.Model,
    fetch_params: dict[str, Any] | None = None,
    mark_done: bool = False,
) -> dict[str, Any]:
    res = request.env["mail.message"]._message_fetch(
        None,
        thread=thread,
        **request.env["mail.message"]._filter_fetch_params(fetch_params),
    )
    messages = res.pop("messages")
    if mark_done and not request.env.user._is_public():
        messages.set_message_done()
    _debug.pipeline(
        "fetch_response",
        model=thread._name,
        record=thread.id,
        messages=len(messages),
        mark_done=mark_done and not request.env.user._is_public(),
    )
    return {
        **res,
        "data": Store().add(messages).get_result(),
        "messages": messages.ids,
    }


def javascript_file_response(path: str) -> http.Response:
    with file_open(path, "rb") as file:
        data = file.read()
    return request.prepare_response(
        data,
        headers=[
            ("Content-Type", "application/javascript"),
            ("X-Content-Type-Options", "nosniff"),
            ("Cache-Control", f"max-age={http.STATIC_CACHE}"),
        ],
    )


def needaction_thread_fields() -> list[StoreFieldSpec]:
    bus_last_id = request.env["bus.bus"].sudo()._bus_last_id()
    return [
        Store.One(
            "thread",
            [
                Store.Attr("message_needaction_counter", sudo=True),
                Store.Attr("message_needaction_counter_bus_id", bus_last_id),
            ],
            as_thread=True,
        )
    ]
