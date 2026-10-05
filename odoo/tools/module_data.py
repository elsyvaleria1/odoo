from __future__ import annotations

import logging
import re
from collections.abc import Callable, Collection, Iterable, Mapping
from typing import TYPE_CHECKING, Any, NamedTuple

from lxml import etree
from psycopg import errors
from psycopg.types.json import Json

from odoo.db.schema import (
    column_exists,
    drop_columns,
    drop_views_depending_on_table,
    get_default_constraint_name,
    get_table_columns,
    get_tables_existing,
    rename_column,
    rename_objects_named_after_column,
    table_exists,
)
from odoo.libs.debug_log import DebugLog
from odoo.libs.sql import SQL
from odoo.orm.validation import MAX_PG_NAME_LENGTH

if TYPE_CHECKING:
    from odoo.db import BaseCursor


_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


# the models whose `_table` is not their name with dots for underscores, for a
# migration that runs before the registry holds them (a pre-migration of base)
_MODEL_TABLES: Mapping[str, str] = {
    "esg.metric.to.survey.question": "esg_metric_to_survey_question_rel",
    "ir.actions.actions": "ir_actions",
    "ir.actions.act_window": "ir_act_window",
    "ir.actions.act_window.view": "ir_act_window_view",
    "ir.actions.act_window_close": "ir_act_window_close",
    "ir.actions.act_url": "ir_act_url",
    "ir.actions.server": "ir_act_server",
    "ir.actions.client": "ir_act_client",
    "ir.actions.report": "ir_act_report_xml",
}


def _table_of(model: str, cr: Any = None) -> str:
    if (dbname := getattr(cr, "dbname", None)) is not None:
        from odoo.modules.registry import Registry

        registry = Registry.registries.get(dbname)
        if registry is not None and model in registry:
            if table := getattr(registry[model], "_table", None):
                return table
    return _MODEL_TABLES.get(model) or model.replace(".", "_")


def _model_slug(model_name: str) -> str:
    return model_name.replace(".", "_")


def model_xmlid(module: str, model_name: str) -> str:
    return f"{module}.model_{_model_slug(model_name)}"


def inherit_xmlid(module: str, model_name: str, parent_name: str) -> str:
    return (
        f"{module}.model_inherit__{_model_slug(model_name)}__{_model_slug(parent_name)}"
    )


def field_xmlid_name(model_name: str, field_name: str) -> str:
    return f"field_{_model_slug(model_name)}__{field_name}"


def field_xmlid(module: str, model_name: str, field_name: str) -> str:
    return f"{module}.{field_xmlid_name(model_name, field_name)}"


def selection_xmlid_name(model_name: str, field_name: str, value: str) -> str:
    xvalue = value.replace(".", "_").replace(" ", "_").lower()
    return f"selection__{_model_slug(model_name)}__{field_name}__{xvalue}"


def selection_xmlid(module: str, model_name: str, field_name: str, value: str) -> str:
    return f"{module}.{selection_xmlid_name(model_name, field_name, value)}"


def _like_prefix(prefix: str) -> str:
    return prefix.replace("_", "\\_") + "%"


def _map_column_values(
    cr: BaseCursor, table: str, column: str, values: Mapping[str, str] | None
) -> None:
    for old_value, new_value in (values or {}).items():
        cr.execute(
            SQL(
                "UPDATE %s SET %s = %s WHERE %s = %s",
                SQL.identifier(table),
                SQL.identifier(column),
                new_value,
                SQL.identifier(column),
                old_value,
            )
        )


def rename_field(
    cr: BaseCursor,
    model: str,
    old: str,
    new: str,
    *,
    values: Mapping[str, str] | None = None,
) -> None:
    # A stored field renamed in place, not dropped and re-added: the column keeps
    # its data, and the `ir.model.fields` row keeps its id -- which is what every
    # `mail.tracking.value`, export template and access record points at, so a
    # drop-and-add would delete that history with the old row. Its external id
    # and, for a Selection, the value rows and their external ids follow.
    table = _table_of(model, cr)
    old_exists, new_exists = (
        column_exists(cr, table, old),
        column_exists(cr, table, new),
    )
    column_renamed = old_exists and not new_exists
    _debug.lifecycle(
        "module_data.rename_field",
        model=model,
        old=old,
        new=new,
        column_renamed=column_renamed,
        values=len(values or {}),
    )
    if column_renamed:
        rename_column(cr, table, old, new)
        _map_column_values(cr, table, new, values)
    elif old_exists:
        # the new field's column is already there, made by a module installed
        # before this rename ran (one the model moved into): what it holds is
        # its default, the old column holds the records' values
        cr.execute(
            SQL(
                "UPDATE %s SET %s = %s",
                SQL.identifier(table),
                SQL.identifier(new),
                SQL.identifier(old),
            )
        )
        _map_column_values(cr, table, new, values)
        drop_columns(cr, table, [old])
    elif new_exists:
        # a table inheriting another in PostgreSQL takes the parent's column
        # rename, but not the index and constraints named after its own column
        rename_objects_named_after_column(cr, table, old, new)
    if column_exists(cr, table, new):
        # the foreign key followed the column; its reflection row follows too,
        # or uninstalling the field's module drops a name that no longer exists
        cr.execute(
            SQL(
                "UPDATE ir_model_constraint SET name = %s WHERE name = %s AND type = 'f'",
                get_default_constraint_name(table, new, "fkey"),
                get_default_constraint_name(table, old, "fkey"),
            )
        )

    cr.execute(
        SQL(
            "SELECT id FROM ir_model_fields WHERE model = %s AND name = %s",
            model,
            old,
        )
    )
    row = cr.fetchone()
    if row is None:
        _debug.logic(
            "module_data.rename_field_skipped", model=model, old=old, reason="no_row"
        )
        return
    field_id = row[0]
    cr.execute(
        SQL(
            "SELECT id FROM ir_model_fields WHERE model = %s AND name = %s",
            model,
            new,
        )
    )
    target = cr.fetchone()
    if target:
        # reflected already, by the module that made the new column: what
        # pointed at the old row -- tracking history above all -- follows to
        # it, and the old row goes rather than be dropped later with that
        # history as an orphan field
        _repoint_references(cr, "ir_model_fields", {field_id: target[0]})
        cr.execute(
            SQL(
                "DELETE FROM ir_model_data WHERE model = 'ir.model.fields' AND res_id = %s",
                field_id,
            )
        )
        cr.execute(SQL("DELETE FROM ir_model_fields WHERE id = %s", field_id))
        _debug.logic(
            "module_data.rename_field_merged",
            model=model,
            old=old,
            into=target[0],
        )
        _logger.info("merged %s.%s into %s", model, old, new)
        return
    cr.execute(SQL("UPDATE ir_model_fields SET name = %s WHERE id = %s", new, field_id))
    cr.execute(
        SQL(
            "UPDATE ir_model_data SET name = %s "
            "WHERE model = 'ir.model.fields' AND name = %s",
            field_xmlid_name(model, new),
            field_xmlid_name(model, old),
        )
    )
    for old_value, new_value in (values or {}).items():
        cr.execute(
            SQL(
                "UPDATE ir_model_fields_selection SET value = %s "
                "WHERE field_id = %s AND value = %s",
                new_value,
                field_id,
                old_value,
            )
        )
    # a value's xml id is named after it as reflection slugs it, which a
    # renamed field or value no longer matches
    cr.execute(
        SQL(
            "SELECT d.id, s.value FROM ir_model_data d "
            "JOIN ir_model_fields_selection s ON s.id = d.res_id "
            "WHERE d.model = 'ir.model.fields.selection' AND s.field_id = %s "
            "AND d.name LIKE %s",
            field_id,
            _like_prefix(selection_xmlid_name(model, old, "")),
        )
    )
    if names := {
        data_id: selection_xmlid_name(model, new, value)
        for data_id, value in cr.fetchall()
    }:
        cr.execute(
            SQL(
                "UPDATE ir_model_data d SET name = n.name "
                "FROM unnest(%s::int[], %s::varchar[]) n(id, name) "
                "WHERE d.id = n.id AND d.name != n.name",
                list(names),
                list(names.values()),
            )
        )
    _logger.info("renamed %s.%s to %s", model, old, new)


