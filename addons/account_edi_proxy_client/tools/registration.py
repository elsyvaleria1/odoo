from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from odoo.api import Environment


class RegistrationNotificationParams(TypedDict):
    title: str
    type: Literal["success"]
    message: str
    next: dict[str, Any]


class RegistrationNotificationAction(TypedDict):
    type: Literal["ir.actions.client"]
    tag: Literal["display_notification"]
    params: RegistrationNotificationParams


def prepare_registration_success_action(
    env: Environment, title: str, message: str
) -> RegistrationNotificationAction:
    move_ids = env.context.get("active_ids")
    if move_ids and env.context.get("active_model") == "account.move":
        next_action = env["account.move"].browse(move_ids).action_send_and_print()
        next_action["views"] = [(False, "form")]
    else:
        next_action = {"type": "ir.actions.act_window_close"}

    return {
        "type": "ir.actions.client",
        "tag": "display_notification",
        "params": {
            "title": title,
            "type": "success",
            "message": message,
            "next": next_action,
        },
    }
