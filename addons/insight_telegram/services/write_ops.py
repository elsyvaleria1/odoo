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

from .catalog import money
from .catalog import quantity as format_quantity

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
    # outgoing mail and the instance's mail machinery: a menu reaches them,
    # but writing them sends data out or rewires the server
    "mail.mail",
    "mail.template",
    "mail.alias",
    "mail.gateway",
    "fetchmail.",
)
# a button whose name says it deletes, archives, undoes or makes users is
# refused even when a screen shows it
BLOCKED_METHOD_WORDS = (
    "unlink",
    "delete",
    "remove",
    "uninstall",
    "install",
    "upgrade",
    "archive",
    "undo",
    "create_user",
    "reset_password",
)
ALLOWED_METHOD_PREFIXES = ("action_", "button_")
# the fields only an administrator sees (passwords, keys) stay out of reach,
# superuser mode or not
ADMIN_GROUP = "base.group_system"
# what an x2many command may do: a one2many creates, changes and -- on a
# draft document -- removes its own lines; a many2many also links and
# unlinks existing records, which deletes nothing. Replacing a one2many's
# lines (6) deletes the ones left out, and linking (4) takes lines from
# another document, so neither is allowed there.
ONE2MANY_COMMANDS = (0, 1, 2, 3)
# fields that tie a business record to a user account: changing them moves
# who logs in as whom, which belongs to the user's own settings
USER_LINK_FIELDS = {"res.partner": ("main_user_id", "user_ids")}
MANY2MANY_COMMANDS = (0, 1, 3, 4, 6)


class OperationError(Exception):
    """An operation the bot refuses: the message says why."""


def is_business_model(model_name) -> bool:
    """Whether `model_name` is outside the technical side the bot never
    writes, whatever reaches it."""
    return bool(model_name) and not model_name.startswith(BLOCKED_PREFIXES)


def is_writable_model(env, model_name) -> bool:
    """Whether the bot may create or change records of `model_name`: a stored
    business model a window action opens, outside the technical side."""
    if not is_business_model(model_name):
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
        _check_values(model, values, normalized.get("ids"))
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
        if not _is_screen_button(env, model_name, method):
            raise OperationError(
                f"{method!r} is no button of a {model_name} screen: only what a "
                "user can press."
            )
        normalized["method"] = method
    if operation.get("attach_files"):
        normalized["attach_files"] = True
    return normalized


def _is_screen_button(env, model_name, method) -> bool:
    """Whether a view of `model_name` shows `method` as a button a user can
    press: a method only code calls is not one."""
    return bool(
        env["ir.ui.view"].search_count(
            [
                ("model", "=", model_name),
                ("arch_db", "like", f'name="{method}"'),
            ],
            limit=1,
        )
    )


REMOVE_COMMANDS = (2, 3)
ROW_COMMANDS = (1, 2, 3)


def _check_values(model, values, ids, path="") -> None:
    """Refuse a value the screens would not let a user set, here and, the
    same way, in every line an x2many command creates or changes.

    :param model: the model the values are for
    :param dict values: field names to values
    :param list ids: the records written, or nothing on a create
    :param str path: where the values sit, for the message
    :raise OperationError: what is refused, and why
    """
    for name, value in values.items():
        field = model._fields.get(name)
        if field is None:
            raise OperationError(
                f"{path}{model._name} has no field {name}; call describe_model."
            )
        if name in USER_LINK_FIELDS.get(model._name, ()):
            raise OperationError(
                f"{path}{name} ties a contact to an Odoo user, which is set from "
                "the user's own settings."
            )
        if field.readonly and field.compute and not field.inverse:
            # a computed field without an inverse keeps its computed value: the
            # figure asked for would be lost silently (price_unit_product_uom
            # for price_unit)
            raise OperationError(
                f"{path}{name} is computed and cannot be set; call describe_model "
                f"on {model._name} and set the editable field it comes from."
            )
        if field.groups and ADMIN_GROUP in field.groups.split(","):
            raise OperationError(f"{path}{name} is only for administrators.")
        if (
            model._name == "res.partner"
            and name == "email"
            and ids
            and _partners_with_users(model, ids)
        ):
            # the address a user's password reset goes to
            raise OperationError(
                f"{path}the email of a contact who is an Odoo user is changed "
                "from the user's own settings."
            )
        if field.type in ("one2many", "many2many") and isinstance(value, list):
            _check_commands(model, field, value, ids, path)