MODEL_NAME_COLUMNS = (
    "model",
    "model_id",
    "res_model",
    "model_name",
    "src_model",
    "parent_res_model",
    "relation",
    "res_model_name",
    "alias_model",
    "resource",
)
_MODEL_EXPRESSION_COLUMNS = (
    ("ir_act_window", ("domain", "context")),
    ("ir_act_server", ("code",)),
    ("ir_filters", ("domain", "context", "sort")),
    ("ir_ui_view", ("arch_db",)),
    ("ir_embedded_actions", ("domain", "context")),
)


def rename_model(cr: BaseCursor, old: str, new: str) -> dict[str, str]:
    # Exact names only, never LIKE '%old%': `crm_team` is a prefix of
    # `crm_team_member`, and a substring rewrite renames both.
    old_table, new_table = old.replace(".", "_"), new.replace(".", "_")
    _absorb_forerunner(cr, old, new, old_table, new_table)
    relations = _rename_model_relations(cr, old, old_table, new_table)
    _rename_table_with_dependents(cr, old_table, new_table)
    _rewrite_model_registry(cr, old, new, old_table, new_table)
    repoint_model_name_columns(cr, old, new)
    _rewrite_reference_values(cr, old, new)
    rewrite_quoted_model_names(cr, old, new)
    _debug.lifecycle(
        "module_data.rename_model", old=old, new=new, relations=len(relations)
    )
    _logger.info(
        "renamed model %s to %s, with %d join table(s)%s",
        old,
        new,
        len(relations),
        "".join(f", {a} -> {b}" for a, b in relations.items()),
    )
    return relations


def _absorb_forerunner(
    cr: BaseCursor, old: str, new: str, old_table: str, new_table: str
) -> None:
    # A registry load of the new code before the migration ran (another module
    # upgraded first) reflects the new model: its ir_model row, fields,
    # selections, inherits, constraints and an empty table. The old model's rows
    # carry the ids data references, so each forerunner row folds into its old
    # counterpart, or moves onto the old model when it has none.
    cr.execute(SQL("SELECT model, id FROM ir_model WHERE model = ANY(%s)", [old, new]))
    ids = dict(cr.fetchall())
    if old not in ids or new not in ids:
        return
    old_id, new_id = ids[old], ids[new]
    cr.execute(
        SQL(
            "SELECT relation_table FROM ir_model_fields WHERE model_id = %s "
            "AND ttype = 'many2many' AND relation_table IS NOT NULL",
            new_id,
        )
    )
    dropped = [new_table, *(row[0] for row in cr.fetchall())]
    for table in dropped:
        if not table_exists(cr, table):
            continue
        cr.execute(SQL("SELECT 1 FROM %s LIMIT 1", SQL.identifier(table)))
        if cr.fetchone():
            raise ValueError(
                f"{table} was created for {new} before {old} was renamed to it, "
                "and it holds rows; refusing to guess which rows are the model's"
            )
        cr.execute(SQL("DROP TABLE %s CASCADE", SQL.identifier(table)))

    cr.execute(
        SQL(
            "SELECT n.id, o.id FROM ir_model_fields n LEFT JOIN ir_model_fields o "
            "ON o.model_id = %s AND o.name = n.name WHERE n.model_id = %s",
            old_id,
            new_id,
        )
    )
    fields = dict(cr.fetchall())
    field_pairs = {n: o for n, o in fields.items() if o}
    cr.execute(
        SQL(
            "SELECT n.id, o.id FROM ir_model_fields_selection n "
            "LEFT JOIN ir_model_fields_selection o "
            "ON o.field_id = (%s::jsonb ->> n.field_id::text)::int AND o.value = n.value "
            "WHERE n.field_id = ANY(%s)",
            Json({str(n): o for n, o in field_pairs.items()}),
            list(field_pairs),
        )
    )
    selections = dict(cr.fetchall())
    _fold(cr, "ir.model.fields.selection", "ir_model_fields_selection", selections)
    cr.execute(
        SQL(
            "UPDATE ir_model_fields_selection SET field_id = "
            "(%s::jsonb ->> field_id::text)::int WHERE field_id = ANY(%s)",
            Json({str(n): o for n, o in field_pairs.items()}),
            list(field_pairs),
        )
    )
    for column, other in (("model_id", "parent_id"), ("parent_id", "model_id")):
        cr.execute(
            SQL(
                "SELECT n.id, o.id FROM ir_model_inherit n LEFT JOIN ir_model_inherit o "
                "ON o.%s = %s AND o.%s = n.%s WHERE n.%s = %s",
                SQL.identifier(column),
                old_id,
                SQL.identifier(other),
                SQL.identifier(other),
                SQL.identifier(column),
                new_id,
            )
        )
        inherits = dict(cr.fetchall())
        _fold(cr, "ir.model.inherit", "ir_model_inherit", inherits)
    cr.execute(
        SQL(
            "SELECT n.id, o.id FROM ir_model_constraint n LEFT JOIN ir_model_constraint o "
            "ON o.model = %s AND o.module = n.module "
            "AND o.name = %s || substring(n.name from %s) "
            "WHERE n.model = %s AND n.name LIKE %s",
            old_id,
            old_table,
            len(new_table) + 1,
            new_id,
            new_table.replace("_", "\\_") + "\\_%",
        )
    )
    constraints = dict(cr.fetchall())
    _fold(cr, "ir.model.constraint", "ir_model_constraint", constraints)
    cr.execute(
        SQL(
            "DELETE FROM ir_model_constraint c WHERE c.model = %s AND NOT EXISTS "
            "(SELECT 1 FROM pg_constraint p WHERE p.conname = c.name) RETURNING id",
            new_id,
        )
    )
    _drop_xmlids(cr, "ir.model.constraint", [row[0] for row in cr.fetchall()])
    cr.execute(
        SQL(
            "DELETE FROM ir_model_relation WHERE model = %s AND name = ANY(%s) "
            "RETURNING id",
            new_id,
            dropped,
        )
    )
    _drop_xmlids(cr, "ir.model.relation", [row[0] for row in cr.fetchall()])
    _fold(cr, "ir.model.fields", "ir_model_fields", fields)
    cr.execute(
        SQL(
            "UPDATE ir_model_fields SET model = %s WHERE model_id = %s",
            old,
            new_id,
        )
    )
    _fold(cr, "ir.model", "ir_model", {new_id: old_id})
    _debug.lifecycle(
        "module_data.forerunner_absorbed",
        old=old,
        new=new,
        fields=len(fields),
        folded_fields=len(field_pairs),
        tables=dropped,
    )
    _logger.info(
        "%s had been reflected before %s was renamed to it; its rows folded into "
        "the old model's",
        new,
        old,
    )


def _fold(
    cr: BaseCursor, xmlid_model: str, table: str, rows: Mapping[int, int | None]
) -> None:
    """Fold each row of ``rows`` into its counterpart, or keep it when it has none.

    A row with a counterpart hands its references and its xmlids over and is
    deleted; an xmlid of a module the counterpart already has one in is
    dropped instead, since the rename gives the counterpart's the same name.
    """
    pairs = {doomed: kept for doomed, kept in rows.items() if kept}
    if not pairs:
        return
    _repoint_references(cr, table, pairs)
    for doomed, kept in pairs.items():
        cr.execute(
            SQL(
                "DELETE FROM ir_model_data d WHERE d.model = %s AND d.res_id = %s "
                "AND EXISTS (SELECT 1 FROM ir_model_data k WHERE k.model = %s "
                "AND k.res_id = %s AND k.module = d.module)",
                xmlid_model,
                doomed,
                xmlid_model,
                kept,
            )
        )
        cr.execute(
            SQL(
                "UPDATE ir_model_data SET res_id = %s WHERE model = %s AND res_id = %s",
                kept,
                xmlid_model,
                doomed,
            )
        )
    cr.execute(
        SQL("DELETE FROM %s WHERE id = ANY(%s)", SQL.identifier(table), list(pairs))
    )


