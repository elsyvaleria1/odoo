from collections import defaultdict

from odoo import Command, api, fields, models, tools
from odoo.exceptions import UserError
from odoo.tools import SQL


def _has_active_column(model) -> bool:
    field = model._fields.get("active")
    return bool(field and field.store and not field.inherited)


class WizardPrivacyLogLookup(models.TransientModel):
    _name = "wizard.privacy.log.lookup"
    _description = "Privacy Lookup Wizard"
    _transient_max_count = 0
    _transient_max_hours = 24

    name = fields.Char(required=True)
    email = fields.Char(required=True)
    line_ids = fields.One2many(
        comodel_name="wizard.privacy.log.lookup.result",
        inverse_name="wizard_id",
    )
    execution_details = fields.Text(
        compute="_compute_execution_details",
        store=True,
    )
    log_id = fields.Many2one(comodel_name="privacy.log")
    records_description = fields.Text(compute="_compute_records_description")
    line_count = fields.Count(count_of="line_ids")

    def _compute_display_name(self):
        self.display_name = self.env._("Privacy Lookup")

    def _get_query_models_blacklist(self) -> list:
        return [
            "res.partner",
            "res.users",
            "mail.notification",
            "mail.followers",
            "discuss.channel.member",
            "mail.message",
        ]

    def _get_query(self):
        name = self.name.strip()
        email = f"%{self.email.strip()}%"
        email_normalized = tools.email_normalize(self.email.strip())
        if not email_normalized:
            raise UserError(self.env._("Invalid email address “%s”", self.email))

        query = SQL(
            """
            WITH indirect_references AS (
                SELECT id
                FROM res_partner
                WHERE email_normalized = %s
                OR name ilike %s)
            (SELECT
                %s AS res_model_id,
                id AS res_id,
                active AS is_active
            FROM res_partner
            WHERE id IN (SELECT id FROM indirect_references)
            ORDER BY id)
            UNION ALL
            SELECT
                %s AS res_model_id,
                id AS res_id,
                active AS is_active
            FROM res_users
            WHERE (
                (login ilike %s)
                OR
                (partner_id IN (
                    SELECT id
                    FROM res_partner
                    WHERE email ilike %s or name ilike %s)))
            -- Step 2: Special case for direct messages
            UNION ALL
            SELECT
                %s AS res_model_id,
                id AS res_id,
                True AS is_active
            FROM mail_message
            WHERE author_id IN (SELECT id FROM indirect_references)
            """,
            email_normalized,
            name,
            self.env["ir.model.data"]._xmlid_to_res_id("base.model_res_partner"),
            self.env["ir.model.data"]._xmlid_to_res_id("base.model_res_users"),
            email,
            email,
            name,
            self.env["ir.model.data"]._xmlid_to_res_id("mail.model_mail_message"),
        )

        blacklisted_models = self._get_query_models_blacklist()
        for model_name in self.env:
            if model_name in blacklisted_models:
                continue

            model = self.env[model_name]
            if model._transient or not model._auto:
                continue

            table_name = model._table

            conditions = []
            for field_name in [
                "email_normalized",
                "email",
                "email_from",
                "company_email",
            ]:
                if field_name in model and model._fields[field_name].store:
                    rec_name = model._rec_name or "name"
                    is_normalized = field_name == "email_normalized" or (
                        model_name == "mailing.trace" and field_name == "email"
                    )

                    conditions.append(
                        SQL(
                            "%s %s %s",
                            SQL.identifier(field_name),
                            SQL("=") if is_normalized else SQL("ilike"),
                            email_normalized if is_normalized else email,
                        )
                    )
                    if (
                        rec_name in model
                        and model._fields[model._rec_name].store
                        and model._fields[model._rec_name].type == "char"
                        and not model._fields[model._rec_name].translate
                    ):
                        conditions.append(
                            SQL(
                                "%s ilike %s",
                                SQL.identifier(rec_name),
                                name,
                            )
                        )
                    if is_normalized:
                        break

            conditions.extend(
                SQL(
                    "%s in (SELECT id FROM indirect_references)",
                    model._field_to_sql(table_name, field_name),
                )
                for field_name, field in model._fields.items()
                if field.comodel_name == "res.partner"
                if field.store
                if field.type == "many2one"
                if field.ondelete != "cascade"
            )

            if conditions:
                query = SQL(
                    """
                    %s
                    UNION ALL
                    SELECT
                        %s AS res_model_id,
                        id AS res_id,
                        %s AS is_active
                    FROM %s
                    WHERE %s
                    """,
                    query,
                    self.env["ir.model"].search([("model", "=", model_name)]).id,  # noqa: E8507 -- one lookup per model of the lookup
                    SQL.identifier("active") if _has_active_column(model) else True,
                    SQL.identifier(table_name),
                    SQL(" OR ").join(conditions),
                )
        return query

    def action_lookup(self):
        self.check_singleton()
        query = self._get_query()
        self.env.flush_all()
        self.env.cr.execute(query)
        results = self.env.cr.dictfetchall()
        self.line_ids = [Command.clear()] + [
            Command.create(reference) for reference in results
        ]
        return self.action_view_lines()

    def _post_log(self) -> None:
        self.check_singleton()
        if not self.log_id and self.execution_details:
            self.log_id = self.env["privacy.log"].create(
                {
                    "anonymized_name": self.name,
                    "anonymized_email": self.email,
                    "execution_details": self.execution_details,
                    "records_description": self.records_description,
                }
            )
        else:
            self.log_id.execution_details = self.execution_details
            self.log_id.records_description = self.records_description

    @api.depends("line_ids.execution_details")
    def _compute_execution_details(self) -> None:
        for wizard in self:
            wizard.execution_details = "\n".join(
                line.execution_details
                for line in wizard.line_ids
                if line.execution_details
            )
            wizard._post_log()

    @api.depends("line_ids")
    def _compute_records_description(self) -> None:
        for wizard in self:
            if not wizard.line_ids:
                wizard.records_description = ""
                continue
            records_by_model = defaultdict(list)
            for line in wizard.line_ids:
                records_by_model[line.res_model_id].append(line.res_id)
            wizard.records_description = "\n".join(
                "{model_name} ({count}): {ids_str}".format(
                    model_name=(
                        f"{model.name} - {model.model}"
                        if self.env.user.has_group("base.group_no_one")
                        else model.name
                    ),
                    count=len(ids),
                    ids_str=", ".join("#%s" % (rec_id) for rec_id in ids),
                )
                for model, ids in records_by_model.items()
            )

    def action_view_lines(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "privacy_lookup.action_privacy_lookup_wizard_line"
        )
        action["domain"] = [("wizard_id", "=", self.id)]
        return action