def _partners_with_users(model, ids) -> bool:
    plain = [ident for ident in ids if isinstance(ident, int)]
    return bool(model.browse(plain).exists().with_context(active_test=False).user_ids)


def _check_commands(model, field, commands, ids, path) -> None:
    """Refuse the x2many commands that delete, reach the technical side, or
    touch lines of another document."""
    name = field.name
    comodel = model.env[field.comodel_name]
    allowed = ONE2MANY_COMMANDS if field.type == "one2many" else MANY2MANY_COMMANDS
    technical = not is_business_model(comodel._name)
    for command in commands:
        if not isinstance(command, (list, tuple)) or not command:
            continue
        code = command[0]
        if code not in allowed:
            raise OperationError(
                f"{path}{name}: command {code} is not allowed; lines are added "
                "(0), changed (1) or, on a draft document, removed one by one (2)."
            )
        if technical and code in (0, 1, 2):
            raise OperationError(
                f"{path}{name}: {comodel._name} records cannot be created or "
                "changed through the bot."
            )
        if field.type == "one2many" and code in ROW_COMMANDS:
            _check_own_line(model, name, command, ids, path)
        if code in (0, 1) and len(command) > 2 and isinstance(command[2], dict):
            line_ids = [command[1]] if code == 1 else None
            _check_values(comodel, command[2], line_ids, f"{path}{name}: ")


def _check_own_line(model, name, command, ids, path) -> None:
    """A line is changed or removed on an existing record it belongs to, and
    removed only while that record is in draft."""
    code = command[0]
    if not ids or any(not isinstance(ident, int) for ident in ids):
        raise OperationError(
            f"{path}{name}: a line is changed or removed on an existing record, by id."
        )
    records = model.browse(ids).exists()
    if command[1] not in records[name].ids:
        raise OperationError(
            f"{path}{name}: line {command[1]!r} does not belong to {model._name} {ids}."
        )
    if code in REMOVE_COMMANDS and (
        "state" not in model._fields
        or any(record.state != "draft" for record in records)
    ):
        raise OperationError(
            f"{path}{name}: lines are removed only while the document is in "
            "draft; removing them is deleting, which the bot never does otherwise."
        )


def _lacks_company(env, operation) -> bool:
    """Whether `operation` creates a record whose company is required but
    not given: the person must pick it, never a default."""
    if operation["op"] != "create":
        return False
    company = env[operation["model"]]._fields.get("company_id")
    return bool(
        company
        and company.type == "many2one"
        and company.required
        and not operation["values"].get("company_id")
    )


def needs_company(env, operations) -> bool:
    """Whether any of `operations` waits for the person to pick a company."""
    return any(_lacks_company(env, operation) for operation in operations)


def set_company(env, operations, company_id) -> list:
    """`operations` with `company_id` given to each one that lacks it."""
    return [
        {**operation, "values": {**operation["values"], "company_id": company_id}}
        if _lacks_company(env, operation)
        else operation
        for operation in operations
    ]