def _drop_xmlids(cr: BaseCursor, xmlid_model: str, res_ids: list[int]) -> None:
    cr.execute(
        SQL(
            "DELETE FROM ir_model_data WHERE model = %s AND res_id = ANY(%s)",
            xmlid_model,
            res_ids,
        )
    )


def _repoint_references(
    cr: BaseCursor, referenced: str, moves: Mapping[int, int]
) -> None:
    if not moves:
        return
    cr.execute(
        SQL(
            "SELECT c.conrelid::regclass::text, a.attname FROM pg_constraint c "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
            "WHERE c.contype = 'f' AND c.confrelid = %s::regclass "
            "AND cardinality(c.conkey) = 1",
            referenced,
        )
    )
    doomed, kept = list(moves), list(moves.values())
    for table, column in cr.fetchall():
        moved = SQL(
            "UPDATE %s t SET %s = m.kept FROM unnest(%s::int[], %s::int[]) m(doomed, kept) "
            "WHERE t.%s = m.doomed",
            SQL.identifier(table),
            SQL.identifier(column),
            doomed,
            kept,
            SQL.identifier(column),
        )
        try:
            with cr.savepoint(flush=False):
                cr.execute(moved, log_exceptions=False)
            continue
        except errors.UniqueViolation:
            pass
        # some rows collide with one the kept record already has: only those
        # are redundant, every other row still moves
        cr.execute(
            SQL(
                # as text: psycopg has no tid loader, so a bare ctid comes back
                # as str or bytes depending on the fetch protocol, and bytes
                # bind back as bytea, which no cast turns into a tid
                "SELECT ctid::text FROM %s WHERE %s = ANY(%s)",
                SQL.identifier(table),
                SQL.identifier(column),
                doomed,
            )
        )
        for (ctid,) in cr.fetchall():
            row = SQL("ctid = %s::tid", ctid)
            try:
                with cr.savepoint(flush=False):
                    cr.execute(
                        SQL(
                            "UPDATE %s t SET %s = m.kept FROM unnest(%s::int[], %s::int[]) "
                            "m(doomed, kept) WHERE t.%s = m.doomed AND t.%s",
                            SQL.identifier(table),
                            SQL.identifier(column),
                            doomed,
                            kept,
                            SQL.identifier(column),
                            row,
                        ),
                        log_exceptions=False,
                    )
            except errors.UniqueViolation:
                cr.execute(SQL("DELETE FROM %s WHERE %s", SQL.identifier(table), row))


# record ids kept beside a model name in an Integer column that no field
# declares a Many2oneReference, so ir_model_fields cannot pair them; the model
# column holds a name or an ir_model id, on the row or, written
# "link->table.column", on the row its link points at
UNDECLARED_REFERENCES: tuple[tuple[str, str, str], ...] = (
    ("approval_observation", "res_id", "model_name"),
    ("integration_exchange", "origin_record_id", "origin_model"),
    ("ir_act_window", "res_id", "res_model"),
    ("ir_embedded_actions", "parent_res_id", "parent_res_model"),
    (
        "ir_filters",
        "embedded_parent_res_id",
        "embedded_action_id->ir_embedded_actions.parent_res_model",
    ),
    ("mail_alias", "alias_force_thread_id", "alias_model_id"),
    ("mail_alias", "alias_parent_thread_id", "alias_parent_model_id"),
    ("res_users_settings_embedded_action", "res_id", "res_model"),
    ("snailmail_letter", "res_id", "model"),
)


def rekey_records(
    cr: BaseCursor, models: Collection[str], table: str, moves: Mapping[int, int]
) -> None:
    # A row keyed anew carries every stored reference to it along. A
    # table-inheritance tree has no foreign key to follow, so the references
    # are the ones reflected in ir_model_fields: Many2one and Many2many columns,
    # (model, res_id) pairs, reference values, and tracked Many2one values.
    # `models` names every model whose records are rows of `table`, which a
    # table inheriting it in PostgreSQL holds too.
    moves = {old: new for old, new in moves.items() if old != new}
    if not moves:
        return
    models = list(models)
    olds, news = list(moves), list(moves.values())
    _debug.lifecycle(
        "module_data.rekey_records", models=models, table=table, moves=len(moves)
    )
    # a foreign key into the rows refuses their new ids before the columns
    # holding it follow, which the fields below rekey; it is restored as it
    # was, so a reference no field explains fails here rather than dangle
    foreign_keys = _foreign_keys_into_tree(cr, table)
    for referencing, name, __ in foreign_keys:
        cr.execute(
            SQL(
                "ALTER TABLE %s DROP CONSTRAINT %s",
                SQL.identifier(referencing),
                SQL.identifier(name),
            )
        )
    _rekey_column(cr, table, "id", olds, news)
    cr.execute(
        SQL(
            "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
            "GREATEST((SELECT max(id) FROM %s), 1))",
            table,
            SQL.identifier(table),
        )
    )
    cr.execute(
        "SELECT model, name, ttype, relation_table, column1, column2, relation, "
        "company_dependent FROM ir_model_fields "
        "WHERE store AND (relation = ANY(%(models)s) "
        "OR (model = ANY(%(models)s) AND ttype = 'many2many') "
        "OR ttype IN ('many2one_reference', 'reference'))",
        {"models": models},
    )
    rekeyed = set()
    for (
        model,
        name,
        ttype,
        relation_table,
        column1,
        column2,
        relation,
        cd,
    ) in cr.fetchall():
        if ttype == "many2one" and relation in models:
            target = (_table_of(model, cr), name, SQL())
            if cd:
                raise ValueError(
                    f"rekey_records: {model}.{name} is company-dependent; its "
                    "references are values of a jsonb column, which this does not rekey"
                )
        elif ttype == "many2many" and relation in models:
            target = (relation_table, column2, SQL())
        elif ttype == "many2many":
            target = (relation_table, column1, SQL())
        elif ttype == "many2one_reference":
            condition = _model_condition_of(cr, _table_of(model, cr), name, models)
            if condition is None:
                continue
            target = (_table_of(model, cr), name, condition)
        elif ttype == "reference":
            _rekey_reference_values(cr, _table_of(model, cr), name, models, moves)
            continue
        else:
            continue
        if target[:2] in rekeyed or not column_exists(cr, target[0], target[1]):
            continue
        rekeyed.add(target[:2])
        _rekey_column(cr, *target[:2], olds, news, target[2])
    for referencing, id_column, model_column in UNDECLARED_REFERENCES:
        if not column_exists(cr, referencing, id_column):
            continue
        if "->" in model_column:
            link, link_target = model_column.split("->")
            target_table, target_column = link_target.split(".")
            if not column_exists(cr, referencing, link) or not column_exists(
                cr, target_table, target_column
            ):
                continue
            condition = SQL(
                " AND %s IN (SELECT id FROM %s WHERE %s = ANY(%s))",
                SQL.identifier(link),
                SQL.identifier(target_table),
                SQL.identifier(target_column),
                models,
            )
        elif column_exists(cr, referencing, model_column):
            condition = _model_condition(cr, referencing, model_column, models)
        else:
            continue
        _rekey_column(cr, referencing, id_column, olds, news, condition)
    if table_exists(cr, "mail_tracking_value"):
        tracked = SQL(
            " AND field_id IN (SELECT id FROM ir_model_fields "
            "WHERE ttype = 'many2one' AND relation = ANY(%s))",
            models,
        )
        for column in ("old_value_integer", "new_value_integer"):
            _rekey_column(cr, "mail_tracking_value", column, olds, news, tracked)
    for referencing, name, definition in foreign_keys:
        cr.execute(
            SQL(
                "ALTER TABLE %s ADD CONSTRAINT %s %s",
                SQL.identifier(referencing),
                SQL.identifier(name),
                SQL(definition),
            )
        )


