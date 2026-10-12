import ast
import datetime
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import SQL, OrderedSet

from odoo.addons.ai.utils.llm_api_service import LLMApiService

_logger = logging.getLogger(__name__)

NB_RECORDS_TO_COMPUTE_ON_FIELD_CREATION = 50


class IrModelFields(models.Model):
    _inherit = "ir.model.fields"

    ai = fields.Boolean(
        string="AI field",
        default=False,
        help="AI computed field",
    )
    ai_domain = fields.Char(
        string="AI field domain",
        compute="_compute_ai_domain",
        store=True,
    )
    system_prompt = fields.Html(
        string="AI Prompt",
        sanitize=True,
        sanitize_output_method="xml",
        help="Prompt given to the AI model to compute the field value",
    )

    @api.depends("ai")
    def _compute_ai_domain(self) -> None:
        for model, ir_fields in self.filtered("ai").grouped("model").items():
            last_record_id = (
                self.env[model]
                .with_context(active_test=False)
                .search([], order="id desc", limit=1)
                .id
            )
            ir_fields.ai_domain = f"[('id', '>', {max(0, last_record_id - NB_RECORDS_TO_COMPUTE_ON_FIELD_CREATION)})]"

    @api.model_create_multi
    def create(self, vals_list):
        ir_model_fields = super().create(vals_list)
        if any(f.ai and f.system_prompt for f in ir_model_fields):
            self.env["ir.cron"]._trigger_ref("ai_fields.ir_cron_fill_ai_fields")

        return ir_model_fields

    def write(self, vals):
        res = super().write(vals)
        if vals.get("system_prompt") or vals.get("ai"):
            self.env["ir.cron"]._trigger_ref("ai_fields.ir_cron_fill_ai_fields")
        return res

    def _prepare_field_attrs(self, field_data):
        attrs = super()._prepare_field_attrs(field_data)
        if attrs and field_data.get("ai"):
            attrs["ai"] = field_data.get("system_prompt") or ""
        return attrs

    def _prepare_field_vals(self, field, model_id):
        field_params = super()._prepare_field_vals(field, model_id)
        ai = getattr(field, "ai", None)
        field_params["ai"] = isinstance(ai, str)
        field_params["system_prompt"] = ai
        return field_params

    def _cron_update_ai_fields(self, batch_size=10) -> None:
        llm_api_service = LLMApiService(self.env, "openai", purpose="ai.fields")
        try:
            llm_api_service._get_api_token()
        except UserError:
            _logger.info("AI Fields cron skipped, openAI key is missing")
            return

        fields = self.search(
            [
                "|",
                "&",
                "&",
                ("ai", "=", True),
                ("system_prompt", "!=", False),
                ("ttype", "in", ("char", "text", "html")),
                "&",
                ("ttype", "=", "properties_definition"),
                ("store", "=", True),
            ],
            order="id",
        )
        remaining_fields = len(fields)

        total_done = 0
        total_remaining = 0
        for field in fields:
            done, remaining, has_time_left = (
                self._update_ai_records_with_empty_property(
                    field, batch_size, remaining_fields
                )
                if field.ttype == "properties_definition"
                else self._update_ai_records_with_empty_field(
                    field, batch_size, remaining_fields
                )
            )
            total_done += done
            total_remaining += remaining
            if not remaining:
                remaining_fields -= 1
            if not has_time_left:
                break
        if not remaining_fields:
            self.env["ir.cron"]._commit_progress(remaining=0)
        elif not total_done:
            self.env["ir.cron"]._commit_progress(remaining=0)
            _logger.info(
                "AI Fields cron rescheduled soon because all records were locked"
            )
            self.env["ir.cron"]._trigger_ref(
                "ai_fields.ir_cron_fill_ai_fields",
                self.env.cr.now() + datetime.timedelta(minutes=1),
            )
        elif total_remaining:
            _logger.info("AI Fields cron skipped %s records", total_remaining)

    def _update_ai_records_with_empty_field(
        self, field, batch_size, remaining_fields
    ) -> tuple[int, int, bool]:
        field.check_singleton()
        has_time_left = True
        model = self.env[field.model]
        query = model._search(ast.literal_eval(field.ai_domain) or [], order="id")
        query.add_where(
            SQL(
                "%(field)s IS NULL",
                field=model._field_to_sql(model._table, field.name, query),
            )
        )
        ids = OrderedSet(query)
        total_done = 0
        while (
            ids
            and has_time_left
            and (records := model.browse(ids).try_lock_for_update(limit=batch_size))
        ):
            records._update_ai_field(model._fields[field.name])
            ids -= set(records._ids)
            done = len(records)
            has_time_left = bool(
                self.env["ir.cron"]._commit_progress(
                    len(records), remaining=remaining_fields
                )
            )
            total_done += done
        return total_done, len(ids), has_time_left

    def _update_ai_records_with_empty_property(
        self, field, batch_size, remaining_fields
    ) -> tuple[int, int, bool]:
        field.check_singleton()
        to_process = []
        definition_orm_field = self.env[field.model]._fields[field.name]
        self.env.cr.execute(
            SQL(
                """
            SELECT m.id AS parent_id, definition
              FROM %(definition_table)s m, jsonb_array_elements(%(definition_name)s) definition
             WHERE definition IS NOT NULL
               AND COALESCE(definition->>'name', '') != ''
               AND definition->>'ai' = 'true'
               AND COALESCE(definition->>'system_prompt', '') != ''
               -- because we can add records at the end of the prompt, for security
               -- reason, we can not compute their values in the CRON
               AND definition->>'type' != 'many2one'
               AND definition->>'type' != 'many2many'
          ORDER BY m.id
            """,
                definition_name=SQL.identifier(field.name),
                definition_table=SQL.identifier(self.env[field.model]._table),
            )
        )
        for values in self.env.cr.dictfetchall():
            definition = values["definition"]
            parent_id = values["parent_id"]

            for properties_orm_field in definition_orm_field.properties_fields:
                model = self.env[properties_orm_field.model_name]
                ai_domain = Domain.AND(
                    [
                        definition.get("ai_domain") or [],
                        [[properties_orm_field.definition_record, "=", parent_id]],
                    ]
                )
                query = model._search(ai_domain, order="id DESC")
                query.add_where(
                    SQL(
                        "(%(field)s IS NULL OR %(field)s->%(property_name)s IS NULL)",
                        field=model._field_to_sql(
                            model._table, properties_orm_field.name, query
                        ),
                        property_name=definition["name"],
                    )
                )
                ids = OrderedSet(query)
                if ids:
                    to_process.append(
                        (model, properties_orm_field.name, definition, ids)
                    )

        has_time_left = True
        total_done = 0
        for model, fname, definition, ids in to_process:
            while has_time_left and (
                records := model.browse(ids).try_lock_for_update(limit=batch_size)
            ):
                records._update_ai_property(fname, definition)
                ids -= set(records._ids)
                done = len(records)
                has_time_left = bool(
                    self.env["ir.cron"]._commit_progress(
                        done, remaining=remaining_fields
                    )
                )
                total_done += done
        return total_done, sum(len(ids) for *__, ids in to_process), has_time_left
