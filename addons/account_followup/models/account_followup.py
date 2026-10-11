from datetime import timedelta
from typing import Self

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import frozendict

from odoo.addons.base.models.mixin_catalog import name_uniq_index


class Account_FollowupFollowupLine(models.Model):
    _name = "account_followup.followup.line"
    _description = "Follow-up Criteria"
    _order = "delay asc"
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=True, hierarchy="parent_of"),
        }
    )

    name = fields.Char(
        string="Description",
        translate=True,
        required=True,
    )
    delay = fields.Integer(
        string="Due Days",
        required=True,
        help="The number of days after the due date of the invoice to wait before sending the reminder. "
        "Can be negative if you want to send the reminder before the invoice due date.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )

    mail_template_id = fields.Many2one(
        comodel_name="mail.template",
        domain="[('model', '=', 'res.partner')]",
    )
    send_email = fields.Boolean(
        string="Email",
        default=True,
    )
    join_invoices = fields.Boolean(
        string="Attach Invoices",
        default=True,
    )
    additional_follower_ids = fields.Many2many(
        comodel_name="res.users",
        string="Add followers",
        help="If set, those users will be added as followers on the partner and receive notifications about any email reply made by the partner on the reminder email.",
    )

    sms_template_id = fields.Many2one(
        comodel_name="sms.template",
        domain="[('model', '=', 'res.partner')]",
    )
    send_sms = fields.Boolean(string="SMS")

    create_activity = fields.Boolean(string="Schedule Activity")
    activity_summary = fields.Char(string="Summary")
    activity_note = fields.Text(string="Note")
    activity_type_id = fields.Many2one(
        comodel_name="mail.activity.type",
        default=False,
    )
    activity_default_responsible_type = fields.Selection(
        selection=[
            ("followup", "Follow-up Responsible"),
            ("salesperson", "Salesperson"),
            ("account_manager", "Account Manager"),
        ],
        string="Responsible",
        default="followup",
        required=True,
        help="Determine who will be assigned to the activity:\n"
        "- Follow-up Responsible (default)\n"
        "- Salesperson: Sales Person defined on the invoice\n"
        "- Account Manager: Sales Person defined on the customer",
    )

    auto_execute = fields.Boolean(
        string="Automatic",
        default=False,
    )

    _days_uniq = models.Constraint(
        "unique(company_id, delay)",
        "Days of the follow-up lines must be different per company",
    )
    _name_src_uniq = name_uniq_index(
        "company_id",
        nulls_distinct=True,
        message="A follow-up action name must be unique. This name is already set to another action.",
    )

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        default = dict(default or {})
        company_ids = set(self.company_id.ids)
        if default.get("company_id"):
            company_ids.add(default["company_id"])

        highest_delay_per_company_id = dict.fromkeys(company_ids, 0)
        highest_delay_per_company_id.update(
            {
                company.id: delay_max
                for company, delay_max in self._read_group(
                    domain=[("company_id", "in", list(company_ids))],
                    groupby=["company_id"],
                    aggregates=["delay:max"],
                )
            }
        )
        for line, vals in zip(self, vals_list, strict=False):
            if "delay" not in default:
                company_id = default.get("company_id") or line.company_id.id
                highest_delay_per_company_id[company_id] += 15
                vals["delay"] = highest_delay_per_company_id[company_id]
            vals["name"] = default.get(
                "name",
                self.env._(
                    "%(delay)s days (copy of %(name)s)",
                    delay=vals["delay"],
                    name=line.name,
                ),
            )
        return vals_list

    @api.onchange("auto_execute")
    def _onchange_auto_execute(self) -> None:
        if self.auto_execute:
            self.create_activity = False

    def _get_next_date(self):
        self.check_singleton()
        next_followup = self._get_next_followup()
        if next_followup:
            delay = next_followup.delay - self.delay
        else:
            previous_followup = self._get_previous_followup()
            if previous_followup:
                delay = self.delay - previous_followup.delay
            else:
                delay = self.delay
        return fields.Date.context_today(self) + timedelta(days=delay)

    @api.model
    def _applicable_company_ids(self, company=None) -> list:
        company = company or self.env.company
        return [int(i) for i in company.parent_path.rstrip("/").split("/")]

    @api.model
    def _search_all_applicable(self, domain, order=None, company=None) -> Self:
        return self.search(
            Domain.AND(
                [
                    domain,
                    Domain("company_id", "in", self._applicable_company_ids(company)),
                ]
            ),
            order=order,
        )

    @api.model
    def _search_applicable(self, domain, order, company=None):
        company_ids = self._applicable_company_ids(company)
        candidates = self._search_all_applicable(domain, order, company)
        if not candidates:
            return candidates
        winning_delay = candidates[0].delay
        return max(
            (line for line in candidates if line.delay == winning_delay),
            key=lambda line: company_ids.index(line.company_id.id),
        )

    def _get_next_followup(self):
        self.check_singleton()
        return self._search_applicable(Domain("delay", ">", self.delay), "delay asc")

    def _get_previous_followup(self):
        self.check_singleton()
        return self._search_applicable(Domain("delay", "<", self.delay), "delay desc")