def rekey_property_values(
    env: Any, models: Collection[str], moves: Mapping[int, int]
) -> None:
    # A Properties value keeps a relational property's ids in its jsonb, by
    # the names its container's definition gives them; only the registry knows
    # which container defines which field, so this runs once it is loaded (an
    # end- migration), after rekey_records moved the rows.
    moves = {old: new for old, new in moves.items() if old != new}
    if not moves:
        return
    models = set(models)
    cr = env.cr

    def moved(value: Any) -> Any:
        if isinstance(value, int) and not isinstance(value, bool):
            return moves.get(value, value)
        if isinstance(value, list):
            return [moved(item) for item in value]
        return value

    for model_name, model in env.registry.items():
        if model._abstract or not model._auto:
            continue
        for field in model._fields.values():
            if field.type != "properties" or not field.store:
                continue
            container_name, definition_name = field.definition.split(".", 1)
            cr.execute(
                SQL(
                    "SELECT id, %s FROM %s WHERE %s IS NOT NULL",
                    SQL.identifier(field.name),
                    SQL.identifier(model._table),
                    SQL.identifier(field.name),
                )
            )
            values_by_id = dict(cr.fetchall())
            if not values_by_id:
                continue
            # the container may be a related or computed field: read it as the
            # registry would, and each container's definition once
            records = (
                env[model_name]
                .sudo()
                .with_context(active_test=False)
                .browse(list(values_by_id))
            )
            names_by_container: dict[int, set[str]] = {}
            relational = 0  # debuglog
            for record in records:
                container = record[container_name]
                if container.id not in names_by_container:
                    names_by_container[container.id] = {
                        prop["name"]
                        for prop in (container[definition_name] or ())
                        if prop.get("type") in ("many2one", "many2many")
                        and prop.get("comodel") in models
                    }
                names = names_by_container[container.id]
                if not names:
                    continue
                relational += 1
                values = values_by_id[record.id]
                rekeyed = {
                    name: moved(value) if name in names else value
                    for name, value in values.items()
                }
                if rekeyed != values:
                    cr.execute(
                        SQL(
                            "UPDATE %s SET %s = %s WHERE id = %s",
                            SQL.identifier(model._table),
                            SQL.identifier(field.name),
                            Json(rekeyed),
                            record.id,
                        )
                    )
            _debug.lifecycle(
                "module_data.rekey_property_values",
                model=model_name,
                field=field.name,
                rows=relational,
            )
    env.invalidate_all()


def rehome_references(
    cr: BaseCursor,
    models: Collection[str],
    into: str,
    *,
    keep: Collection[str] = ("ir.model.data",),
) -> None:
    # A record that became its parent's row extended (`_inherits_shared_id`)
    # files its messages, followers, activities and attachments under its
    # parent's model, with the same id. An external id still names the record.
    models = list(models)
    cr.execute(
        "SELECT model, name FROM ir_model_fields "
        "WHERE ttype = 'many2one_reference' AND store AND model <> ALL(%s)",
        [list(keep)],
    )
    for model, name in cr.fetchall():
        table = _table_of(model, cr)
        found = _model_column_of(cr, table, name)
        if found is None:
            continue
        column, is_id = found
        if is_id:
            cr.execute(
                SQL(
                    "UPDATE %s SET %s = (SELECT id FROM ir_model WHERE model = %s) "
                    "WHERE %s IN (SELECT id FROM ir_model WHERE model = ANY(%s))",
                    SQL.identifier(table),
                    SQL.identifier(column),
                    into,
                    SQL.identifier(column),
                    models,
                )
            )
        else:
            cr.execute(
                SQL(
                    "UPDATE %s SET %s = %s WHERE %s = ANY(%s)",
                    SQL.identifier(table),
                    SQL.identifier(column),
                    into,
                    SQL.identifier(column),
                    models,
                )
            )
    _debug.lifecycle("module_data.rehome_references", models=models, into=into)


def lift_columns(
    cr: BaseCursor,
    source: str,
    target: str,
    columns: Collection[str | tuple[str, str]],
    *,
    keep_target: Collection[str] = (),
) -> list[str]:
    # Columns of `source` (and of every table inheriting it in PostgreSQL)
    # become `target`'s, row by row on the same id: copied, checked, then
    # dropped. A column in `keep_target` keeps the target's own value where it
    # has one. A row that held a value the target did not receive raises
    # before anything is dropped, so a short copy fails the upgrade instead of
    # losing what it missed. A (source column, target column) pair renames the
    # column on the way. Returns the source columns lifted.
    pairs = [
        (column, column) if isinstance(column, str) else column for column in columns
    ]
    pairs = [(old, new) for old, new in pairs if column_exists(cr, source, old)]
    for column, target_column in pairs:
        old_name = SQL.identifier(column)
        name = SQL.identifier(target_column)
        if not column_exists(cr, target, target_column):
            cr.execute(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute"
                " WHERE attrelid = %s::regclass AND attname = %s",
                [source, column],
            )
            [[column_type]] = cr.fetchall()
            cr.execute(
                SQL(
                    "ALTER TABLE %s ADD COLUMN %s %s",
                    SQL.identifier(target),
                    name,
                    SQL(column_type),
                )
            )
        kept = target_column in keep_target
        cr.execute(
            SQL(
                "UPDATE %s t SET %s = %s FROM %s s WHERE s.id = t.id",
                SQL.identifier(target),
                name,
                SQL("COALESCE(t.%s, s.%s)", name, old_name)
                if kept
                else SQL("s.%s", old_name),
                SQL.identifier(source),
            )
        )
        cr.execute(
            SQL(
                "SELECT count(*) FROM %s s WHERE s.%s IS NOT NULL AND NOT EXISTS"
                " (SELECT 1 FROM %s t WHERE t.id = s.id AND %s)",
                SQL.identifier(source),
                old_name,
                SQL.identifier(target),
                SQL("t.%s IS NOT NULL", name)
                if kept
                else SQL("t.%s IS NOT DISTINCT FROM s.%s", name, old_name),
            )
        )
        [[missed]] = cr.fetchall()
        if missed:
            raise ValueError(
                f"lift_columns: {missed} row(s) of {source}.{column} have no "
                f"{target} row to receive their value; nothing was dropped"
            )
        _debug.lifecycle(
            "module_data.lift_column", source=source, target=target, column=column
        )
    cr.execute(
        """
        WITH RECURSIVE tree(oid) AS (
            SELECT %s::regclass::oid
             UNION
            SELECT inherit.inhrelid FROM pg_inherits inherit
              JOIN tree ON inherit.inhparent = tree.oid
        )
        SELECT oid::regclass::text FROM tree
        """,
        [source],
    )
    lifted = [column for column, __ in pairs]
    tables = [table for (table,) in cr.fetchall()]
    # a view reading the column, on any table of the tree, is its module's to
    # rebuild at init; the root's drop cascades to the children's columns
    for table in tables:
        for column in lifted:
            drop_views_depending_on_table(cr, table, column)
    for table in tables:
        for column in lifted:
            cr.execute(
                SQL(
                    "ALTER TABLE %s DROP COLUMN IF EXISTS %s",
                    SQL.identifier(table),
                    SQL.identifier(column),
                )
            )
    return lifted


def _foreign_keys_into_tree(cr: BaseCursor, table: str) -> list[tuple[str, str, str]]:
    cr.execute(
        """
        WITH RECURSIVE tree(oid) AS (
            SELECT %s::regclass::oid
             UNION
            SELECT inherit.inhrelid FROM pg_inherits inherit
              JOIN tree ON inherit.inhparent = tree.oid
        )
        SELECT con.conrelid::regclass::text, con.conname, pg_get_constraintdef(con.oid)
          FROM pg_constraint con JOIN tree ON con.confrelid = tree.oid
         WHERE con.contype = 'f'
        """,
        [table],
    )
    return cr.fetchall()