def describe(env, operations) -> list:
    """The proposed operations as the person reads them: each field by its
    label and each value as the screen shows it, never raw ids.

    :param env: an environment in the person's language
    :param list operations: operations validated by `check`
    :return: the lines, Markdown-light
    :rtype: list
    """
    lines = []
    for number, operation in enumerate(operations, 1):
        model = env[operation["model"]]
        label = env["ir.model"]._get(operation["model"]).name or operation["model"]
        if operation["op"] == "create":
            lines.append(
                "**"
                + env._("%(number)s. Create %(model)s", number=number, model=label)
                + "**"
            )
            lines += _values_lines(model, operation["values"])
        else:
            names = _records_text(model, operation["ids"])
            if operation["op"] == "write":
                lines.append(
                    "**"
                    + env._(
                        "%(number)s. Change %(model)s %(records)s",
                        number=number,
                        model=label,
                        records=names,
                    )
                    + "**"
                )
                ids = operation["ids"]
                record = (
                    model.browse(ids[0]).exists()
                    if len(ids) == 1 and isinstance(ids[0], int)
                    else model.browse()
                )
                lines += _values_lines(model, operation["values"], record)
            else:
                lines.append(
                    "**"
                    + env._(
                        "%(number)s. %(model)s %(records)s:",
                        number=number,
                        model=label,
                        records=names,
                    )
                    + "** "
                    + env._(
                        "button %(button)s",
                        button=_button_text(model, operation["method"]),
                    )
                )
        if operation.get("attach_files"):
            lines.append("📎 " + env._("Attach the files you sent"))
        lines.append("")
    return lines[:-1] if lines else lines


def _records_text(model, ids) -> str:
    """The records `ids` name, by their names; a record proposed before by
    its number."""
    names = []
    for ident in ids:
        if isinstance(ident, str):
            names.append(model.env._("(#%(number)s above)", number=ident[4:]))
            continue
        record = model.browse(ident).exists()
        names.append(record.display_name if record else f"#{ident}")
    return ", ".join(names)


def _button_text(model, method) -> str:
    words = method.removeprefix("action_").removeprefix("button_").replace("_", " ")
    return f"«{words}»"


def _currency(model, values):
    """The currency amounts of `values` are in: theirs, their company's, else
    the environment's company's."""
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


def _qty(value) -> str:
    return format_quantity(value) if isinstance(value, (int, float)) else str(value)


QUANTITY_FIELDS = ("product_qty", "product_uom_qty", "quantity")
# the fields a priced line shows in its own words; any other one it sets is
# listed after them, so nothing changes unseen
ROW_FIELDS = ("product_id", "price_unit", *QUANTITY_FIELDS)


def _values_lines(model, values, record=None) -> list:
    """One line per field of `values`; an x2many's commands as its rows, and a
    document's priced lines as they will stand once changed."""
    currency = _currency(model, values)
    if record and "currency_id" in record._fields and record.currency_id:
        currency = record.currency_id
    lines = []
    for name, value in values.items():
        field = model._fields[name]
        comodel = model.env[field.comodel_name] if field.relational else None
        if (
            record
            and field.type == "one2many"
            and isinstance(value, list)
            and _is_priced(comodel)
        ):
            lines += _resulting_lines(comodel, field, record[name], value, currency)
        elif field.type in ("one2many", "many2many") and isinstance(value, list):
            lines += _relation_lines(comodel, field, value, currency)
        else:
            lines.append(
                f"• {_label(model, field)}: {_value_text(model, field, value, currency)}"
            )
    return lines


def _label(model, field) -> str:
    """A field's label in the language of `model`'s environment."""
    return field._description_string(model.env) or field.name


def _value_text(model, field, value, currency) -> str:
    """`value` as the screen shows it: names, not ids."""
    env = model.env
    if value is False or value is None or value == "":
        return "—"
    if field.type == "many2one" and isinstance(value, int):
        record = env[field.comodel_name].browse(value).exists()
        return record.display_name if record else f"#{value}"
    if field.type == "many2many" and isinstance(value, list):
        return _relation_names(env[field.comodel_name], value)
    if field.type == "boolean":
        return env._("Yes") if value else env._("No")
    if field.type == "selection":
        selection = field._description_selection(env)
        return dict(selection).get(value, str(value))
    if field.type == "monetary" and isinstance(value, (int, float)):
        return money(value, currency)
    if field.type in ("float", "integer") and isinstance(value, (int, float)):
        return _qty(value)
    if field.type == "html":
        text = str(value)
        return text if len(text) <= 200 else text[:199] + "…"
    return str(value)


