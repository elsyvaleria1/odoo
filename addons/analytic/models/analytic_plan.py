import re

from odoo import api, fields, models
from odoo.db.schema import create_index
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import (
    TransactionMemo,
    float_compare,
    float_round,
    frozendict,
    get_index_name,
    ormcache,
)

from odoo.addons.base.models.ir_model_common import MODULE_UNINSTALL_FLAG

_debug = DebugLog(__name__)

RELEVANT_PLANS = TransactionMemo(
    "get_relevant_plans",
    invalidated_by={
        "account.analytic.plan": ("default_applicability",),
        "account.analytic.applicability": (),
    },
)


class AccountAnalyticPlan(models.Model):
    _name = "account.analytic.plan"
    _inherit = ["mixin.color"]
    _description = "Analytic Plans"
    _parent_store = True
    _rec_name = "complete_name"
    _order = "sequence asc, id"

    name = fields.Char(
        translate=True,
        inverse="_inverse_name",
        required=True,
    )
    description = fields.Text()
    parent_id = fields.Many2one(
        comodel_name="account.analytic.plan",
        inverse="_inverse_parent_id",
        index="btree_not_null",
        domain="['!', ('id', 'child_of', id)]",
        ondelete="cascade",
    )
    parent_path = fields.Char(index="btree")
    root_id = fields.Many2one(
        comodel_name="account.analytic.plan",
        compute="_compute_root_id",
        search="_search_root_id",
    )
    children_ids = fields.One2many(
        comodel_name="account.analytic.plan",
        inverse_name="parent_id",
        string="Childrens",
    )
    children_count = fields.Count(
        count_of="children_ids",
        string="Children Plans Count",
    )
    complete_name = fields.Char(
        compute="_compute_complete_name",
        recursive=True,
        store=True,
    )
    account_ids = fields.One2many(
        comodel_name="account.analytic.account",
        inverse_name="plan_id",
        string="Accounts",
    )
    account_count = fields.Count(
        count_of="account_ids",
        string="Analytic Accounts Count",
    )
    all_account_count = fields.Integer(
        string="All Analytic Accounts Count",
        compute="_compute_all_account_count",
    )
    color = fields.Integer(default=lambda self: self._default_color())
    sequence = fields.Integer(default=10)

    default_applicability = fields.Selection(
        selection=[
            ("optional", "Optional"),
            ("mandatory", "Mandatory"),
            ("unavailable", "Unavailable"),
        ],
        readonly=False,
        company_dependent=True,
    )
    applicability_ids = fields.One2many(
        comodel_name="account.analytic.applicability",
        inverse_name="analytic_plan_id",
        domain="[('company_id', '=', current_company_id)]",
    )

    def _auto_init(self):
        super()._auto_init()

        def precommit():
            if self.env["ir.default"]._get(self._name, "default_applicability") is None:
                self.env["ir.default"].set(
                    self._name,
                    "default_applicability",
                    "optional",
                )

        self.env.cr.precommit.add(precommit)

    @ormcache()
    def __get_all_plans(self) -> tuple:
        project_plan = self.browse(
            int(self.env.registry.settings.get(self.env, "analytic.project_plan", 0))
        )
        if not project_plan:
            raise UserError(
                self.env._(
                    "A 'Project' plan needs to exist and its id needs to be set as `analytic.project_plan` in the system variables"
                )
            )
        other_plans = self.sudo().search([("parent_id", "=", False)]) - project_plan
        return project_plan.id, other_plans.ids

    def _get_all_plans(self):
        return map(self.browse, self.__get_all_plans())

    def _strict_column_name(self) -> str:
        self.check_singleton()
        project_plan, _other_plans = self._get_all_plans()
        return "account_id" if self == project_plan else f"x_plan{self.id}_id"

    def _column_name(self):
        return self.root_id._strict_column_name()

    def _inverse_name(self) -> None:
        self._sync_all_plan_column()

    def _inverse_parent_id(self) -> None:
        self._sync_all_plan_column()

    @api.depends("parent_id", "parent_path")
    def _compute_root_id(self) -> None:
        for plan in self.sudo():
            plan.root_id = plan._get_root()

    def _search_root_id(self, operator, value):
        if operator != "=":
            return NotImplemented
        return [("parent_path", "=like", f"{value}/%")]

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self) -> None:
        for plan in self:
            if plan.parent_id:
                plan.complete_name = "%s / %s" % (
                    plan.parent_id.complete_name,
                    plan.name,
                )
            else:
                plan.complete_name = plan.name

    @api.depends("account_ids", "children_ids")
    def _compute_all_account_count(self) -> None:
        if not self.ids:
            self.all_account_count = 0
            return
        self.env.cr.execute(
            """
            SELECT parent.id,
                   array_agg(child.id) as children_ids
              FROM account_analytic_plan parent
              JOIN account_analytic_plan child ON child.parent_path LIKE parent.parent_path || '%%'
             WHERE parent.id = ANY(%s)
          GROUP BY parent.id
        """,
            [list(self.ids)],
        )
        all_children_ids = dict(self.env.cr.fetchall())

        plans_count = dict(
            self.env["account.analytic.account"]._read_group(
                domain=[("plan_id", "child_of", self.ids)],
                aggregates=["id:count"],
                groupby=["plan_id"],
            )
        )
        plans_count = {k.id: v for k, v in plans_count.items()}
        for plan in self:
            plan.all_account_count = sum(
                plans_count.get(child_id, 0)
                for child_id in all_children_ids.get(plan.id, [])
            )

    @api.onchange("parent_id")
    def _onchange_parent_id(self):
        project_plan, __ = self._get_all_plans()
        if self._origin.id == project_plan.id:
            raise UserError(
                self.env._(
                    "You cannot add a parent to the base plan '%s'", project_plan.name
                )
            )

    @api.constrains("parent_id")
    def _check_project_plan_has_no_parent(self) -> None:
        project_plan, __ = self._get_all_plans()
        if project_plan in self and project_plan.parent_id:
            raise ValidationError(
                self.env._(
                    "You cannot add a parent to the base plan '%s'", project_plan.name
                )
            )

    def action_view_analytical_accounts(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.analytic.account",
            "domain": [("plan_id", "child_of", self.id)],
            "context": {"default_plan_id": self.id},
            "name": self.env._("Analytical Accounts"),
            "view_mode": "list,form",
        }

    def action_view_children_plans(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.analytic.plan",
            "domain": [("parent_id", "=", self.id)],
            "context": {"default_parent_id": self.id, "default_color": self.color},
            "name": self.env._("Analytical Plans"),
            "view_mode": "list,form",
        }

    @api.model
    def get_relevant_plans(self, **kwargs):
        cache = RELEVANT_PLANS(self.env)
        key = frozendict(kwargs, __company_ids__=tuple(self.env.companies.ids))
        if key in cache:
            return cache[key]
        record_account_ids = kwargs.get("existing_account_ids", [])
        project_plan, other_plans = self.env["account.analytic.plan"]._get_all_plans()
        root_plans = (project_plan + other_plans).filtered(
            lambda p: (
                p.all_account_count > 0
                and not p.parent_id
                and p._get_applicability(**kwargs) != "unavailable"
            )
        )
        forced_plans = (
            self.env["account.analytic.account"]
            .browse(record_account_ids)
            .exists()
            .mapped("root_plan_id")
            - root_plans
        )
        cache[key] = [
            {
                "id": plan.id,
                "name": plan.name,
                "color": plan.color,
                "applicability": plan._get_applicability(**kwargs)
                if plan in root_plans
                else "optional",
                "all_account_count": plan.all_account_count,
                "column_name": plan._column_name(),
            }
            for plan in (root_plans + forced_plans).sorted("sequence")
        ]
        return cache[key]

    def _get_applicability(self, **kwargs):
        self.check_singleton()
        if "applicability" in kwargs:
            return kwargs["applicability"]
        else:
            score = 0
            applicability = self.default_applicability
            for applicability_rule in self.applicability_ids.filtered(
                lambda rule: (
                    not rule.company_id
                    or not kwargs.get("company_id")
                    or rule.company_id.id == kwargs.get("company_id")
                )
            ):
                score_rule = applicability_rule._get_score(**kwargs)
                if score_rule > score:
                    applicability = applicability_rule.applicability
                    score = score_rule
            return applicability

    def unlink(self):
        plans = self.browse(self._get_descendant_ids(include_self=True))
        doomed_roots = plans.filtered(lambda plan: not plan.parent_id)
        in_doomed_trees = plans.filtered(lambda plan: plan.root_id in doomed_roots)
        doomed_fields = plans._get_plan_column() | in_doomed_trees._get_related_field()
        related_fields = (plans - in_doomed_trees)._get_related_field()
        _debug.logic(
            "plan.unlink",
            plans=len(plans),
            roots=len(doomed_roots),
            dropped_fields=len(doomed_fields),
            related_to_check=len(related_fields),
        )
        res = super().unlink()
        self.env.registry.clear_cache("stable")
        doomed_fields.unlink()
        related_fields.filtered(lambda f: not self._is_subplan_field_used(f)).unlink()
        return res

    def _hierarchy_name(self) -> tuple:
        depth = self.parent_path.count("/") - 1
        fname = f"{self._column_name()}_{depth}"
        if fname.startswith("account_id"):
            fname = f"x_{fname}"
        return depth, fname

    def _is_subplan_field_used(self, field) -> bool:
        assert "_id_" in field.name
        root_name, depth = field.name.rsplit("_", maxsplit=1)
        plan_id_match = re.search(r"\d+", root_name)
        plan_id = int(
            plan_id_match.group() if plan_id_match else next(self._get_all_plans())
        )
        return bool(
            self.env["account.analytic.plan"].search(
                [
                    ("root_id", "=", plan_id),
                    ("parent_path", "like", "%".join("/" * (int(depth) + 1))),
                ]
            )
        )

    def _get_plan_column(self, model=False):
        domain = [("name", "in", [plan._strict_column_name() for plan in self])]
        if model:
            domain.append(("model", "=", model))
        return self.env["ir.model.fields"].sudo().search(domain)

    def _get_related_field(self, model=False):
        domain = [("name", "in", [plan._hierarchy_name()[1] for plan in self])]
        if model:
            domain.append(("model", "=", model))
        return self.env["ir.model.fields"].sudo().search(domain)

    def _sync_all_plan_column(self) -> None:
        model_names = self.env.registry.get_descendants(
            ["mixin.analytic.plan.fields"], "_inherit"
        ) - {"mixin.analytic.plan.fields"}
        for model in model_names:
            self._sync_plan_column(model)

    def _sync_plan_column(self, model) -> None:
        for plan in self.sorted("parent_path"):
            prev_stored = plan._get_plan_column(model)
            depth, name_related = plan._hierarchy_name()
            prev_related = plan._get_related_field(model)
            if plan.parent_id:
                if prev_stored:
                    prev_stored.with_context({MODULE_UNINSTALL_FLAG: True}).unlink()
                description = f"{plan.root_id.name} ({depth})"
                if not prev_related:
                    self.env["ir.model.fields"].with_context(
                        update_custom_fields=True
                    ).sudo().create(
                        {
                            "name": name_related,
                            "field_description": description,
                            "state": "manual",
                            "model": model,
                            "model_id": self.env["ir.model"]._get_id(model),
                            "ttype": "many2one",
                            "relation": "account.analytic.plan",
                            "related": plan._column_name()
                            + ".plan_id"
                            + ".parent_id" * (depth - 1),
                            "store": False,
                            "readonly": True,
                        }
                    )
                else:
                    prev_related.field_description = description
            else:
                if prev_related:
                    prev_related.with_context({MODULE_UNINSTALL_FLAG: True}).unlink()
                description = plan.name
                if not prev_stored:
                    column = plan._strict_column_name()
                    field = (
                        self.env["ir.model.fields"]
                        .with_context(update_custom_fields=True)
                        .sudo()
                        .create(
                            {
                                "name": column,
                                "field_description": description,
                                "state": "manual",
                                "model": model,
                                "model_id": self.env["ir.model"]._get_id(model),
                                "ttype": "many2one",
                                "relation": "account.analytic.account",
                                "copied": True,
                                "on_delete": "restrict",
                            }
                        )
                    )
                    Model = self.env[model]
                    if Model._auto:
                        tablename = Model._table
                        indexname = get_index_name(tablename, column)
                        create_index(
                            self.env.cr,
                            indexname,
                            tablename,
                            [column],
                            "btree",
                            f"{column} IS NOT NULL",
                        )
                        field["index"] = True
                else:
                    prev_stored.field_description = description
        if self.children_ids:
            self.children_ids._sync_plan_column(model)

    def write(self, vals):
        new_parent = self.env["account.analytic.plan"].browse(vals.get("parent_id"))
        plan2previous_parent = {plan: plan.parent_id for plan in self if plan.parent_id}
        if "parent_id" in vals and new_parent:
            for plan in self:
                self.env["account.analytic.account"]._update_accounts_in_analytic_lines(
                    new_fname=new_parent._column_name(),
                    current_fname=plan._column_name(),
                    accounts=self.env["account.analytic.account"].search(  # noqa: E8507 -- one query per plan: the plan names the column to move
                        [("plan_id", "child_of", plan.id)]
                    ),
                )

        res = super().write(vals)

        if "parent_id" in vals and not new_parent:
            for plan, previous_parent in plan2previous_parent.items():
                self.env["account.analytic.account"]._update_accounts_in_analytic_lines(
                    new_fname=plan._column_name(),
                    current_fname=previous_parent._column_name(),
                    accounts=self.env["account.analytic.account"].search(  # noqa: E8507 -- one query per plan: the plan names the column to move
                        [("plan_id", "child_of", plan.id)]
                    ),
                )
        return res

    def _get_distribution_amount(
        self, amount, percentage, total_percentage, distribution_on_each_plan
    ):
        decimal_precision = self.env["decimal.precision"].get_precision(
            "Percentage Analytic"
        )
        distributed_percentage, distributed_amount = distribution_on_each_plan.get(
            self, (0, 0)
        )
        allocated_percentage = distributed_percentage + percentage
        if (
            float_compare(
                allocated_percentage,
                total_percentage,
                precision_digits=decimal_precision,
            )
            == 0
        ):
            calculated_amount = (amount * total_percentage / 100) - distributed_amount
        else:
            calculated_amount = amount * percentage / 100
        distributed_amount += float_round(
            calculated_amount, precision_digits=decimal_precision
        )
        distribution_on_each_plan[self] = (allocated_percentage, distributed_amount)
        return calculated_amount


class AccountAnalyticApplicability(models.Model):
    _name = "account.analytic.applicability"
    _description = "Analytic Plan's Applicabilities"
    _check_company_auto = True
    _check_company_domain = models.check_company_domain_parent_of

    analytic_plan_id = fields.Many2one(
        comodel_name="account.analytic.plan",
        index="btree_not_null",
    )
    business_domain = fields.Selection(
        selection=[
            ("general", "Miscellaneous"),
        ],
        string="Domain",
        required=True,
    )
    applicability = fields.Selection(
        selection=[
            ("optional", "Optional"),
            ("mandatory", "Mandatory"),
            ("unavailable", "Unavailable"),
        ],
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )

    def _get_score(self, **kwargs):
        self.check_singleton()
        score = 0.5 if self.company_id and kwargs.get("company_id") else 0
        if not kwargs.get("business_domain"):
            return score
        else:
            return (
                score + 1
                if kwargs.get("business_domain") == self.business_domain
                else -1
            )