def _model_column_of(
    cr: BaseCursor, table: str, res_column: str
) -> tuple[str, bool] | None:
    # a Many2oneReference names its model beside it, by name in a char column
    # (res_id <-> res_model or model, cause_res_id <-> cause_model) or as an
    # ir_model id (calendar_event.res_model_id): the column, and whether it is an id
    prefix = res_column.removesuffix("res_id")
    columns = get_table_columns(cr, table)
    for base in (f"{prefix}res_model", f"{prefix}model"):
        for candidate, is_id in ((base, False), (f"{base}_id", True)):
            column = columns.get(candidate)
            if column and (column["udt_name"] == "int4") == is_id:
                return candidate, is_id
    return None


def _model_condition_of(
    cr: BaseCursor, table: str, res_column: str, models: list[str]
) -> SQL | None:
    found = _model_column_of(cr, table, res_column)
    if found is None:
        return None
    return _model_condition(cr, table, found[0], models)


def _model_condition(cr: BaseCursor, table: str, column: str, models: list[str]) -> SQL:
    if get_table_columns(cr, table)[column]["udt_name"] == "int4":
        return SQL(
            " AND %s IN (SELECT id FROM ir_model WHERE model = ANY(%s))",
            SQL.identifier(column),
            models,
        )
    return SQL(" AND %s = ANY(%s)", SQL.identifier(column), models)


def _rekey_column(
    cr: BaseCursor,
    table: str,
    column: str,
    olds: list[int],
    news: list[int],
    where: SQL | None = None,
) -> None:
    where = where or SQL()
    # through negative ids: a row may take an id another holds until that one
    # moves too, and a unique key on the column would refuse the overlap
    cr.execute(
        SQL(
            "UPDATE %s t SET %s = -m.new FROM unnest(%s::int[], %s::int[]) m(old, new) "
            "WHERE t.%s = m.old%s",
            SQL.identifier(table),
            SQL.identifier(column),
            olds,
            news,
            SQL.identifier(column),
            where,
        )
    )
    cr.execute(
        SQL(
            "UPDATE %s SET %s = -%s WHERE %s < 0%s",
            SQL.identifier(table),
            SQL.identifier(column),
            SQL.identifier(column),
            SQL.identifier(column),
            where,
        )
    )


def _rekey_reference_values(
    cr: BaseCursor,
    table: str,
    column: str,
    models: list[str],
    moves: Mapping[int, int],
) -> None:
    if not column_exists(cr, table, column):
        return
    for model in models:
        cr.execute(
            SQL(
                "UPDATE %s t SET %s = %s || m.new FROM unnest(%s::int[], %s::int[]) "
                "m(old, new) WHERE t.%s = %s || m.old",
                SQL.identifier(table),
                SQL.identifier(column),
                f"{model},",
                list(moves),
                list(moves.values()),
                SQL.identifier(column),
                f"{model},",
            )
        )


def _moved_identifier(cr: BaseCursor, table: str, suffix: str) -> str:
    """Name a constraint or index of ``table`` that ended in ``suffix``.

    :return: ``table + suffix`` when it fits and is free; otherwise the table
        part is shortened and the column and label kept, as PostgreSQL names
        what it creates, and a counter settles a collision
    :rtype: str
    """
    counter = 0
    while True:
        tag = str(counter) if counter else ""
        room = MAX_PG_NAME_LENGTH - len(suffix) - len(tag)
        name = (
            table[:room] + tag + suffix
            if room > 0
            else (table + tag + suffix)[:MAX_PG_NAME_LENGTH]
        )
        cr.execute(
            SQL(
                "SELECT 1 FROM pg_constraint WHERE conrelid = %s::regclass "
                "AND conname = %s UNION ALL SELECT 1 FROM pg_class "
                "WHERE relname = %s AND relnamespace = current_schema()::regnamespace",
                table,
                name,
                name,
            )
        )
        if not cr.fetchone():
            return name
        counter += 1


def _rename_table_with_dependents(cr: BaseCursor, old: str, new: str) -> bool:
    if not table_exists(cr, old) or table_exists(cr, new):
        return False
    cr.execute(
        SQL("ALTER TABLE %s RENAME TO %s", SQL.identifier(old), SQL.identifier(new))
    )
    cr.execute(
        SQL(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = %s::regclass AND conname LIKE %s",
            new,
            old.replace("_", "\\_") + "\\_%",
        )
    )
    # the names that fit go first, so a shortened one never takes their place
    for (name,) in sorted(
        cr.fetchall(),
        key=lambda row: len(new + row[0][len(old) :]) > MAX_PG_NAME_LENGTH,
    ):
        cr.execute(
            SQL(
                "ALTER TABLE %s RENAME CONSTRAINT %s TO %s",
                SQL.identifier(new),
                SQL.identifier(name),
                SQL.identifier(_moved_identifier(cr, new, name[len(old) :])),
            )
        )
    cr.execute(
        SQL(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() "
            "AND tablename = %s AND indexname LIKE %s",
            new,
            old.replace("_", "\\_") + "\\_%",
        )
    )
    for (name,) in sorted(
        cr.fetchall(),
        key=lambda row: len(new + row[0][len(old) :]) > MAX_PG_NAME_LENGTH,
    ):
        cr.execute(
            SQL(
                "ALTER INDEX %s RENAME TO %s",
                SQL.identifier(name),
                SQL.identifier(_moved_identifier(cr, new, name[len(old) :])),
            )
        )
    # the sequences the table owns (a join table owns none): guessing
    # `old_id_seq` compares a name that may outgrow the limit, which
    # PostgreSQL refuses as an identifier
    cr.execute(
        SQL(
            "SELECT seq.relname FROM pg_depend dep "
            "JOIN pg_class seq ON seq.oid = dep.objid AND seq.relkind = 'S' "
            "WHERE dep.classid = 'pg_class'::regclass "
            "AND dep.refobjid = %s::regclass AND dep.deptype IN ('a', 'i')",
            new,
        )
    )
    for (name,) in cr.fetchall():
        if name.startswith(old):
            cr.execute(
                SQL(
                    "ALTER SEQUENCE %s RENAME TO %s",
                    SQL.identifier(name),
                    SQL.identifier(_moved_identifier(cr, new, name[len(old) :])),
                )
            )
    return True


def _rename_model_relations(
    cr: BaseCursor, old: str, old_table: str, new_table: str
) -> dict[str, str]:
    cr.execute(
        SQL(
            "SELECT DISTINCT model, relation, relation_table, column1, column2 "
            "FROM ir_model_fields WHERE ttype = 'many2many' "
            "AND relation_table IS NOT NULL AND (model = %s OR relation = %s)",
            old,
            old,
        )
    )
    old_column, new_column = f"{old_table}_id", f"{new_table}_id"
    renamed: dict[str, str] = {}
    for model, relation, relation_table, column1, column2 in cr.fetchall():
        tables = [_table_of(model, cr), _table_of(relation, cr)]
        target = relation_table
        if relation_table == "_".join(sorted(tables)) + "_rel":
            moved = [new_table if t == old_table else t for t in tables]
            target = "_".join(sorted(moved)) + "_rel"
            # PostgreSQL would truncate the moved name and the ORM refuses it: a
            # field whose automatic name outgrows the limit declares relation= with
            # the name its table already has, so the table stays where it is.
            if len(target) > MAX_PG_NAME_LENGTH:
                target = relation_table
        if target != relation_table and table_exists(cr, relation_table):
            if table_exists(cr, target):
                raise ValueError(
                    f"both {relation_table} and {target} exist; refusing to guess "
                    "which one holds the links"
                )
            _rename_table_with_dependents(cr, relation_table, target)
            renamed[relation_table] = target
        if table_exists(cr, target):
            for column in (column1, column2):
                if column == old_column and not column_exists(cr, target, new_column):
                    rename_column(cr, target, old_column, new_column)
        cr.execute(
            SQL(
                "UPDATE ir_model_fields SET relation_table = %s, "
                "column1 = CASE WHEN column1 = %s THEN %s ELSE column1 END, "
                "column2 = CASE WHEN column2 = %s THEN %s ELSE column2 END "
                "WHERE ttype = 'many2many' AND relation_table = %s",
                target,
                old_column,
                new_column,
                old_column,
                new_column,
                relation_table,
            )
        )
        if target != relation_table:
            cr.execute(
                SQL(
                    "UPDATE ir_model_relation SET name = %s WHERE name = %s",
                    target,
                    relation_table,
                )
            )
    return renamed