def _relation_names(comodel, commands) -> str:
    """The records a many2many's link commands leave, by name."""
    ids = []
    for command in commands:
        if isinstance(command, (list, tuple)) and command:
            if command[0] == 6 and len(command) > 2:
                ids = list(command[2] or [])
            elif command[0] == 4:
                ids.append(command[1])
    return _records_text(comodel, ids) if ids else "—"


def _relation_lines(comodel, field, commands, currency) -> list:
    """An x2many's commands: new lines one per row, with a total where the
    rows carry a quantity and a unit price."""
    env = comodel.env
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
            lines.append(
                "   ◦ " + env._("Change %(line)s: %(values)s", line=name, values=text)
            )
        elif code == 4:
            lines.append(
                "   ◦ "
                + env._(
                    "Add: %(records)s", records=_records_text(comodel, [command[1]])
                )
            )
        elif code == 6:
            lines.append(
                "   ◦ "
                + env._(
                    "Leave only: %(records)s",
                    records=_records_text(comodel, list(command[2] or [])) or "—",
                )
            )
        elif code in REMOVE_COMMANDS:
            lines.append(
                "   ◦ "
                + env._(
                    "Remove: %(records)s",
                    records=_records_text(comodel, [command[1]]),
                )
            )
    if priced and len(lines) > 2:
        lines.append("   " + _total_text(env, total, currency))
    return lines


def _total_text(env, total, currency) -> str:
    return env._("**Total: %(amount)s** (before taxes)", amount=money(total, currency))


def _quantity_field(comodel):
    return next((name for name in QUANTITY_FIELDS if name in comodel._fields), None)


def _is_priced(comodel) -> bool:
    """Whether a line model has a product, a quantity and a unit price."""
    return bool(
        "product_id" in comodel._fields
        and "price_unit" in comodel._fields
        and _quantity_field(comodel)
    )


def _resulting_lines(comodel, field, existing, commands, currency) -> list:
    """The lines of a document as they will stand once `commands` apply to
    the `existing` ones: every row, marked when it changes, and the total
    that results, so the person checks the document and not the edit."""
    env = comodel.env
    quantity_name = _quantity_field(comodel)
    rows = {
        line.id: {
            "product_id": line.product_id.id,
            "quantity": line[quantity_name],
            "price_unit": line.price_unit,
            "discount": line.discount if "discount" in line._fields else 0.0,
            "mark": "",
            "extra": {},
        }
        for line in existing
    }
    added = []
    for command in commands:
        if not isinstance(command, (list, tuple)) or not command:
            continue
        code = command[0]
        values = command[2] if len(command) > 2 and isinstance(command[2], dict) else {}
        if code == 1 and command[1] in rows:
            row = rows[command[1]]
            row.update(_row_values(values))
            row["extra"] = values
            row["mark"] = "✏️ "
        elif code in REMOVE_COMMANDS and command[1] in rows:
            rows[command[1]]["mark"] = "❌ "
        elif code == 0:
            row = {
                "product_id": False,
                "quantity": 0.0,
                "price_unit": 0.0,
                "discount": 0.0,
            }
            row.update(_row_values(values))
            row.update(mark="➕ ", extra=values)
            added.append(row)
    lines = [
        "• " + env._("%(lines)s (as it will stand):", lines=_label(comodel, field))
    ]
    total = 0.0
    products = comodel.env["product.product"].browse(
        [row["product_id"] for row in [*rows.values(), *added] if row["product_id"]]
    )
    names = {product.id: product.display_name for product in products.exists()}
    for row in [*rows.values(), *added]:
        price = row["price_unit"] or 0.0
        amount = row["quantity"] or 0.0
        subtotal = _subtotal(amount, price, row["discount"])
        text = (
            f"{names.get(row['product_id'], '—')} — {_qty(amount)} × "
            f"{money(price, currency)} = {money(subtotal, currency)}"
        )
        extra = _extra_text(comodel, row["extra"], currency)
        if extra:
            text = f"{text} · {extra}"
        if row["mark"] == "❌ ":
            lines.append("   ❌ " + env._("%(line)s (removed)", line=text))
            continue
        total += subtotal
        lines.append(f"   {row['mark'] or '◦ '}{text}")
    lines.append("   " + _total_text(env, total, currency))
    return lines


