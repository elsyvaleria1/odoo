"""What the bot may change in Odoo, and how an authorized change is applied.

The agent never writes: it proposes operations, which are kept on the chat
until the person who asked says "autorizo" (or presses the button), and only
then run, in superuser mode but in that person's name, as a user would from
the screens: business models reachable from a menu, through the ORM, never
deleting and never touching the technical side (views, actions, modules,
settings, users, rights, credentials).
"""

import logging

from markupsafe import Markup, escape

_logger = logging.getLogger(__name__)

MAX_OPERATIONS = 20

# The technical side and the instance's own machinery stay out of reach,
# whatever menu reaches them.
BLOCKED_PREFIXES = (
    "ir.",
    "res.users",
    "res.groups",
    "res.company",
    "res.config",
    "res.lang",
    "res.currency",
    "base.",
    "base_",
    "bus.",
    "credential.",
    "integration.",
    "mcp.",
    "telegram.",
    "auth_",
    "auth.",
    "website.page",
    "theme.",
    "report.",
    "web_editor.",
    "html_editor.",
    "spreadsheet.",
)
BLOCKED_METHOD_WORDS = ("unlink", "delete", "remove", "uninstall", "install", "upgrade")
ALLOWED_METHOD_PREFIXES = ("action_", "button_")


class OperationError(Exception):
    """An operation the bot refuses: the message says why."""


def is_writable_model(env, model_name) -> bool:
    """Whether the bot may create or change records of `model_name`: a stored
    business model a window action opens, outside the technical side."""
    if not model_name or model_name.startswith(BLOCKED_PREFIXES):
        return False
    model = env.get(model_name)
    if model is None or model._abstract or model._transient or not model._auto:
        return False
    return bool(
        env["ir.actions.act_window"].search_count(
            [("res_model", "=", model_name)], limit=1
        )
    )


def check(env, operation) -> dict:
    """Validate one proposed operation and return it normalized.

    :param env: an environment to read the models in
    :param dict operation: ``{"op": "create"|"write"|"action", "model": ...,
        "values": {...}, "ids": [...], "method": ...}``
    :return: the operation, with only the keys it uses
    :rtype: dict
    """
    op = operation.get("op")
    model_name = (operation.get("model") or "").strip()
    if op not in ("create", "write", "action"):
        raise OperationError(f"Unknown operation {op!r}: create, write or action.")
    if not is_writable_model(env, model_name):
        raise OperationError(
            f"{model_name!r} cannot be changed through the bot: only business "
            "records reachable from a menu, never the technical side."
        )
    model = env[model_name]
    normalized = {"op": op, "model": model_name}
    if op in ("write", "action"):
        ids = operation.get("ids") or []
        if not isinstance(ids, list) or not ids:
            raise OperationError(
                "`ids` must list the records, or ref:N for one created before."
            )
        for ident in ids:
            if not (
                isinstance(ident, int)
                or (isinstance(ident, str) and ident.startswith("ref:"))
            ):
                raise OperationError(f"Bad id {ident!r}: an integer, or ref:N.")
        normalized["ids"] = ids
    if op in ("create", "write"):
        values = operation.get("values")
        if not isinstance(values, dict) or not values:
            raise OperationError("`values` must map field names to values.")
        unknown = [name for name in values if name not in model._fields]
        if unknown:
            raise OperationError(
                f"{model_name} has no field {', '.join(unknown)}; call describe_model."
            )
        normalized["values"] = values
    if op == "action":
        method = (operation.get("method") or "").strip()
        if not method.startswith(ALLOWED_METHOD_PREFIXES) or any(
            word in method for word in BLOCKED_METHOD_WORDS
        ):
            raise OperationError(
                f"{method!r} is not allowed: only a screen's action_* or button_* "
                "buttons, never deleting."
            )
        if not callable(getattr(model, method, None)):
            raise OperationError(f"{model_name} has no button {method!r}.")
        normalized["method"] = method
    if operation.get("attach_files"):
        normalized["attach_files"] = True
    return normalized


def describe(env, operations) -> list:
    """One line per operation, for the person to authorize."""
    lines = []
    for number, operation in enumerate(operations, 1):
        label = env["ir.model"]._get(operation["model"]).name or operation["model"]
        if operation["op"] == "create":
            lines.append(
                f"{number}. Crear {label}: {_values_text(operation['values'])}"
            )
        elif operation["op"] == "write":
            lines.append(
                f"{number}. Modificar {label} {operation['ids']}: "
                f"{_values_text(operation['values'])}"
            )
        else:
            lines.append(
                f"{number}. {label} {operation['ids']}: botón {operation['method']}"
            )
        if operation.get("attach_files"):
            lines.append("   + adjuntar los archivos que mandaste")
    return lines


def _values_text(values) -> str:
    text = ", ".join(f"{name}={value!r}" for name, value in values.items())
    return text if len(text) <= 400 else text[:399] + "…"


def apply(env, operations, files, requester):
    """Run authorized operations, all or none, and say what they did.

    :param env: a read-write environment in superuser mode, as `requester`
    :param list operations: operations validated by `check`
    :param list files: ``[(name, bytes, mimetype)]`` to attach where asked
    :param requester: the user who asked and authorized
    :return: the records touched, one per operation
    :rtype: list
    """
    created = []
    touched = []
    with env.cr.savepoint():
        for operation in operations:
            operation = check(env, operation)
            model = env[operation["model"]]
            if operation["op"] == "create":
                records = model.create(operation["values"])
                created.append(records)
            else:
                records = model.browse(_resolve(operation["ids"], created)).exists()
                if not records:
                    raise OperationError(
                        f"No {operation['model']} record {operation['ids']} found."
                    )
                if operation["op"] == "write":
                    records.write(operation["values"])
                else:
                    getattr(records, operation["method"])()
            if operation.get("attach_files"):
                for name, content, mimetype in files:
                    env["ir.attachment"].create(
                        {
                            "name": name,
                            "raw": content,
                            "mimetype": mimetype or None,
                            "res_model": records._name,
                            "res_id": records[:1].id,
                        }
                    )
            _note(records, requester)
            touched.append(records)
        env.flush_all()
    return touched


def _resolve(ids, created) -> list:
    resolved = []
    for ident in ids:
        if isinstance(ident, str) and ident.startswith("ref:"):
            index = int(ident[4:]) - 1
            if not 0 <= index < len(created):
                raise OperationError(f"{ident} names no record created before it.")
            resolved += created[index].ids
        else:
            resolved.append(ident)
    return resolved


def _note(records, requester) -> None:
    """Say on each record's history who asked for the change through the bot."""
    if not hasattr(records, "message_post"):
        return
    body = Markup("<p>%s</p>") % escape(
        f"Hecho desde el bot de Telegram a petición de {requester.name}, "
        "autorizado por la persona."
    )
    for record in records:
        try:
            record.message_post(
                body=body, message_type="comment", subtype_xmlid="mail.mt_note"
            )
        except Exception:
            _logger.info("insight_telegram could not note %s", record, exc_info=True)