def _rewrite_model_registry(
    cr: BaseCursor, old: str, new: str, old_table: str, new_table: str
) -> None:
    for statement in (
        "UPDATE ir_model SET model = %s WHERE model = %s",
        "UPDATE ir_model_fields SET model = %s WHERE model = %s",
        "UPDATE ir_model_fields SET relation = %s WHERE relation = %s",
    ):
        cr.execute(SQL(statement, new, old))
    owned = SQL("(SELECT id FROM ir_model WHERE model = %s)", new)
    cr.execute(
        SQL(
            "UPDATE ir_model_constraint SET name = %s || substring(name from %s) "
            "WHERE model = %s AND name LIKE %s",
            new_table + "_",
            len(old_table) + 2,
            owned,
            old_table.replace("_", "\\_") + "\\_%",
        )
    )
    cr.execute(
        SQL(
            "UPDATE ir_model_data SET name = %s WHERE model = 'ir.model' AND name = %s",
            f"model_{new_table}",
            f"model_{old_table}",
        )
    )
    for prefix, xmlid_model, source, scope in (
        ("field_{}__", "ir.model.fields", "ir_model_fields", "model_id"),
        ("selection__{}__", "ir.model.fields.selection", None, None),
        ("model_inherit__{}__", "ir.model.inherit", "ir_model_inherit", "model_id"),
        ("constraint_{}_", "ir.model.constraint", "ir_model_constraint", "model"),
    ):
        old_prefix, new_prefix = prefix.format(old_table), prefix.format(new_table)
        restrict = (
            SQL(
                " AND res_id IN (SELECT id FROM %s WHERE %s = %s)",
                SQL.identifier(source),
                SQL.identifier(scope),
                owned,
            )
            if source and scope
            else SQL()
        )
        cr.execute(
            SQL(
                "UPDATE ir_model_data SET name = %s || substring(name from %s) "
                "WHERE model = %s AND name LIKE %s%s",
                new_prefix,
                len(old_prefix) + 1,
                xmlid_model,
                old_prefix.replace("_", "\\_") + "%",
                restrict,
            )
        )


def repoint_model_name_columns(
    cr: BaseCursor, old: str, new: str, *, skip: Collection[tuple[str, str]] = ()
) -> None:
    cr.execute(
        SQL(
            "SELECT c.table_name, c.column_name FROM information_schema.columns c "
            "JOIN information_schema.tables t ON t.table_schema = c.table_schema "
            "AND t.table_name = c.table_name "
            "WHERE c.table_schema = current_schema() AND t.table_type = 'BASE TABLE' "
            "AND c.data_type IN ('character varying', 'text') "
            "AND c.column_name = ANY(%s)",
            list(MODEL_NAME_COLUMNS),
        )
    )
    for table, column in cr.fetchall():
        if (table, column) in skip:
            continue
        cr.execute(
            SQL(
                "UPDATE %s SET %s = %s WHERE %s = %s",
                SQL.identifier(table),
                SQL.identifier(column),
                new,
                SQL.identifier(column),
                old,
            )
        )


def _rewrite_reference_values(cr: BaseCursor, old: str, new: str) -> None:
    cr.execute(
        "SELECT model, name FROM ir_model_fields WHERE ttype = 'reference' AND store"
    )
    for model, field in cr.fetchall():
        table = _table_of(model, cr)
        if not column_exists(cr, table, field):
            continue
        cr.execute(
            SQL(
                "UPDATE %s SET %s = %s || substring(%s from %s) WHERE %s LIKE %s",
                SQL.identifier(table),
                SQL.identifier(field),
                new + ",",
                SQL.identifier(field),
                len(old) + 2,
                SQL.identifier(field),
                old.replace("_", "\\_") + ",%",
            )
        )


def rewrite_quoted_model_names(cr: BaseCursor, old: str, new: str) -> None:
    existing = set(get_tables_existing(cr, [t for t, _ in _MODEL_EXPRESSION_COLUMNS]))
    for table, columns in _MODEL_EXPRESSION_COLUMNS:
        if table not in existing:
            continue
        types = get_table_columns(cr, table)
        for column in columns:
            if column not in types:
                continue
            for quote in ("'", '"'):
                needle, replacement = f"{quote}{old}{quote}", f"{quote}{new}{quote}"
                if types[column]["udt_name"] == "jsonb":
                    # jsonb::text escapes a double quote, so each value is
                    # rewritten as the text it is, not as the document's text
                    cr.execute(
                        SQL(
                            """
                            UPDATE %(table)s SET %(column)s = (
                                   SELECT jsonb_object_agg(key, replace(value, %(needle)s, %(new)s))
                                     FROM jsonb_each_text(%(column)s))
                             WHERE EXISTS (
                                   SELECT 1 FROM jsonb_each_text(%(column)s)
                                    WHERE position(%(needle)s in value) > 0)
                            """,
                            table=SQL.identifier(table),
                            column=SQL.identifier(column),
                            needle=needle,
                            new=replacement,
                        )
                    )
                    continue
                cr.execute(
                    SQL(
                        "UPDATE %s SET %s = replace(%s, %s, %s) "
                        "WHERE position(%s in %s) > 0",
                        SQL.identifier(table),
                        SQL.identifier(column),
                        SQL.identifier(column),
                        needle,
                        replacement,
                        needle,
                        SQL.identifier(column),
                    )
                )


def retire_empty_module(cr: BaseCursor, module: str) -> None:
    cr.execute(SQL("SELECT 1 FROM ir_model_data WHERE module = %s LIMIT 1", module))
    if cr.fetchone():
        _debug.logic("module_data.module_kept", module=module, reason="has_xmlids")
        return
    cr.execute(
        SQL(
            "UPDATE ir_module_module SET state = 'uninstalled', db_version = NULL "
            "WHERE name = %s AND state != 'uninstalled'",
            module,
        )
    )
    retired = cr.rowcount > 0
    # Also for a row already uninstalled: the module is gone from disk, and a
    # leftover auto_install makes the loader mark it `to install` the day its
    # dependencies happen to be installed, which ends the upgrade in an
    # inconsistent state naming a module nobody can supply.
    cr.execute(
        SQL(
            "UPDATE ir_module_module SET auto_install = FALSE "
            "WHERE name = %s AND auto_install",
            module,
        )
    )
    cr.execute(
        SQL(
            "DELETE FROM ir_module_module_dependency "
            "WHERE module_id = (SELECT id FROM ir_module_module WHERE name = %s)",
            module,
        )
    )
    _debug.lifecycle("module_data.module_retired", module=module, retired=retired)
    if retired:
        _logger.info("%s retired: every record it shipped now lives elsewhere", module)