def _row_values(values) -> dict:
    """The product, quantity and unit price a line's values set."""
    found = {}
    if "product_id" in values:
        found["product_id"] = values["product_id"]
    amount = next((values[name] for name in QUANTITY_FIELDS if name in values), None)
    if amount is not None:
        found["quantity"] = amount
    if "price_unit" in values:
        found["price_unit"] = values["price_unit"]
    if isinstance(values.get("discount"), (int, float)):
        found["discount"] = values["discount"]
    return found


def _subtotal(amount, price, discount) -> float:
    """A line's amount before taxes, its discount (a percentage) applied."""
    return amount * price * (1 - (discount or 0.0) / 100.0)


def _extra_text(comodel, values, currency) -> str:
    """The fields a priced line sets beyond its product, quantity and price,
    by label: a discount or a tax changes the document as much."""
    return ", ".join(
        f"{_label(comodel, comodel._fields[name])}: "
        f"{_value_text(comodel, comodel._fields[name], value, currency)}"
        for name, value in (values or {}).items()
        if name in comodel._fields and name not in ROW_FIELDS
    )


def _row_text(comodel, values, currency):
    """One row of a line: product, quantity × price = subtotal and whatever
    else it sets when it has them, else its fields by label."""
    product = values.get("product_id")
    amount = next((values[name] for name in QUANTITY_FIELDS if name in values), None)
    price = values.get("price_unit")
    if product and amount is not None and "product_id" in comodel._fields:
        name = _value_text(comodel, comodel._fields["product_id"], product, currency)
        extra = _extra_text(comodel, values, currency)
        suffix = f" · {extra}" if extra else ""
        if isinstance(price, (int, float)) and isinstance(amount, (int, float)):
            discount = values.get("discount")
            subtotal = _subtotal(
                amount, price, discount if isinstance(discount, (int, float)) else 0
            )
            text = (
                f"{name} — {_qty(amount)} × {money(price, currency)}"
                f" = {money(subtotal, currency)}{suffix}"
            )
            return text, subtotal
        return f"{name} — {_qty(amount)}{suffix}", None
    return _plain_text(comodel, values, currency), None


def _plain_text(comodel, values, currency) -> str:
    parts = [
        f"{_label(comodel, comodel._fields[name])}: "
        f"{_value_text(comodel, comodel._fields[name], value, currency)}"
        for name, value in values.items()
        if name in comodel._fields
    ]
    return ", ".join(parts) or "—"


def apply(env, operations, files, requester):
    """Run authorized operations, all or none, and say what they did.

    :param env: a read-write environment in superuser mode, as `requester`
    :param list operations: operations validated by `check`
    :param list files: ``[(name, bytes, mimetype)]`` to attach where asked
    :param requester: the user who asked and authorized
    :return: the records touched, one per operation
    :rtype: list
    """
    if needs_company(env, operations):
        raise OperationError("Pick the company first.")
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
        records.env._(
            "Done from the Telegram bot at the request of %(person)s, who "
            "authorized it.",
            person=requester.name,
        )
    )
    for record in records:
        try:
            # a failed note must not abort the transaction the change is in
            with record.env.cr.savepoint():
                record.message_post(
                    body=body, message_type="comment", subtype_xmlid="mail.mt_note"
                )
        except Exception:
            _logger.info("insight_telegram could not note %s", record, exc_info=True)
