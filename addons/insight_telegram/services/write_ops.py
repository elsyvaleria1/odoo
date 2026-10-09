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
        for name, value in values.items():
            if model._fields[name].type in ("one2many", "many2many"):
                _check_lines(model, normalized.get("ids"), name, value)
        company = model._fields.get("company_id")
        if (
            op == "create"
            and company
            and company.type == "many2one"
            and company.required
            and not values.get("company_id")
        ):
            # with every company allowed, the default one is arbitrary: the
            # company is always the person's choice, said explicitly
            raise OperationError(
                f"{model_name} needs company_id: ask the person which company "
                "if they have not said it."
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


REMOVE_COMMANDS = (2, 3)
ROW_COMMANDS = (1, 2, 3)


def _check_lines(model, ids, name, commands) -> None:
    """Refuse x2many commands that delete beyond what a user may on screen:
    a draft document's own lines may be removed one by one, nothing else."""
    if not isinstance(commands, list):
        return
    for command in commands:
        if not isinstance(command, (list, tuple)) or not command:
            continue
        code = command[0]
        if code == 5 or (code in REMOVE_COMMANDS and not ids):
            raise OperationError(
                f"{name}: lines are removed one by one, and only from a draft "
                "document that already exists."
            )
        if code not in ROW_COMMANDS:
            continue
        if not ids or any(not isinstance(ident, int) for ident in ids):
            raise OperationError(
                f"{name}: a line is changed or removed on an existing record, by id."
            )
        records = model.browse(ids).exists()
        if command[1] not in records[name].ids:
            raise OperationError(
                f"{name}: line {command[1]!r} does not belong to {model._name} {ids}."
            )
        if code in REMOVE_COMMANDS and (
            "state" not in model._fields
            or any(record.state != "draft" for record in records)
        ):
            raise OperationError(
                f"{name}: lines are removed only while the document is in draft; "
                "removing them is deleting, which the bot never does otherwise."
            )


def describe(env, operations) -> list:
    """The proposed operations as the person reads them: each field by its
    label and each value as the screen shows it, never raw ids."""
    lines = []
    for number, operation in enumerate(operations, 1):
        model = env[operation["model"]]
        label = env["ir.model"]._get(operation["model"]).name or operation["model"]
        if operation["op"] == "create":
            lines.append(f"**{number}. Crear {label}**")
            lines += _values_lines(model, operation["values"])
        else:
            names = _records_text(model, operation["ids"])
            if operation["op"] == "write":
                lines.append(f"**{number}. Modificar {label} {names}**")
                lines += _values_lines(model, operation["values"])
            else:
                lines.append(
                    f"**{number}. {label} {names}:** botón {_button_text(model, operation['method'])}"
                )
        if operation.get("attach_files"):
            lines.append("📎 Adjuntar los archivos que mandaste")
        lines.append("")
    return lines[:-1] if lines else lines


def _records_text(model, ids) -> str:
    names = []
    for ident in ids:
        if isinstance(ident, str):
            names.append(f"(la #{ident[4:]} de arriba)")
            continue
        record = model.browse(ident).exists()
        names.append(record.display_name if record else f"#{ident}")
    return ", ".join(names)


def _button_text(model, method) -> str:
    words = method.removeprefix("action_").removeprefix("button_").replace("_", " ")
    return f"«{words}»"


def _currency(model, values):
    env = model.env
    currency = values.get("currency_id")
    if isinstance(currency, int):
        found = env["res.currency"].browse(currency).exists()
        if found:
            return found
    company = values.get("company_id")
    if isinstance(company, int):
        found = env["res.company"].browse(company).exists()
        if found:
            return found.currency_id
    return env.company.currency_id


def _money(amount, currency) -> str:
    text = f"{amount:,.2f}"
    symbol = currency.symbol or ""
    if currency.position == "after":
        return f"{text} {symbol} {currency.name}".strip()
    return f"{symbol}{text} {currency.name}".strip()


def _number(value) -> str:
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}" if isinstance(value, (int, float)) else str(value)


QUANTITY_FIELDS = ("product_qty", "product_uom_qty", "quantity")


def _values_lines(model, values) -> list:
    currency = _currency(model, values)
    lines = []
    for name, value in values.items():
        field = model._fields[name]
        if field.type in ("one2many", "many2many") and isinstance(value, list):
            lines += _relation_lines(
                model.env[field.comodel_name], field, value, currency
            )
        else:
            lines.append(
                f"• {_label(model, field)}: {_value_text(model, field, value, currency)}"
            )
    return lines


def _label(model, field) -> str:
    """A field's label in the language of `model`'s environment."""
    return field._description_string(model.env) or field.name


def _value_text(model, field, value, currency) -> str:
    env = model.env
    if value is False or value is None or value == "":
        return "—"
    if field.type == "many2one" and isinstance(value, int):
        record = env[field.comodel_name].browse(value).exists()
        return record.display_name if record else f"#{value}"
    if field.type == "boolean":
        return "Sí" if value else "No"
    if field.type == "selection":
        selection = field._description_selection(env)
        return dict(selection).get(value, str(value))
    if field.type == "monetary" and isinstance(value, (int, float)):
        return _money(value, currency)
    if field.type in ("float", "integer") and isinstance(value, (int, float)):
        return _number(value)
    if field.type == "html":
        text = str(value)
        return text if len(text) <= 200 else text[:199] + "…"
    return str(value)


def _relation_lines(comodel, field, commands, currency) -> list:
    """An x2many's commands: new lines one per row, with a total where the
    rows carry a quantity and a unit price."""
    lines = [f"• {_label(comodel, field)}:"]
    total = 0.0
    priced = False
    for command in commands:
        if not isinstance(command, (list, tuple)) or not command:
            continue
        code = command[0]
        if code == 0 and len(command) > 2 and isinstance(command[2], dict):
            text, amount = _row_text(comodel, command[2], currency)
            lines.append(f"   ◦ {text}")
            if amount is not None:
                total += amount
                priced = True
        elif code == 1 and len(command) > 2 and isinstance(command[2], dict):
            text, _amount = _row_text(comodel, command[2], currency)
            name = _records_text(comodel, [command[1]])
            lines.append(f"   ◦ Cambiar {name}: {text}")
        elif code in (4, 6):
            ids = [command[1]] if code == 4 else list(command[2] or [])
            lines.append(f"   ◦ {_records_text(comodel, ids)}")
        elif code in REMOVE_COMMANDS:
            lines.append(f"   ◦ Quitar: {_records_text(comodel, [command[1]])}")
    if priced and len(lines) > 2:
        lines.append(f"   **Total: {_money(total, currency)}** (antes de impuestos)")
    return lines


def _row_text(comodel, values, currency):
    """One row of a line: product, quantity × price = subtotal when it has
    them, else its fields by label."""
    product = values.get("product_id")
    quantity = next((values[name] for name in QUANTITY_FIELDS if name in values), None)
    price = values.get("price_unit")
    if product and quantity is not None and "product_id" in comodel._fields:
        name = _value_text(comodel, comodel._fields["product_id"], product, currency)
        if isinstance(price, (int, float)) and isinstance(quantity, (int, float)):
            subtotal = quantity * price
            text = (
                f"{name} — {_number(quantity)} × {_money(price, currency)}"
                f" = {_money(subtotal, currency)}"
            )
            return text, subtotal
        return f"{name} — {_number(quantity)}", None
    parts = [
        f"{_label(comodel, comodel._fields[name])}: "
        f"{_value_text(comodel, comodel._fields[name], value, currency)}"
        for name, value in values.items()
        if name in comodel._fields
    ]
    return ", ".join(parts) or "—", None


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