def rename_module(cr: BaseCursor, old: str, new: str) -> bool:
    cr.execute(SQL("SELECT id FROM ir_module_module WHERE name = %s", old))
    if not cr.fetchone():
        return False
    _drop_uninstalled_placeholder(cr, old, new)
    rename = _ModuleRename(old, new, *_module_names(cr, old))
    cr.execute(
        SQL(
            "UPDATE ir_module_module SET name = %s, data_file_checksums = NULL "
            "WHERE name = %s",
            new,
            old,
        )
    )
    for table in ("ir_module_module_dependency", "ir_module_module_exclusion"):
        cr.execute(
            SQL(
                """
                DELETE FROM %(table)s stale
                      WHERE stale.name = %(old)s
                        AND EXISTS (SELECT 1 FROM %(table)s kept
                                     WHERE kept.module_id = stale.module_id
                                       AND kept.name = %(new)s)
                """,
                table=SQL.identifier(table),
                old=old,
                new=new,
            )
        )
        cr.execute(
            SQL(
                "UPDATE %s SET name = %s WHERE name = %s",
                SQL.identifier(table),
                new,
                old,
            )
        )
    moved = _rename_module_xmlids(cr, old, new)
    cr.execute(
        SQL(
            """
            UPDATE ir_config_parameter
               SET key = %(new)s || substring(key from %(tail)s)
             WHERE key LIKE %(like)s
               AND NOT EXISTS (
                   SELECT 1 FROM ir_config_parameter existing
                    WHERE existing.key = %(new)s || substring(ir_config_parameter.key from %(tail)s)
               )
            """,
            new=f"{new}.",
            tail=len(old) + 2,
            like=_like_prefix(f"{old}."),
        )
    )
    _rename_module_references(cr, rename)
    cr.execute(
        SQL(
            "UPDATE ir_ui_view SET key = %s || substring(key from %s) WHERE key LIKE %s",
            f"{new}.",
            len(old) + 2,
            _like_prefix(f"{old}."),
        )
    )
    for table, column in (
        ("ir_asset", "path"),
        ("ir_asset", "target"),
        ("ir_ui_view", "arch_fs"),
    ):
        if column_exists(cr, table, column):
            cr.execute(
                SQL(
                    "UPDATE %s SET %s = regexp_replace(%s, %s, %s) WHERE %s ~ %s",
                    SQL.identifier(table),
                    SQL.identifier(column),
                    SQL.identifier(column),
                    f"^(/?){old}/",
                    rf"\1{new}/",
                    SQL.identifier(column),
                    f"^/?{old}/",
                )
            )
    if column_exists(cr, "ir_asset", "bundle"):
        cr.execute(
            SQL(
                "UPDATE ir_asset SET bundle = %s || substring(bundle from %s) "
                "WHERE bundle LIKE %s",
                f"{new}.",
                len(old) + 2,
                _like_prefix(f"{old}."),
            )
        )
    _debug.lifecycle("module_data.module_renamed", old=old, new=new, xmlids=moved)
    _logger.info("renamed module %s to %s with %s xml id(s)", old, new, moved)
    return True


def fold_module(cr: BaseCursor, folded: str, into: str) -> None:
    """Merge module ``folded`` into ``into``: a rename when ``into`` is not
    installed, otherwise ``folded``'s external ids, dependencies and module row
    move onto ``into``. Records both modules declare under the same name must be
    the same record; a name each module gives a different record raises."""
    cr.execute(
        SQL(
            "SELECT name, state FROM ir_module_module WHERE name = ANY(%s)",
            [folded, into],
        )
    )
    states = dict(cr.fetchall())
    if folded not in states:
        return
    if states.get(into, "uninstalled") == "uninstalled":
        rename_module(cr, folded, into)
        return
    cr.execute(
        SQL(
            """
            DELETE FROM ir_model_data d
             USING ir_model_data o
             WHERE d.module = %s AND o.module = %s AND o.name = d.name
               AND o.model = d.model AND o.res_id = d.res_id
            """,
            folded,
            into,
        )
    )
    cr.execute(
        SQL(
            """
            SELECT d.name FROM ir_model_data d
             WHERE d.module = %s
               AND EXISTS (SELECT 1 FROM ir_model_data o
                            WHERE o.module = %s AND o.name = d.name)
            """,
            folded,
            into,
        )
    )
    if clashing := sorted(name for (name,) in cr.fetchall()):
        raise ValueError(f"{folded} and {into} both own {clashing}")
    cr.execute(
        SQL("UPDATE ir_model_data SET module = %s WHERE module = %s", into, folded)
    )
    cr.execute(
        SQL(
            """
            DELETE FROM ir_module_module_dependency d
                  WHERE d.name = %(folded)s
                    AND EXISTS (SELECT 1 FROM ir_module_module_dependency o
                                 WHERE o.module_id = d.module_id
                                   AND o.name = %(into)s)
            """,
            folded=folded,
            into=into,
        )
    )
    cr.execute(
        SQL(
            "UPDATE ir_module_module_dependency SET name = %s WHERE name = %s",
            into,
            folded,
        )
    )
    retire_empty_module(cr, folded)


def _drop_uninstalled_placeholder(cr: BaseCursor, old: str, new: str) -> None:
    cr.execute(SQL("SELECT id, state FROM ir_module_module WHERE name = %s", new))
    if not (row := cr.fetchone()):
        return
    module_id, state = row
    if state != "uninstalled":
        raise ValueError(
            f"{old} and {new} are both present and {new} is {state}; "
            f"uninstall {new}, then upgrade base again"
        )
    cr.execute(
        SQL(
            "DELETE FROM ir_model_data WHERE module = 'base' "
            "AND model = 'ir.module.module' AND res_id = %s",
            module_id,
        )
    )
    for table in ("ir_module_module_dependency", "ir_module_module_exclusion"):
        cr.execute(
            SQL("DELETE FROM %s WHERE module_id = %s", SQL.identifier(table), module_id)
        )
    cr.execute(SQL("DELETE FROM ir_module_module WHERE id = %s", module_id))
    _logger.info("dropped the uninstalled %s placeholder", new)


def _rename_module_xmlids(cr: BaseCursor, old: str, new: str) -> int:
    cr.execute(
        SQL(
            """
            SELECT d.name FROM ir_model_data d
             WHERE d.module = %s
               AND EXISTS (SELECT 1 FROM ir_model_data o
                            WHERE o.module = %s AND o.name = d.name)
            """,
            old,
            new,
        )
    )
    if clashing := sorted(name for (name,) in cr.fetchall()):
        raise ValueError(f"{old} and {new} both own {clashing}")
    cr.execute(SQL("UPDATE ir_model_data SET module = %s WHERE module = %s", new, old))
    moved = cr.rowcount
    cr.execute(
        SQL(
            "UPDATE ir_model_data SET name = %s "
            "WHERE module = 'base' AND model = 'ir.module.module' AND name = %s",
            f"module_{new}",
            f"module_{old}",
        )
    )
    return moved


def _module_names(cr: BaseCursor, module: str) -> tuple[set[str], set[str]]:
    # what `module.` opens as stored data knows it: the module's xml ids and its
    # config-parameter keys, and the model names it opens, which it must not touch
    prefix = f"{module}."
    cr.execute(SQL("SELECT name FROM ir_model_data WHERE module = %s", module))
    names = {name for (name,) in cr.fetchall()}
    for table, column in (("ir_config_parameter", "key"), ("ir_model", "model")):
        if not table_exists(cr, table):
            continue
        cr.execute(
            SQL(
                "SELECT %s FROM %s WHERE %s LIKE %s",
                SQL.identifier(column),
                SQL.identifier(table),
                SQL.identifier(column),
                _like_prefix(prefix),
            )
        )
        found = {value[len(prefix) :] for (value,) in cr.fetchall()}
        if table == "ir_model":
            return names, found
        names |= found
    return names, set()


_XMLID_CALL = (
    r"\b(?:ref|_xmlid_to_res_id|_xmlid_to_res_model_res_id|_xmlid_lookup)\(\s*"
)
_XMLID_ATTRIBUTES = frozenset({"t-call", "t-call-assets", "t-snippet"})


