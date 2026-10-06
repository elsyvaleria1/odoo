from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrContractSalaryBenefit(models.Model):
    _name = "hr.contract.salary.benefit"
    _description = "Salary Package Benefit"
    _order = "sequence"

    def _get_domain_field(self) -> list:
        fields_ids = self.env["hr.version"]._get_fields_benefit(triggers=False)
        return [
            ("model", "=", "hr.version"),
            ("name", "in", fields_ids),
            ("ttype", "not in", ("one2many", "many2one", "many2many")),
        ]

    def _get_domain_binary_field(self) -> list:
        return [("model", "=", "hr.version"), ("ttype", "=", "binary")]

    def _selection_public_field_names(self) -> list:
        return [
            (field.id, field.field_description)
            for field in self.sudo()
            .env["ir.model.fields"]
            .search(self._get_domain_field())
        ]

    name = fields.Char(translate=True)
    show_name = fields.Boolean(
        default=True,
        help="Whether the name should be displayed in the Salary Configurator",
    )
    active = fields.Boolean(default=True)
    source = fields.Selection(
        selection=[
            ("field", "Field"),
        ],
        string="Benefit Source",
        default="field",
        required=True,
    )
    res_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        string="Employee Record Related Field",
        required=False,
        domain=_get_domain_field,
        ondelete="cascade",
        help="Select the contract's field where the value of the benefit will be written",
    )
    cost_res_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        string="Cost Field",
        domain=_get_domain_field,
        ondelete="cascade",
        help="Select the contract's field to consider in salary computation",
    )
    # TODO: rename res_field_public into field / cost_field for consistency with fold_field and manual_field
    res_field_public = fields.Selection(
        selection="_selection_public_field_names",
        string="Benefit Field",
        compute="_compute_res_field_public",
        inverse="_inverse_res_field_public",
        readonly=False,
    )
    cost_res_field_public = fields.Selection(
        selection="_selection_public_field_names",
        string="Cost Field (Public)",
        compute="_compute_cost_res_field_public",
        inverse="_inverse_cost_res_field_public",
        readonly=False,
    )
    field = fields.Char(
        compute="_compute_field",
        store=True,
        readonly=True,
    )
    cost_field = fields.Char(
        related="cost_res_field_id.name",
        string="Cost Field Name",
        compute_sudo=True,
        readonly=True,
    )
    sequence = fields.Integer(default=100)
    benefit_type_id = fields.Many2one(
        comodel_name="hr.contract.salary.benefit.type",
        default=lambda self: self.env.ref(
            "hr_contract_salary.l10n_be_monthly_benefit", raise_if_not_found=False
        ),
        required=True,
        help="Allow to define the periodicity and output type of the advantage",
    )
    benefit_ids = fields.Many2many(
        comodel_name="hr.contract.salary.benefit",
        relation="hr_contract_salary_benefit_rel",
        column1="benefit_ids",
        column2="mandatory_benefit_ids",
        string="Mandatory Benefits",
        compute="_compute_benefits",
        store=True,
        readonly=False,
        domain="[('id', '!=', id), ('structure_type_id', '=', structure_type_id)]",
        help="Select other Benefits that need to be selected to make this Benefit available",
    )
    folded = fields.Boolean()
    fold_label = fields.Char(translate=True)
    fold_res_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        string="Fold Condition",
        domain=_get_domain_field,
        ondelete="cascade",
        help="The field here needs to be set for this benefit to be folded by default.",
    )
    fold_field = fields.Char(
        related="fold_res_field_id.name",
        string="Fold Field Name",
        readonly=True,
    )
    manual_res_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        domain=_get_domain_field,
        ondelete="cascade",
        help="Contract field used to manually encode an benefit value.",
    )
    manual_field = fields.Char(
        related="manual_res_field_id.name",
        string="Manual Field Name",
        readonly=True,
    )
    country_id = fields.Many2one(comodel_name="res.country")
    structure_type_id = fields.Many2one(
        comodel_name="hr.payroll.structure.type",
        string="Salary Structure Type",
        index=True,
        required=True,
    )
    icon = fields.Char(
        compute="_compute_icon",
        store=True,
        readonly=False,
    )
    display_type = fields.Selection(
        selection=[
            ("always", "Always Selected"),
            ("dropdown", "Dropdown"),
            ("dropdown-group", "Dropdown Group"),
            ("radio", "Radio Buttons"),
            ("slider", "Slider"),
            ("manual", "Manual Input"),
            ("text", "Text"),
        ]
    )
    description = fields.Html(translate=True)
    slider_min = fields.Float()
    slider_max = fields.Float()
    slider_step = fields.Integer(default=1)
    value_ids = fields.One2many(
        comodel_name="hr.contract.salary.benefit.value",
        inverse_name="benefit_id",
    )
    always_show_description = fields.Boolean(
        default=True,
        help="If unchecked, Description will only be shown when Benefit is selected",
    )
    requested_documents_field_ids = fields.Many2many(
        comodel_name="ir.model.fields",
        string="Requested Documents (IDs)",
        domain=_get_domain_binary_field,
    )
    requested_documents_fields_string = fields.Text(
        string="Requested Documents",
        compute="_compute_requested_fields_string",
        readonly=True,
    )
    requested_documents = fields.Char(
        string="Requested Documents Fields",
        compute="_compute_requested_documents",
        compute_sudo=True,
    )
    has_admin_access = fields.Boolean(compute="_compute_has_admin_access")

    uom = fields.Selection(
        selection=[("days", "Days"), ("percent", "Percent"), ("currency", "Currency")],
        string="Unit of Measure",
        default="currency",
    )

    activity_type_id = fields.Many2one(
        comodel_name="mail.activity.type",
        help="The type of activity that will be created automatically on the contract if this benefit is chosen by the employee.",
    )
    activity_creation = fields.Selection(
        selection=[
            ("running", "Employee signs his contract"),
            ("countersigned", "Contract is countersigned"),
        ],
        default="running",
        help="Choose when the activity is created:\n"
        "- Employee signs his contract: Activity is created as soon as the employee signed the contract\n"
        "- Contract is countersigned: HR responsible have signed the contract and conclude the process.",
    )
    activity_creation_type = fields.Selection(
        selection=[
            ("always", "When the benefit is set"),
            ("onchange", "When the benefit is modified"),
        ],
        default="always",
        help="Define when the system creates a new activity:\n"
        "- When the benefit is set: Unique creation the first time the employee will take the benefit\n"
        "- When the benefit is modified: Activity will be created for each change regarding the benefit.",
    )
    activity_responsible_id = fields.Many2one(
        comodel_name="res.users",
        string="Assigned to",
    )
    sign_template_id = fields.Many2one(
        comodel_name="sign.template",
        string="Template to Sign",
        help="Documents selected here will be requested to the employee for additional signatures related to the benefit. eg: A company car policy to approve if you choose a company car.",
    )
    sign_copy_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Send a copy to",
        help="Email address to which to transfer the signature.",
    )
    sign_frenquency = fields.Selection(
        selection=[
            ("onchange", "When the benefit is set"),
            ("always", "When the benefit is modified"),
        ],
        string="Sign Creation Type",
        default="onchange",
        help="Define when the system creates a new sign request:\n"
        "- When the benefit is set: Unique signature request the first time the employee will take the benefit\n"
        "- When the benefit is modified: Signature request will be created for each change regarding the benefit.",
    )

    _required_fold_res_field_id = models.Constraint(
        "check (folded = FALSE OR (folded = TRUE AND fold_res_field_id IS NOT NULL))",
        "A folded field is required",
    )

    @api.depends("res_field_id")
    def _compute_field(self) -> None:
        for record in self:
            if record.source == "field":
                record.field = record.res_field_id.name
            else:
                record.field = False

    @api.depends("res_field_id")
    def _compute_res_field_public(self) -> None:
        for record in self:
            record.res_field_public = record.res_field_id.id

    @api.depends("cost_res_field_id")
    def _compute_cost_res_field_public(self) -> None:
        for record in self:
            record.cost_res_field_public = record.cost_res_field_id.id

    def _inverse_res_field_public(self) -> None:
        for record in self:
            record.res_field_id = (
                self.sudo().env["ir.model.fields"].browse(record.res_field_public)
            )

    def _inverse_cost_res_field_public(self) -> None:
        for record in self:
            record.cost_res_field_id = (
                self.sudo().env["ir.model.fields"].browse(record.cost_res_field_public)
            )

    @api.depends_context("lang")
    @api.depends("requested_documents_field_ids")
    def _compute_requested_fields_string(self) -> None:
        self.requested_documents_fields_string = False
        for record in self:
            if record.requested_documents_field_ids:
                record.requested_documents_fields_string = ", ".join(
                    [
                        f.field_description
                        for f in record.sudo().requested_documents_field_ids
                    ]
                )

    @api.depends("requested_documents_field_ids")
    def _compute_requested_documents(self) -> None:
        for benefit in self:
            benefit.requested_documents = ",".join(
                benefit.requested_documents_field_ids.mapped("name")
            )

    @api.depends("structure_type_id")
    def _compute_benefits(self) -> None:
        # `benefit.structure_type_id`, not `self.structure_type_id`: on a
        # multi-record recompute - an ordinary write loop is enough - `self`
        # yields the UNION of the types, which equals no single record's type,
        # so every record's mandatory-benefit list was emptied.
        for benefit in self:
            benefit.benefit_ids = benefit.benefit_ids.filtered_domain(
                [("structure_type_id", "=", benefit.structure_type_id.id)]
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_requested_documents_as_required()
        return records

    def write(self, vals):
        previous_field_ids = self.env["ir.model.fields"]
        if "requested_documents_field_ids" in vals:
            previous_field_ids = self.requested_documents_field_ids
        res = super().write(vals)
        if "requested_documents_field_ids" in vals:
            self._sync_requested_documents_as_required(previous_field_ids)
        return res

    def _sync_requested_documents_as_required(self, previous_field_ids=False) -> None:
        """Keep `hr.contract.salary.personal.info.is_required` in sync with which fields
        are still referenced by some benefit's `requested_documents_field_ids`."""
        still_requested_field_ids = (
            self.env["hr.contract.salary.benefit"]
            .search([])
            .requested_documents_field_ids
        )
        no_longer_requested_field_ids = (
            previous_field_ids or self.env["ir.model.fields"]
        ) - still_requested_field_ids
        PersonalInfo = self.env["hr.contract.salary.personal.info"]
        if no_longer_requested_field_ids:
            PersonalInfo.search(
                [("field", "in", no_longer_requested_field_ids.mapped("name"))]
            ).is_required = False
        if self.requested_documents_field_ids:
            PersonalInfo.search(
                [("field", "in", self.requested_documents_field_ids.mapped("name"))]
            ).is_required = True

    @api.depends_context("uid")
    def _compute_has_admin_access(self) -> None:
        self.has_admin_access = self.env.user._is_system()

    @api.constrains("slider_min", "slider_max")
    def _check_min_inferior_to_max(self) -> None:
        for record in self:
            if (
                record.display_type == "slider"
                and record.slider_min > record.slider_max
            ):
                raise ValidationError(
                    self.env._(
                        "The minimum value for the slider should be inferior to the maximum value."
                    )
                )

    @api.constrains("display_type", "res_field_id", "source")
    def _check_benefits_field(self) -> None:
        white_list = ["radio", "slider", "manual", "always"]
        for record in self:
            if record.source == "rule" and record.display_type not in white_list:
                raise ValidationError(
                    self.env._(
                        "The display type of a benefit linked to a salary rule must be one of the following: %s"
                    )
                    % ", ".join(white_list)
                )
            if (
                record.source == "field"
                and not record.res_field_id
                and record.display_type != "always"
            ):
                raise ValidationError(
                    self.env._(
                        "Benefits that are not linked to a field or salary rule should always be displayed."
                    )
                )

    @api.depends("show_name")
    def _compute_icon(self) -> None:
        self.filtered(lambda b: not b.show_name).icon = False


class HrContractSalaryBenefitType(models.Model):
    _name = "hr.contract.salary.benefit.type"
    _description = "Contract Benefit Type"
    _order = "sequence"

    name = fields.Char(translate=True)
    periodicity = fields.Selection(
        selection=[
            ("monthly", "Monthly"),
            ("yearly", "Yearly"),
        ],
        default="monthly",
    )
    sequence = fields.Integer(default=100)


class HrContractSalaryBenefitValue(models.Model):
    _name = "hr.contract.salary.benefit.value"
    _description = "Contract Benefit Value"
    _order = "sequence"

    name = fields.Char(translate=True)
    sequence = fields.Integer(default=100)
    benefit_id = fields.Many2one(
        comodel_name="hr.contract.salary.benefit",
        index="btree_not_null",
    )
    value = fields.Float()
    selector_highlight = fields.Selection(
        selection=[("none", "None"), ("red", "Red")],
        default="none",
    )
    always_show_description = fields.Boolean()

    display_type = fields.Selection(
        selection=[
            ("line", "Line"),
            ("section", "Section"),
        ],
        default="line",
    )
    benefit_display_type = fields.Selection(
        related="benefit_id.display_type",
        string="Benefit Display Type",
    )
