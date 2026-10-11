import json
import logging
import re
import typing
from decimal import Decimal, InvalidOperation

from odoo.db import schema as sql
from odoo.libs.debug_log import DebugLog
from odoo.libs.sql import SQL

if typing.TYPE_CHECKING:
    from .._typing import BaseModel, ModelLike
    from .base import Field
    from .relational import Many2many, Many2one
    from .textual import BaseString, Char

_logger = logging.getLogger("odoo.fields")
_debug = DebugLog(__name__)
_schema = logging.getLogger("odoo.schema")


def get_column_order(udt_name: str) -> int:
    return sql.SQL_ORDER_BY_TYPE[udt_name]


def update_db(
    field: Field[typing.Any],
    model: ModelLike,
    columns: dict[str, dict[str, typing.Any]],
) -> bool:
    if not field.column_type:
        return False

    column = columns.get(field.name) or {}

    field.update_db_column(model, column)
    field.update_db_notnull(model, column)

    if (
        not column
        and field.related
        and field.related.count(".") == 1
        and field.related_field.store
        and not field.related_field.compute
        and not field.related_field.is_attachment_backed
        and not field.related_field.is_x2many
        and not field.related_field.company_dependent
        and _is_column_copyable(field.related_field, field)
    ):
        join_field = model._fields[field._related_names[0]]
        if join_field.is_many2one and join_field.store and not join_field.compute:
            _debug.logic(
                "field.ddl.related_column_filled_by_join",
                model=model._name,
                field=field.name,
                related=field.related,
            )
            model.pool.post_init(field.update_db_related, model)
            return False

    return not column


def _is_column_copyable(source: Field[typing.Any], target: Field[typing.Any]) -> bool:
    if source.column_type is None or target.column_type is None:
        return False
    if source.column_type[0] != target.column_type[0]:
        return False
    if source.column_type[0] != "varchar":
        return True
    source_size = getattr(source, "size", None)
    target_size = getattr(target, "size", None)
    return target_size is None or (
        source_size is not None and source_size <= target_size
    )


def update_db_column(
    field: Field[typing.Any], model: ModelLike, column: dict[str, typing.Any]
) -> None:
    column_type = field.column_type
    if column_type is None:
        raise TypeError(f"{field} has no column: update_db_column does not apply")
    if not column:
        sql.create_column(
            model.env.cr,
            model._table,
            field.name,
            column_type[1],
            field.string,
        )
        return
    if column["udt_name"] == column_type[0]:
        return
    _debug.logic(
        "field.ddl.column_converted",
        model=model._name,
        field=field.name,
        from_type=column["udt_name"],
        to_type=column_type[0],
    )
    field._convert_db_column(model, column)


def convert_db_column(
    field: Field[typing.Any], model: ModelLike, column: dict[str, typing.Any]
) -> None:
    column_type = field.column_type
    if column_type is None:
        raise TypeError(f"{field} has no column: _convert_db_column does not apply")
    if field.company_dependent:
        _enter_company_dependent(field, model, column)
    elif column["udt_name"] == "jsonb":
        _leave_company_dependent(field, model, keep_translation=False)
    else:
        sql.convert_column(model.env.cr, model._table, field.name, column_type[1])


def _get_company_ids(model: ModelLike) -> list[int]:
    companies = model.env.company.browse().sudo().with_context(active_test=False)
    return list(companies.search([], order="id").ids)


def _enter_company_dependent(
    field: Field[typing.Any], model: ModelLike, column: dict[str, typing.Any]
) -> None:
    company_ids = _get_company_ids(model)
    _debug.logic(
        "field.ddl.company_dependent_entered",
        model=model._name,
        field=field.name,
        from_type=column["udt_name"],
        companies=len(company_ids),
    )
    sql.convert_column_to_company_dependent(
        model.env.cr,
        model._table,
        field.name,
        company_ids,
        value_format=(
            "YYYY-MM-DD HH24:MI:SS"
            if column["udt_name"].startswith("timestamp")
            else None
        ),
    )


def _get_main_company_id(model: ModelLike) -> int | None:
    main = model.env.ref("base.main_company", raise_if_not_found=False)
    if main is not None and main._name == "res.company":
        return typing.cast("int", main.id)
    company_ids = _get_company_ids(model)
    return company_ids[0] if company_ids else None


def _leave_company_dependent(
    field: Field[typing.Any], model: ModelLike, *, keep_translation: bool
) -> None:
    column_type = field.column_type
    assert column_type is not None
    company_id = _get_main_company_id(model)
    if company_id is None:
        raise ValueError(
            f"{field} is no longer company-dependent, but no company exists to "
            f"choose the value its column keeps"
        )
    fallback_json = None
    defaults = model.env.registry.get("ir.default")
    if defaults is not None and not defaults._abstract:
        fallback = field._get_company_dependent_fallback_raw(
            model.with_company(company_id)
        )
        if fallback is not None and fallback is not False:
            fallback_json = json.dumps(
                field._to_json_value(
                    field.convert_to_column(fallback, model, validate=False)
                ),
                default=str,
            )
    _debug.logic(
        "field.ddl.company_dependent_left",
        model=model._name,
        field=field.name,
        to_type=column_type[0],
        company=company_id,
        fallback=fallback_json is not None,
        keep_translation=keep_translation,
    )
    sql.convert_column_from_company_dependent(
        model.env.cr,
        model._table,
        field.name,
        column_type[1],
        company_id,
        fallback_json=fallback_json,
        keep_translation=keep_translation,
    )