class _ModuleRename:
    # A module's name as it stands in stored data: the prefix of an xml id in
    # the positions that hold one, and of a quoted name the module owns (an xml
    # id, a config-parameter key), never of a model name, since `iot.` also opens
    # model names (`env['iot.box']`) that no module rename touches.
    def __init__(
        self,
        old: str,
        new: str,
        names: Iterable[str] = (),
        models: Iterable[str] = (),
    ) -> None:
        self.old = old
        self.new = new
        self.names = frozenset(names) - frozenset(models)
        module = re.escape(old)
        self.text = re.compile(
            rf"(?P<lead>{_XMLID_CALL}['\"]|%\(|\bt-call(?:-assets)?\s*=\s*['\"])"
            rf"{module}\.(?=\w)"
        )
        self.quoted = re.compile(
            rf"(?P<lead>['\"]|\baction-){module}\.(?P<name>[\w.-]+)(?=(?P<end>['\"/?#&\s]|$))"
        )
        self.whole = re.compile(rf"\s*{module}\.(?P<name>[\w.-]+)\s*")
        self.lead = re.compile(rf"^(?P<lead>\s*){module}\.(?=\w)")
        self.items = re.compile(rf"(?P<lead>(?:^|,)\s*!?\s*){module}\.(?=\w)")
        self.action = re.compile(rf"{module}\.\w[\w.]*")

    def in_text(self, value: str) -> str:
        value = self.text.sub(lambda m: f"{m['lead']}{self.new}.", value)
        return self.quoted.sub(self._quoted, value)

    def _quoted(self, match: re.Match[str]) -> str:
        lead, name = match["lead"], match["name"]
        # a quoted name must close where it ends; a URL's `action-` need not
        if (lead in ("'", '"') and match["end"] != lead) or name not in self.names:
            return match[0]
        return f"{lead}{self.new}.{name}"

    def in_attribute(self, element: etree._Element, attribute: str, value: str) -> str:
        if attribute == "groups":
            return self.items.sub(lambda m: f"{m['lead']}{self.new}.", value)
        if attribute in _XMLID_ATTRIBUTES:
            return self.lead.sub(lambda m: f"{m['lead']}{self.new}.", value)
        if attribute == "t-install":
            return self.new if value.strip() == self.old else value
        if (
            element.tag == "button"
            and attribute == "name"
            and element.get("type") == "action"
            and self.action.fullmatch(value)
        ):
            return f"{self.new}{value[len(self.old) :]}"
        # an attribute whose whole value is an xml id of the module (a kanban's
        # on_create, a widget's action)
        if (whole := self.whole.fullmatch(value)) and whole["name"] in self.names:
            return value.replace(f"{self.old}.", f"{self.new}.", 1)
        return self.in_text(value)

    def in_arch(self, value: str) -> str:
        if not value or self.old not in value:
            return value
        try:
            root = etree.fromstring(value.encode())
        except etree.XMLSyntaxError:
            _debug.logic("module_data.arch_unparsed", old=self.old, model=None)
            return value
        renamed = False
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            for attribute, text in element.attrib.items():
                target = attribute
                if element.tag == "attribute" and attribute in ("add", "remove"):
                    target = element.get("name") or ""
                rewritten = self.in_attribute(element, target, text)
                if rewritten != text:
                    element.set(attribute, rewritten)
                    renamed = True
            if element.tag == "attribute" and element.text:
                rewritten = self.in_attribute(
                    element, element.get("name") or "", element.text
                )
                if rewritten != element.text:
                    element.text = rewritten
                    renamed = True
        return etree.tostring(root, encoding="unicode") if renamed else value


def _rename_module_references(cr: BaseCursor, rename: _ModuleRename) -> int:
    old, new = rename.old, rename.new
    needle = f"{old}."
    rewritten = _rewrite_view_arches(
        cr,
        SQL("position(%s in arch_db::text) > 0", old),
        lambda value, _view_model: rename.in_arch(value),
    )
    tables = set(
        get_tables_existing(cr, [source.table for source in _EXPRESSION_SOURCES])
    )
    for source in _EXPRESSION_SOURCES:
        if source.table not in tables:
            continue
        columns = _existing_columns(cr, source.table, source.columns)
        if not columns:
            continue
        cr.execute(
            SQL(
                "SELECT id, %s FROM %s WHERE %s",
                SQL(", ").join(SQL.identifier(column) for column in columns),
                SQL.identifier(source.table),
                SQL(" OR ").join(
                    SQL("position(%s in %s::text) > 0", needle, SQL.identifier(column))
                    for column in columns
                ),
            )
        )
        for row_id, *values in cr.fetchall():
            changes = {}
            for column, value in zip(columns, values, strict=True):
                if isinstance(value, dict):
                    renamed_texts = {
                        lang: rename.in_text(text) if text else text
                        for lang, text in value.items()
                    }
                    if renamed_texts != value:
                        changes[column] = Json(renamed_texts)
                elif value and (renamed := rename.in_text(value)) != value:
                    changes[column] = renamed
            if not changes:
                continue
            cr.execute(
                SQL(
                    "UPDATE %s SET %s WHERE id = %s",
                    SQL.identifier(source.table),
                    SQL(", ").join(
                        SQL("%s = %s", SQL.identifier(column), value)
                        for column, value in changes.items()
                    ),
                    row_id,
                )
            )
            rewritten += 1
    _debug.perf.count(
        "module_data.module_references_rewritten", old=old, new=new, rows=rewritten
    )
    return rewritten


class _Source(NamedTuple):
    table: str
    columns: tuple[str, ...]


# where stored data spells a module's xml ids as text
_EXPRESSION_SOURCES = (
    _Source(
        "mail_template",
        (
            "body_html",
            "subject",
            "email_from",
            "email_to",
            "email_cc",
            "partner_to",
            "reply_to",
            "scheduled_date",
        ),
    ),
    _Source("ir_act_server", ("code",)),
    _Source("ir_filters", ("domain", "context", "sort")),
    _Source("ir_act_window", ("domain", "context")),
    _Source("ir_rule", ("domain_force",)),
    _Source("ir_access", ("domain",)),
    _Source("base_automation", ("filter_domain", "filter_pre_domain")),
    _Source("automation_rule", ("filter_domain", "filter_pre_domain")),
    _Source("ir_embedded_actions", ("domain", "context", "python_method")),
)


def _existing_columns(cr: BaseCursor, table: str, columns: Iterable[str]) -> list[str]:
    return [column for column in columns if column_exists(cr, table, column)]


def _rewrite_view_arches(
    cr: BaseCursor, condition: SQL, rewrite: Callable[[str, Any], str]
) -> int:
    if not table_exists(cr, "ir_ui_view"):
        return 0
    cr.execute(SQL("SELECT id, model, arch_db FROM ir_ui_view WHERE %s", condition))
    rewritten = 0
    for view_id, view_model, arch in cr.fetchall():
        translations = {
            lang: rewrite(value, view_model) for lang, value in (arch or {}).items()
        }
        if translations == (arch or {}):
            continue
        cr.execute(
            SQL(
                "UPDATE ir_ui_view SET arch_db = %s WHERE id = %s",
                Json(translations),
                view_id,
            )
        )
        rewritten += 1
    return rewritten


def drop_views(cr: BaseCursor, module: str, names: Iterable[str]) -> int:
    """Delete the views ``module`` shipped under ``names``, with every view
    inheriting them: a view naming a field its module no longer defines fails
    validation the moment its model's views load, long before the end of the
    upgrade would have removed it. A descendant another module still ships is
    recreated when that module loads."""
    cr.execute(
        SQL(
            """
            WITH RECURSIVE doomed(id) AS (
                SELECT res_id FROM ir_model_data
                 WHERE module = %s AND model = 'ir.ui.view' AND name = ANY(%s)
                UNION
                SELECT view.id FROM ir_ui_view AS view
                  JOIN doomed ON view.inherit_id = doomed.id
            )
            SELECT id FROM doomed
            """,
            module,
            list(names),
        )
    )
    view_ids = [view_id for (view_id,) in cr.fetchall()]
    if not view_ids:
        return 0
    cr.execute(
        SQL(
            "DELETE FROM ir_model_data WHERE model = 'ir.ui.view' AND res_id = ANY(%s)",
            view_ids,
        )
    )
    cr.execute(SQL("DELETE FROM ir_ui_view WHERE id = ANY(%s)", view_ids))
    _logger.info(
        "dropped %d view(s) of %s that no longer validate", len(view_ids), module
    )
    return len(view_ids)
