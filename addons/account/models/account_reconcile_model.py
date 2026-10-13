import re

import psycopg

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict, mute_logger

_debug = DebugLog(__name__)


class AccountReconcileModel(models.Model):
    _name = "account.reconcile.model"
    _description = (
        "Preset to create journal entries during a invoices and payments matching"
    )
    _inherit = ["mixin.mail.thread"]
    _order = "sequence, id"
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", hierarchy="parent_of"),
        }
    )

    active = fields.Boolean(
        default=True,
        tracking=True,
    )
    name = fields.Char(
        translate=True,
        required=True,
        tracking=True,
    )
    sequence = fields.Integer(
        default=10,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        readonly=True,
        required=True,
    )

    trigger = fields.Selection(
        selection=[("manual", "Manual"), ("auto_reconcile", "Automated")],
        default="manual",
        required=True,
        tracking=True,
        help="Validate the statement line automatically (reconciliation based on your rule).",
    )
    next_activity_type_id = fields.Many2one(
        comodel_name="mail.activity.type",
        string="Next Activity",
    )

    can_be_proposed = fields.Boolean(
        compute="_compute_can_be_proposed",
        store=True,
        copy=False,
    )
    mapped_partner_id = fields.Many2one(
        comodel_name="res.partner",
        compute="_compute_mapped_partner_id",
        store=True,
        copy=False,
    )
    match_journal_ids = fields.Many2many(
        comodel_name="account.journal",
        string="Journals",
        domain="[('type', 'in', ('bank', 'cash', 'credit'))]",
        check_company=True,
        tracking=True,
        help="The reconciliation model will only be available from the selected journals.",
    )
    match_direction = fields.Selection(
        selection=[
            ("incoming", "Incoming"),
            ("outgoing", "Outgoing"),
            ("both", "Incoming and outgoing"),
        ],
        string="Direction",
        default="both",
        required=True,
        tracking=True,
        help="The reconciliation model will only be applied to money received (incoming), money paid (outgoing) or both.",
    )
    match_amount = fields.Selection(
        selection=[
            ("lower", "Is lower than or equal to"),
            ("greater", "Is greater than or equal to"),
            ("between", "Is between"),
        ],
        string="Amount (absolute)",
        tracking=True,
        help="The reconciliation model will only be applied when the absolute amount, whatever its direction, is lower than, greater than or between the specified amount(s).",
    )
    match_amount_min = fields.Float(
        string="Amount Min Parameter",
        tracking=True,
    )
    match_amount_max = fields.Float(
        string="Amount Max Parameter",
        tracking=True,
    )
    match_label = fields.Selection(
        selection=[
            ("contains", "Contains"),
            ("not_contains", "Not Contains"),
            ("match_regex", "Match Regex"),
        ],
        string="Label",
        tracking=True,
        help="""The reconciliation model will only be applied when either the statement line label, the transaction details or the note matches the following:
        * Contains: The statement line must contains this string (case insensitive). It is matched literally, so % and _ carry no special meaning.
        * Not Contains: Negation of "Contains".
        * Match Regex: Define your own regular expression.""",
    )
    match_label_param = fields.Char(
        string="Label Parameter",
        tracking=True,
    )
    match_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Partners",
        tracking=True,
        help="The reconciliation model will only be applied to the selected customers/vendors.",
    )

    line_ids = fields.One2many(
        comodel_name="account.reconcile.model.line",
        inverse_name="model_id",
        copy=True,
        tracking=True,
    )

    _match_amount_min_match_amount_max_check = models.Constraint(
        "CHECK(match_amount_min >= 0 AND match_amount_max >= 0)",
        "The amount bounds of a reconciliation model cannot be negative: they are "
        "compared to the absolute amount. Use the direction to tell money received "
        "from money paid.",
    )

    @api.constrains("match_label", "match_label_param")
    @_debug.perf.timed
    def _check_match_label_param(self) -> None:
        for record in self:
            if not record.match_label:
                continue
            if not record.match_label_param:
                _debug.logic(
                    "reco_model_rejected", reco_model=record, reason="empty_label_param"
                )
                raise ValidationError(
                    self.env._(
                        "%(model)s: the label filter is set to %(mode)s but no text "
                        "was given, so the model would never match anything.",
                        model=record.display_name,
                        mode=dict(
                            record._fields["match_label"]._description_selection(
                                self.env
                            )
                        )[record.match_label],
                    )
                )
            if record.match_label == "match_regex":
                try:
                    re.compile(record.match_label_param, re.IGNORECASE)
                    with (
                        mute_logger("odoo.db.cursor"),
                        self.env.cr.savepoint(flush=False),
                    ):
                        self.env.cr.execute(
                            SQL("SELECT '' ~* %s", record.match_label_param)
                        )
                except (re.error, psycopg.errors.InvalidRegularExpression) as err:
                    _debug.logic(
                        "reco_model_rejected",
                        reco_model=record,
                        reason="bad_label_regex",
                    )
                    raise ValidationError(
                        self.env._(
                            "%(model)s: the label regex is not valid.",
                            model=record.display_name,
                        )
                    ) from err

    @api.depends(
        "mapped_partner_id",
        "match_label",
        "match_direction",
        "match_amount",
        "match_partner_ids",
        "match_journal_ids",
        "trigger",
    )
    def _compute_can_be_proposed(self) -> None:
        for model in self:
            model.can_be_proposed = not model.mapped_partner_id and (
                model.match_label
                or model.match_direction != "both"
                or model.match_amount
                or model.match_partner_ids
                or model.match_journal_ids
                or model.trigger == "auto_reconcile"
            )

    @api.depends("match_label", "line_ids.partner_id", "line_ids.account_id")
    def _compute_mapped_partner_id(self) -> None:
        for model in self:
            is_partner_mapping = (
                model.match_label
                and len(model.line_ids) == 1
                and model.line_ids[0].partner_id
                and not model.line_ids[0].account_id
            )
            model.mapped_partner_id = (
                is_partner_mapping and model.line_ids[0].partner_id.id
            )

    @_debug.perf.timed
    def action_set_manual(self) -> None:
        _debug.lifecycle("action_set_manual", records=self)
        self.trigger = "manual"

    @_debug.perf.timed
    def action_set_auto_reconcile(self) -> None:
        _debug.lifecycle("action_set_auto_reconcile", records=self)
        self.trigger = "auto_reconcile"

    @_debug.perf.timed
    def action_reconcile_stat(self):
        _debug.lifecycle("action_reconcile_stat", records=self)
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "account.action_move_journal_line"
        )
        action.update(
            {
                "context": {},
                "domain": [("line_ids.reconcile_model_id", "=", self.id)],
                "help": """<p class="o_view_nocontent_empty_folder">{}</p>""".format(
                    self.env._("This reconciliation model has created no entry so far")
                ),
            }
        )
        return action

    def _get_copy_name(self, name):
        candidate = self.env._("%s (copy)", name)
        while self.search_count([("name", "=", candidate)], limit=1):
            candidate = self.env._("%s (copy)", candidate)
        return candidate

    def _get_copy_name_rounds(self, original, copied):
        rounds, name = 0, original
        while name != copied:
            longer = self.env._("%s (copy)", name)
            if len(longer) > len(copied):
                return 0
            name, rounds = longer, rounds + 1
        return rounds

    @_debug.perf.timed
    def copy_data(self, default=None):
        _debug.lifecycle("copy_data", records=self)
        default = dict(default or {})
        vals_list = super().copy_data(default)
        if default.get("name"):
            return vals_list
        for model, vals in zip(self, vals_list, strict=True):
            vals["name"] = self._get_copy_name(model.name)
        return vals_list

    def copy_translations(self, new, excluded=()) -> None:
        super().copy_translations(new, excluded=(*excluded, "name"))
        rounds = self._get_copy_name_rounds(self.name, new.name)
        if not rounds:
            return

        def rename(record, term):
            for _round in range(rounds):
                term = record.env._("%s (copy)", term)
            return term

        self._copy_translations_of_renamed_field(new, "name", rename)