def convert_db_column_translatable(
    field: BaseString, model: ModelLike, column: dict[str, typing.Any]
) -> None:
    assert field.column_type is not None, (
        f"{field}: a column conversion is only reached for a stored column"
    )
    _debug.logic(
        "field.ddl.column_converted_translatable",
        model=model._name,
        field=field.name,
        from_type=column["udt_name"],
        translate=bool(field.translate),
    )
    if field.company_dependent:
        _enter_company_dependent(field, model, column)
    elif field.translate:
        sql.convert_column_translatable(
            model.env.cr, model._table, field.name, field.column_type[1]
        )
    elif column["udt_name"] == "jsonb":
        _leave_company_dependent(field, model, keep_translation=True)
    else:
        sql.convert_column(model.env.cr, model._table, field.name, field.column_type[1])


def widen_varchar_column(
    field: Char, model: ModelLike, column: dict[str, typing.Any]
) -> None:
    column_type = field.column_type
    if (
        column
        and column_type is not None
        and column_type[0] == "varchar"
        and column["udt_name"] == "varchar"
        and column["character_maximum_length"]
        and (field.size is None or column["character_maximum_length"] < field.size)
    ):
        _debug.logic(
            "field.ddl.varchar_widened",
            model=model._name,
            field=field.name,
            from_size=column["character_maximum_length"],
            to_size=field.size,
        )
        sql.convert_column(model.env.cr, model._table, field.name, column_type[1])


def update_db_notnull(
    field: Field[typing.Any], model: ModelLike, column: dict[str, typing.Any]
) -> None:
    has_notnull = column and column["is_nullable"] == "NO"

    if not column or (field.required and not has_notnull):
        if model._has_rows_in_table():
            _debug.pipeline(
                "field.ddl.init_column",
                model=model._name,
                field=field.name,
                new_column=not column,
            )
            model._init_column(field.name, new_column=not column)

    if field.required and not has_notnull:
        _debug.logic(
            "field.ddl.not_null_scheduled",
            model=model._name,
            field=field.name,
            new_column=not column,
            computed=bool(field.compute),
        )

        @model.pool.post_init
        def add_not_null() -> None:
            current = model._fields[field.name]
            if not current.required or not current.store:
                return
            if current.compute:
                records = model.browse(
                    id_
                    for (id_,) in model.env.execute_query(
                        SQL(
                            "SELECT id FROM %s AS t WHERE %s IS NULL",
                            SQL.identifier(model._table),
                            model._field_to_sql("t", current.name),
                        )
                    )
                )
                model.env.add_to_compute(current, records)
            model.flush_model([current.name])

            def apply_not_null(cr: typing.Any) -> None:
                sql.set_not_null(cr, model._table, current.name)

            model.pool.post_constraint(
                model.env.cr,
                apply_not_null,
                key=f"add_not_null:{model._table}:{current.name}",
            )
            reconcile_sql_default(current, model)

    elif field.required:
        reconcile_sql_default(field, model)

    elif has_notnull:
        _debug.logic("field.ddl.not_null_dropped", model=model._name, field=field.name)
        sql.drop_not_null(model.env.cr, model._table, field.name)
        reconcile_sql_default(field, model)


def get_wanted_sql_default(field: Field[typing.Any], model: ModelLike) -> typing.Any:
    value = field.default_literal
    if (
        field.required
        and value is not None
        and isinstance(value, (str, int, float, bool))
        and not field.translate
        and not field.company_dependent
    ):
        return field.convert_to_column(value, model, validate=False)
    return None


_SQL_DEFAULT_CAST = re.compile(
    r"(.*)::[a-z][a-z0-9_ ]*(?:\(\d+(?:,\s*\d+)?\))?", re.DOTALL
)


def _get_sql_default_text(expression: str) -> str:
    text = expression.strip()
    while match := _SQL_DEFAULT_CAST.fullmatch(text):
        text = match.group(1).strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    if len(text) >= 2 and text[0] == text[-1] == "'":
        text = text[1:-1].replace("''", "'")
    return text


def is_sql_default_equal(expression: str | None, wanted: typing.Any) -> bool:
    if expression is None or wanted is None:
        return expression is None and wanted is None
    text = _get_sql_default_text(expression)
    if isinstance(wanted, bool):
        return text == ("true" if wanted else "false")
    if isinstance(wanted, (int, float, Decimal)):
        try:
            return Decimal(text) == Decimal(
                repr(wanted) if isinstance(wanted, float) else wanted
            )
        except InvalidOperation:
            return False
    return text == str(wanted)


