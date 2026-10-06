from itertools import batched

from odoo import Command, api, fields, models
from odoo.tools import SQL

# When cleaning_mode = automatic, _clean_records calls action_validate.
# This is quite slow so requires smaller batch size.
DR_CREATE_STEP_AUTO = 5000
DR_CREATE_STEP_MANUAL = 50000


class Data_CleaningModel(models.Model):
    _name = "data_cleaning.model"
    _inherit = ["mixin.data.cleaning.notification"]
    _description = "Cleaning Model"
    _order = "name"

    _cleaning_mode_field = "cleaning_mode"

    active = fields.Boolean(default=True)
    name = fields.Char(
        compute="_compute_name",
        store=True,
        copy=True,
        readonly=False,
        required=True,
    )

    res_model_id = fields.Many2one(
        comodel_name="ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
    )
    res_model_name = fields.Char(
        related="res_model_id.model",
        string="Model Name",
        readonly=True,
    )

    cleaning_mode = fields.Selection(
        selection=[
            ("manual", "Manual"),
            ("automatic", "Automatic"),
        ],
        default="manual",
        required=True,
    )

    rule_ids = fields.One2many(
        comodel_name="data_cleaning.rule",
        inverse_name="cleaning_model_id",
        string="Rules",
    )
    records_to_clean_count = fields.Integer(
        string="Records To Clean",
        compute="_compute_records_to_clean",
    )

    # The notification block -- fields, period arithmetic and delivery -- is
    # `mixin.data.cleaning.notification`.

    @api.onchange("res_model_id")
    def _compute_name(self):
        for cm_model in self:
            if not cm_model.name:
                cm_model.name = (
                    cm_model.res_model_id.name if cm_model.res_model_id else ""
                )

    @api.onchange("res_model_id")
    def _onchange_res_model_id(self):
        self.check_singleton()
        if any(rule.field_id.model_id != self.res_model_id for rule in self.rule_ids):
            self.rule_ids = [Command.clear()]

    def _compute_records_to_clean(self) -> None:
        count_data = self.env["data_cleaning.record"]._read_group(
            [("cleaning_model_id", "in", self.ids)], ["cleaning_model_id"], ["__count"]
        )
        counts = {cleaning_model.id: count for cleaning_model, count in count_data}
        for cm_model in self:
            cm_model.records_to_clean_count = counts.get(cm_model.id, 0)

    def _cron_clean_records(self) -> None:
        cleaning_models = self.sudo().search([])
        cleaning_models._clean_records(batch_commits=True)
        cleaning_models._notify_pending_records()

    def _clean_records_format_phone(self, **kwargs):
        self.check_singleton()

        self.env.cr.execute("""
            SELECT res_id, data_cleaning_rule_id
            FROM data_cleaning_record
            JOIN data_cleaning_record_data_cleaning_rule_rel
            ON data_cleaning_record_data_cleaning_rule_rel.data_cleaning_record_id = data_cleaning_record.id""")
        existing_rows = self.env.cr.fetchall()

        field = kwargs["field_name"]
        records = self.env[self.res_model_name].search([(field, "not in", [False, ""])])
        records = records.with_context(prefetch_fields=False)
        # Avoids multiple select queries when reading fields in _get_country_id and record[field].
        records.read(
            [fname for fname in ["country_id", "company_id"] if fname in records]
            + [field]
        )
        field_id = kwargs["field_id"]
        rule_ids = kwargs["rule_ids"]
        result = []
        for record in records:
            record_country = self.env["data_cleaning.record"]._get_country_id(record)
            formatted = self.env[self.res_model_name]._phone_format(
                number=record[field],
                country=record_country,
                force_format="INTERNATIONAL",
            )
            if (
                (record.id, rule_ids[0]) not in existing_rows
                and formatted
                and record[field] != formatted
            ):
                result.append(
                    {
                        "res_id": record["id"],
                        "rule_ids": rule_ids,
                        "cleaning_model_id": self.id,
                        "field_id": field_id,
                    }
                )
        return result

    def _clean_records(self, batch_commits=False) -> None:
        self.env.flush_all()

        records_to_clean = []
        cleaning_record_table = SQL.identifier(self.env["data_cleaning.record"]._table)
        for cleaning_model in self:
            records_to_create = []
            active_model = self.env[cleaning_model.res_model_name]
            active_name = active_model._active_name

            table = SQL.identifier(active_model._table)
            active_cond = (
                SQL("AND %s", SQL.identifier(active_name)) if active_name else SQL()
            )

            field_actions = cleaning_model.rule_ids._action_to_sql()
            for field_name, field_action in field_actions.items():
                action = field_action["action"]
                operator = field_action["operator"]
                if operator is False:  # special case for ACTIONS_SQL
                    cleaner = getattr(cleaning_model, "_clean_records_%s" % action)
                    values = cleaner(**field_action)
                    records_to_create += values
                else:
                    query = SQL(
                        """
                        SELECT
                            id AS res_id
                        FROM
                            %(table)s
                        WHERE
                            %(field)s %(operator)s %(cleaned_field_expr)s
                            AND NOT EXISTS(
                                SELECT 1
                                FROM %(cleaning_record_table)s
                                WHERE
                                    res_id = %(table)s.id
                                    AND cleaning_model_id = %(cleaning_model_id)s)
                            %(active_cond)s
                        ORDER BY id
                        """,
                        table=table,
                        field=(
                            field := active_model._field_to_sql(
                                active_model._table, field_name
                            )
                        ),
                        operator=SQL(operator),
                        # can be complex sql expression & multiple actions get
                        # combined through string formatting, so doesn't seem
                        # to be a smarter solution than whitelisting the entire thing
                        cleaned_field_expr=SQL(action, field)
                        if field_action["composable"]
                        else SQL(action),
                        cleaning_record_table=cleaning_record_table,
                        cleaning_model_id=cleaning_model.id,
                        active_cond=active_cond,
                    )
                    self.env.cr.execute(query)
                    for r in self.env.cr.fetchall():
                        records_to_create.append(
                            {
                                "res_id": r[0],
                                "rule_ids": field_action["rule_ids"],
                                "cleaning_model_id": cleaning_model.id,
                                "field_id": field_action["field_id"],
                            }
                        )

            if cleaning_model.cleaning_mode == "automatic":
                for records_to_create_batch in batched(
                    records_to_create, DR_CREATE_STEP_AUTO, strict=False
                ):
                    self.env["data_cleaning.record"].create(
                        records_to_create_batch
                    ).action_validate()
                    if batch_commits:
                        # Commit after each batch iteration to avoid complete rollback on timeout as
                        # this can create lots of new records.
                        self.env["ir.cron"]._commit_progress()
            else:
                records_to_clean += records_to_create
        for records_to_clean_batch in batched(
            records_to_clean, DR_CREATE_STEP_MANUAL, strict=False
        ):
            self.env["data_cleaning.record"].create(records_to_clean_batch)
            if batch_commits:
                self.env["ir.cron"]._commit_progress()

    def _get_count_pending(self):
        self.check_singleton()
        return self.env["data_cleaning.record"].search_count(
            [
                ("cleaning_model_id", "=", self.id),
            ]
        )

    def _get_notification_body(self, records_count):
        self.check_singleton()
        return self.env["ir.qweb"]._render(
            "data_cleaning.notification",
            {
                "records_count": records_count,
                "res_model_label": self.res_model_id.name,
                "cleaning_model_id": self.id,
                "menu_id": self.env.ref("data_recycle.menu_data_cleaning_root").id,
            },
        )

    def _get_notification_subject(self):
        return self.env._("Data to Clean")

    # CRUD METHODS

    def write(self, vals):
        stale = self.env["data_cleaning.model"]
        if "active" in vals and not vals["active"]:
            stale = self
        elif "res_model_id" in vals:
            # `res_model_name` is a stored related on the rule, so the queued rows
            # start claiming the new model while still holding the old table's
            # `res_id`. They then propose an edit to whichever record happens to
            # carry that id -- and the records that do need cleaning are not
            # queued at all, because the scan skips what is already there.
            stale = self.filtered(lambda m: m.res_model_id.id != vals["res_model_id"])
        if stale:
            # `active_test=False`, or the records the user discarded outlive the
            # rule they belong to and come back when it is unarchived.
            self.env["data_cleaning.record"].with_context(active_test=False).search(
                [
                    ("cleaning_model_id", "in", stale.ids),
                ]
            ).unlink()
        return super().write(vals)

    # ACTION METHODS

    def open_records(self):
        self.check_singleton()

        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "data_cleaning.action_data_cleaning_record"
        )
        action["context"] = dict(
            self.env["ir.actions.actions"]._eval_action_context(action.get("context")),
            searchpanel_default_cleaning_model_id=self.id,
        )
        return action

    def action_clean_records(self):
        self.sudo()._clean_records()

        if self.cleaning_mode == "manual":
            return self.open_records()
        return None
