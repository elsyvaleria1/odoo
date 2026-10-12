import ast
import logging
from collections.abc import Iterable
from datetime import date, datetime

import psycopg
import psycopg.errors

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.models import MAGIC_COLUMNS
from odoo.tools import SQL, get_lang
from odoo.tools.misc import format_date, format_datetime, unique
from odoo.tools.misc import partition as tools_partition

_logger = logging.getLogger(__name__)


class Data_MergeRecord(models.Model):
    _name = "data_merge.record"
    _description = "Deduplication Record"
    _order = "res_id desc"

    active = fields.Boolean(
        compute="_compute_active",
        store=True,
    )
    group_id = fields.Many2one(
        comodel_name="data_merge.group",
        string="Record Group",
        index=True,
        required=True,
        ondelete="cascade",
    )
    model_id = fields.Many2one(
        related="group_id.model_id",
        readonly=True,
    )
    res_model_id = fields.Many2one(
        related="group_id.res_model_id",
        readonly=True,
    )
    res_model_name = fields.Char(
        related="group_id.res_model_name",
        readonly=True,
    )
    is_master = fields.Boolean(default=False)
    is_deleted = fields.Boolean(compute="_compute_fields")
    is_discarded = fields.Boolean(default=False)

    name = fields.Char(compute="_compute_fields")
    res_id = fields.Many2oneReference(
        model_field="res_model_name",
        string="Record ID",
        index=True,
        readonly=False,
        aggregator=None,
    )
    record_create_date = fields.Datetime(
        string="Created On",
        compute="_compute_fields",
    )
    record_create_uid = fields.Char(
        string="Created By",
        compute="_compute_fields",
    )
    record_write_date = fields.Datetime(
        string="Updated On",
        compute="_compute_fields",
    )
    record_write_uid = fields.Char(
        string="Updated By",
        compute="_compute_fields",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_fields",
        search="_search_company_id",
    )

    differences = fields.Char(
        compute="_compute_differences",
        store=True,
        help="Differences with the master record",
    )
    field_values = fields.Char(compute="_compute_field_values")
    used_in = fields.Char(
        compute="_compute_usage",
        store=True,
        help="List of other models referencing this record",
    )

    def _search_company_id(self, operator, value):
        if operator not in ("in", "ilike", "like", "any"):
            raise NotImplementedError

        cr = self.env.cr
        self.env["data_merge.model"].flush_model()
        self.env["data_merge.group"].flush_model(["model_id"])
        restrict_model_ids = self.env.context.get("data_merge_model_ids")
        if restrict_model_ids:
            cr.execute(
                """
                SELECT im.model,
                       m.res_model_id
                  FROM data_merge_model m
                  JOIN ir_model im ON im.id = m.res_model_id
                 WHERE m.id = ANY(%s)
                """,
                [list(restrict_model_ids)],
            )
        else:
            cr.execute(
                """
                SELECT im.model,
                       m.res_model_id
                  FROM data_merge_model m
                  JOIN ir_model im ON im.id = m.res_model_id
                 WHERE m.id IN (SELECT g.model_id FROM data_merge_group g)
                """
            )
        models_info = list(unique(r for r in cr.fetchall() if r[0] in self.env))
        if not models_info:
            query = (
                self.env["data_merge.record"]
                .with_context(active_test=False)
                ._search([])
            )
            return Domain("id", "in", query)

        models_with_company, models_no_company = tools_partition(
            lambda r: self.env[r[0]]._fields.get("company_id"),
            models_info,
        )

        false_company_domain_is_true = (
            operator in ("ilike", "like") and not value
        ) or (isinstance(value, Iterable) and (operator == "in" and False in value))

        join_queries = []
        where_queries = []
        if models_no_company and false_company_domain_is_true:
            where_queries.append(
                SQL(
                    "dmm.res_model_id = ANY(%s)",
                    [r[1] for r in models_no_company],
                )
            )
        for model_name, model_id in models_with_company:
            Model = self.env[model_name]
            query = Model.with_context(active_test=False)._search(
                [("company_id", operator, value)]
            )
            from_clause, where_clause = query.from_clause, query.where_clause
            model_table = Model._table
            from_sql_code = from_clause.code
            assert (
                from_sql_code.startswith(f'"{model_table}"') and not from_clause.params
            )
            extra_joins = SQL(from_sql_code[len(f'"{model_table}"') :])

            join_queries.append(
                SQL(
                    """
                LEFT JOIN %s
                ON data_merge_record.res_id = %s.id
                %s
                """,
                    SQL.identifier(model_table),
                    SQL.identifier(model_table),
                    extra_joins,
                )
            )
            where_queries.append(
                SQL(
                    "(%s AND dmm.res_model_id = %s)",
                    where_clause,
                    model_id,
                )
            )
        if not where_queries:
            return Domain.FALSE
        sql = SQL(
            """(
            SELECT data_merge_record.id
            FROM data_merge_record
            JOIN data_merge_group dmg ON dmg.id = data_merge_record.group_id
            JOIN data_merge_model dmm ON dmm.id = dmg.model_id
            %s
            WHERE %s
            )""",
            SQL(" ").join(join_queries),
            SQL(" OR ").join(where_queries),
        )
        return Domain("id", "in", sql)

    def _render_values(self, to_read) -> dict:
        self.check_singleton()

        def format_value(value, env):
            if isinstance(value, tuple):
                return value[1]
            if isinstance(value, datetime):
                return format_datetime(env, value, dt_format="short")
            if isinstance(value, date):
                return format_date(env, value)
            return value

        def ir_field(key):
            return self.env["ir.model.fields"]._get(self.res_model_name, key)

        def field_description(key):
            return ir_field(key)["field_description"]

        model_fields = self.env[self.res_model_name]._fields

        def hidden_field(key):
            return (
                key in MAGIC_COLUMNS
                or key not in model_fields
                or model_fields[key].groups
                or model_fields[key].classification
                or not model_fields[key].export_string_translation
                or ir_field(key)["ttype"] == "binary"
            )

        record = self._original_records()
        if not record:
            return {}

        record_data = record.read(to_read)[0]
        return {
            str(field_description(key)): format_value(value, self.env)
            for key, value in record_data.items()
            if value and not hidden_field(key)
        }

    @api.depends("res_id")
    def _compute_field_values(self) -> None:
        model_fields = {}
        for record in self:
            if record.model_id not in model_fields:
                model_fields[record.model_id] = record.model_id.rule_ids.mapped(
                    "field_id.name"
                )
            to_read = model_fields[record.model_id]

            if not to_read:
                record.field_values = ""
            else:
                record.field_values = ", ".join(
                    list(record._render_values(to_read).values())
                )

    @api.depends("res_id")
    def _compute_differences(self) -> None:
        for record in self:
            if record.group_id.divergent_fields:
                read_fields = record.group_id.divergent_fields.split(",")
                record.differences = ", ".join(
                    [
                        "%s: %s" % (k, v)
                        for k, v in record._render_values(read_fields).items()
                    ]
                )
            else:
                record.differences = ""

    def _get_references(self):
        res_models = list(set(self.mapped("res_model_name")))
        model_fields = dict.fromkeys(res_models, self.env["ir.model.fields"])
        all_fields = (
            self.env["ir.model.fields"]
            .sudo()
            .search(
                [
                    ("store", "=", True),
                    ("ttype", "in", ("one2many", "many2one", "many2many")),
                    ("relation", "in", res_models),
                    ("index", "=", True),
                ]
            )
        )
        for field in all_fields:
            if (
                not isinstance(self.env[field.model], models.BaseModel)
                or not self.env[field.model]._auto
                or self.env[field.model]._transient
            ):
                continue
            model_fields[field.relation] |= field

        model_name = {field.model: field.model_id.name for field in all_fields}

        references = {record.id: [] for record in self}
        records_by_model = self.grouped("res_model_name")
        for res_model_name in res_models:
            records = records_by_model[res_model_name]
            records_mapped = {record.res_id: record.id for record in records}
            reference_fields = model_fields[res_model_name]

            group_model_fields = {field.model: [] for field in reference_fields}
            for field in reference_fields:
                group_model_fields[field.model].append(field.name)

            for model, ref_fields in group_model_fields.items():
                domain = Domain.OR(
                    [[(f, "in", records.mapped("res_id"))] for f in ref_fields]
                )
                groupby_field = ref_fields[0]
                count_grouped = self.env[model]._read_group(
                    domain & Domain(groupby_field, "!=", False),
                    [groupby_field],
                    ["__count"],
                )
                for group_value, count in count_grouped:
                    record_id = records_mapped.get(group_value.id)
                    if not record_id:
                        continue
                    references[record_id].append((count, model_name[model]))
        return references

    @api.depends("res_id")
    def _compute_usage(self) -> None:
        if ast.literal_eval(
            self.env.registry.settings.get(
                self.env, "data_merge.compute_references", "True"
            )
        ):
            references = self._get_references()
            for record in self:
                ref = references[record.id]
                record.used_in = ", ".join(["%s %s" % (r[0], r[1]) for r in ref])
        else:
            self.used_in = ""

    @api.depends("res_model_name", "res_id")
    def _compute_fields(self) -> None:
        groups = self.grouped("res_model_name")
        for res_model_name, records in groups.items():
            if not res_model_name:
                records.is_deleted = False
                records.name = False
                records.company_id = False
                records.record_create_date = False
                records.record_create_uid = False
                records.record_write_date = False
                records.record_write_uid = False
                continue

            existing_records = {r.id: r for r in records._original_records()}
            for record in records:
                original_record = (
                    existing_records.get(record.res_id) or self.env[res_model_name]
                )
                name = original_record.display_name
                record.is_deleted = record.res_id not in existing_records
                record.name = name or "*Record Deleted*"
                record.company_id = (
                    original_record._fields.get("company_id")
                    and original_record.company_id
                )
                record.record_create_date = original_record.create_date
                record.record_create_uid = (
                    original_record.create_uid.name or "*Deleted*"
                )
                record.record_write_date = original_record.write_date
                record.record_write_uid = original_record.write_uid.name or "*Deleted*"

    @api.depends("is_deleted", "is_discarded")
    def _compute_active(self) -> None:
        for record in self:
            record.active = not (record.is_deleted or record.is_discarded)

    def _original_records(self):
        if not self:
            return []

        model_name = set(self.mapped("res_model_name")) or {}

        if len(model_name) != 1:
            raise ValidationError(self.env._("Records must be of the same model"))

        model = model_name.pop()
        ids = self.mapped("res_id")
        return (
            self.env[model].with_context(active_test=False).sudo().browse(ids).exists()
        )

    def _record_snapshot(self):
        self.check_singleton()
        return self._render_values([])

    @api.model
    def _update_foreign_keys(self, destination, source) -> None:
        source_ids = source.ids
        self.env.flush_all()
        self.env["mixin.merge"]._update_foreign_keys_generic(
            destination._name, source, destination
        )

        self._merge_additional_models(destination, source_ids)
        fields_to_recompute = [
            f.name for f in destination._fields.values() if f.compute and f.store
        ]
        destination.modified(fields_to_recompute)
        self.env.flush_all()
        self.env.invalidate_all()

    @api.model
    def _merge_additional_models(self, destination, source_ids) -> None:
        if hasattr(destination, "message_follower_ids"):
            self._merge_mail_followers(
                destination, self.env[destination._name].browse(source_ids)
            )
        models_to_adapt = [
            {
                "table": "ir_attachment",
                "id_field": "res_id",
                "model_field": "res_model",
            },
            {
                "table": "mail_activity",
                "id_field": "res_id",
                "model_field": "res_model",
            },
            {
                "table": "ir_model_data",
                "id_field": "res_id",
                "model_field": "model",
            },
            {
                "table": "mail_message",
                "id_field": "res_id",
                "model_field": "model",
            },
        ]
        query = """
            UPDATE %(table)s
            SET %(id_field)s = %%(destination_id)s
            WHERE %(id_field)s = %%(record_id)s
            AND %(model_field)s = %%(model)s"""
        for model in models_to_adapt:
            q = query % model
            for rec_id in source_ids:
                try:
                    with self.env.cr.savepoint():
                        params = {
                            "destination_id": destination.id,
                            "record_id": rec_id,
                            "model": destination._name,
                        }
                        self.env.cr.execute(q, params)
                except psycopg.errors.UniqueViolation:
                    _logger.warning(
                        "Query %s failed, due to an unique constraint", query
                    )
                except psycopg.IntegrityError:
                    _logger.warning("Query %s failed", query)
                except psycopg.Error as error:
                    raise ValidationError(self.env._("Query Failed.")) from error

        with self.env.cr.savepoint():
            for fname, field in destination._fields.items():
                if field.company_dependent:
                    self.env.cr.execute(
                        SQL(
                            """
                        UPDATE %(table)s
                        SET %(col)s = NULLIF(
                            (
                                SELECT jsonb_object_agg(key, value)
                                FROM %(table)s, jsonb_each(%(col)s)
                                WHERE id IN %(source_ids)s
                            ) || COALESCE(%(col)s, '{}'::jsonb),
                            '{}'::jsonb
                        )
                        WHERE id = %(destination_id)s
                        """,
                            table=SQL.identifier(destination._table),
                            col=SQL.identifier(fname),
                            destination_id=destination.id,
                            source_ids=tuple(source_ids),
                        )
                    )

    def _merge_mail_followers(self, destination, source) -> None:
        dest_followers = destination.message_follower_ids.partner_id
        new_followers = source.message_follower_ids.partner_id - dest_followers
        destination.message_subscribe(new_followers.ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            group = self.env["data_merge.group"].browse(vals["group_id"])
            if "res_id" not in vals:
                raise ValidationError(self.env._("There is not referenced record"))
            record = self.env[group.res_model_name].browse(vals["res_id"])

            if not record.exists():
                raise ValidationError(
                    self.env._("The referenced record does not exist")
                )
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("is_master"):
            master = self.with_context(active_test=False).group_id.record_ids.filtered(
                "is_master"
            )
            master.write({"is_master": False})

        return super().write(vals)

    def open_record(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": self.res_model_name,
            "res_id": self.res_id,
            "context": {"create": False, "edit": False},
        }

    def action_deduplicates(self, records):
        MergeRecord = self.env["data_merge.record"]
        MergeModel = self.env["data_merge.model"]
        MergeGroup = self.env["data_merge.group"]

        active_ids = records.ids
        active_model = records._name

        if len(active_ids) < 2:
            translated_desc = records.with_context(
                lang=get_lang(self.env).code
            )._description
            raise UserError(
                self.env._(
                    "You must select at least two %s in order to merge them.",
                    translated_desc,
                )
            )
        if active_model not in self.env:
            raise ValidationError(self.env._("The target model does not exists."))

        view = self.env.ref("data_cleaning.data_merge_record_view_search_merge_action")
        action = {
            "name": self.env._("Deduplicate"),
            "view_mode": "list",
            "res_model": "data_merge.record",
            "type": "ir.actions.act_window",
            "search_view_id": [view.id, "search"],
            "domain": [
                ("res_id", "in", active_ids),
                ("res_model_name", "=", active_model),
            ],
            "context": {"group_by": ["group_id"]},
            "help": '<p class="o_view_nocontent_smiling_face">%s</p>'
            % self.env._("No duplicates found"),
        }

        merge_model = MergeModel.with_context(active_test=False).search(
            [
                ("res_model_name", "=", active_model),
                ("is_contextual_merge_action", "=", True),
            ]
        )
        if not merge_model:
            model_name = (
                self.env["ir.model"]
                ._get(active_model)
                .with_context(lang=self.env.user.lang)
                .display_name
            )
            merge_model = MergeModel.create(
                {
                    "name": self.env._("Manual Selection - %s", model_name),
                    "res_model_id": self.env["ir.model"]._get(active_model).id,
                    "active": False,
                    "is_contextual_merge_action": True,
                }
            )

        merge_group = MergeGroup.create({"model_id": merge_model.id})

        results = MergeRecord.search_read(
            [("res_id", "in", active_ids), ("res_model_name", "=", active_model)],
            fields=["res_id"],
        )
        existing_records = {result["res_id"]: result["id"] for result in results}

        records_to_create = []
        records_to_update = []
        for record in records:
            if record.id not in existing_records:
                records_to_create.append(
                    {
                        "res_id": record.id,
                        "model_id": merge_model.id,
                        "group_id": merge_group.id,
                    }
                )
            else:
                records_to_update.append(existing_records[record.id])

        MergeRecord.browse(records_to_update).write(
            {"group_id": merge_group.id, "is_master": False}
        )
        MergeRecord.create(records_to_create)

        return action