def reconcile_sql_default(field: Field[typing.Any], model: ModelLike) -> None:
    wanted = get_wanted_sql_default(field, model)
    current = sql.get_column_default(model.env.cr, model._table, field.name)
    if is_sql_default_equal(current, wanted):
        return
    _debug.logic(
        "field.ddl.sql_default",
        model=model._name,
        field=field.name,
        had_default=current is not None,
        applied=wanted is not None,
    )

    def apply_default(cr: typing.Any) -> None:
        if wanted is None:
            sql.drop_default(cr, model._table, field.name)
        else:
            sql.set_default(cr, model._table, field.name, wanted)

    model.pool.post_constraint(
        model.env.cr,
        apply_default,
        key=f"set_default:{model._table}:{field.name}",
    )


def update_db_related(field: Field[typing.Any], model: ModelLike) -> None:
    comodel = model.env[field.related_field.model_name]
    join_field, comodel_field = field._related_names
    with _debug.perf(
        "field.ddl.related_column_filled",
        cr=model.env.cr,
        model=model._name,
        field=field.name,
        comodel=comodel._name,
    ) as span:
        model.env.cr.execute(
            SQL(
                """ UPDATE %(model_table)s AS x
                SET %(model_field)s = y.%(comodel_field)s
                FROM %(comodel_table)s AS y
                WHERE x.%(join_field)s = y.id """,
                model_table=SQL.identifier(model._table),
                model_field=SQL.identifier(field.name),
                comodel_table=SQL.identifier(comodel._table),
                comodel_field=SQL.identifier(comodel_field),
                join_field=SQL.identifier(join_field),
            )
        )
        span.set(rows=model.env.cr.rowcount)


def update_db_foreign_key(
    field: Many2one, model: BaseModel, column: dict[str, typing.Any]
) -> None:
    if field.company_dependent:
        return
    comodel = model.env[field.comodel_name]
    if not model._is_an_ordinary_table() or not comodel._is_an_ordinary_table():
        _debug.logic(
            "field.ddl.foreign_key_skipped",
            model=model._name,
            field=field.name,
            reason="not_ordinary_table",
        )
        return
    if not comodel._auto or comodel._is_table_inheritance_root():
        _debug.logic(
            "field.ddl.foreign_key_skipped",
            model=model._name,
            field=field.name,
            reason="comodel_not_auto" if not comodel._auto else "inheritance_root",
        )
        return
    model.pool.add_foreign_key(
        model._table,
        field.name,
        comodel._table,
        "id",
        field.ondelete or "set null",
        model,
        field._module,
    )


def update_db_relation_table(field: Many2many, model: ModelLike) -> bool:
    cr = model.env.cr
    relation, column1, column2 = field._get_relation_triple()
    if not model.pool.register_relation_table(
        model._name, relation, field._module, reflect=not field.manual
    ):
        return False
    comodel = model.env[field.comodel_name]
    if not sql.table_exists(cr, relation):
        cr.execute(
            SQL(
                """ CREATE TABLE %(rel)s (%(id1)s INTEGER NOT NULL,
                                      %(id2)s INTEGER NOT NULL,
                                      PRIMARY KEY(%(id1)s, %(id2)s));
                COMMENT ON TABLE %(rel)s IS %(comment)s;
                CREATE INDEX ON %(rel)s (%(id2)s, %(id1)s); """,
                rel=SQL.identifier(relation),
                id1=SQL.identifier(column1),
                id2=SQL.identifier(column2),
                comment=f"RELATION BETWEEN {model._table} AND {comodel._table}",
            )
        )
        _schema.debug(
            "Create table %r: m2m relation between %r and %r",
            relation,
            model._table,
            comodel._table,
        )
        _debug.lifecycle(
            "field.ddl.relation_table_created",
            model=model._name,
            field=field.name,
            relation=relation,
        )
        model.pool.post_init(field.update_db_foreign_keys, model)
        return True

    model.pool.post_init(field.update_db_foreign_keys, model)
    return False


def _relation_is_shared_with_tree(field: Many2many, model: BaseModel) -> bool:
    if not model._table_inheritance_root:
        return False
    if model._is_table_inheritance_root():
        return True
    root = model.env[model._get_root_model_name()]
    root_field = root._fields.get(field.name)
    return root_field is not None and root_field.relation == field.relation


def update_db_foreign_keys(field: Many2many, model: BaseModel) -> None:
    comodel = model.env[field.comodel_name]
    relation, column1, column2 = field._get_relation_triple()
    model_side = model._is_an_ordinary_table() and not _relation_is_shared_with_tree(
        field, model
    )
    _debug.pipeline(
        "field.ddl.m2m_foreign_keys",
        model=model._name,
        field=field.name,
        relation=relation,
        model_side=model_side,
        comodel_side=comodel._is_an_ordinary_table()
        and not comodel._is_table_inheritance_root(),
        ondelete=field.ondelete or "cascade",
    )
    if model_side:
        model.pool.add_foreign_key(
            relation,
            column1,
            model._table,
            "id",
            "cascade",
            model,
            field._module,
            force=False,
        )
    if comodel._is_an_ordinary_table() and not comodel._is_table_inheritance_root():
        model.pool.add_foreign_key(
            relation,
            column2,
            comodel._table,
            "id",
            field.ondelete or "cascade",
            model,
            field._module,
        )
