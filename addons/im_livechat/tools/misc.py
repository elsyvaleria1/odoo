from typing import TYPE_CHECKING, Literal, TypedDict, cast

from werkzeug.exceptions import NotFound

from odoo.http import request

if TYPE_CHECKING:
    from odoo.api import Environment
    from odoo.models import BaseModel

    from odoo.addons.base.models.ir_actions_actions import IrActionsActions


def downgrade_to_public_user():
    public_user = request.env.ref("base.public_user")
    request.session.uid = None
    request.update_env(user=public_user)
    request.cookies = {}


def force_guest_env(guest_token, raise_if_not_found=True):
    downgrade_to_public_user()
    guest = request.env["mail.guest"]._get_guest_from_token(guest_token)
    if guest:
        request.update_context(guest=guest)
    elif raise_if_not_found:
        raise NotFound


class LivechatHistoryAction(TypedDict, total=False):
    res_id: int
    view_mode: str
    mobile_view_mode: str
    views: list[tuple[int | Literal[False], str]]
    context: dict[str, object] | str
    domain: list[tuple[str, str, list[int]]] | str


def prepare_livechat_history_action(
    env: Environment, discuss_channels: BaseModel
) -> LivechatHistoryAction:
    action = cast(
        "LivechatHistoryAction",
        cast(
            "IrActionsActions", env["ir.actions.act_window"]
        )._get_action_dict_by_xml_id("im_livechat.discuss_channel_action"),
    )
    if len(discuss_channels) == 1:
        action["res_id"] = cast("int", discuss_channels.id)
        action["view_mode"] = "form"
        action["views"] = [view for view in action["views"] if view[1] == "form"]
        return action
    action["context"] = {}
    action["domain"] = [("id", "in", discuss_channels.ids)]
    action["mobile_view_mode"] = "list"
    action["view_mode"] = "list"
    action["views"] = [view for view in action["views"] if view[1] in ("list", "form")]
    return action
