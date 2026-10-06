from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import ormcache

_debug = DebugLog(__name__)


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    state = fields.Selection(
        selection_add=[
            ("documents_account_record_create", "New Journal Entry"),
        ],
        ondelete={
            "documents_account_record_create": "cascade",
        },
    )
    documents_account_create_model = fields.Selection(
        selection=[
            ("account.move.in_invoice", "Vendor Bill"),
            ("account.move.out_invoice", "Customer Invoice"),
            ("account.move.in_refund", "Vendor Credit Note"),
            ("account.move.out_refund", "Credit Note"),
            ("account.move.entry", "Miscellaneous Operations"),
            ("account.bank.statement", "Bank Statement"),
            ("account.move.in_receipt", "Purchase Receipt"),
        ]
    )
    documents_account_journal_id = fields.Many2one(
        comodel_name="account.journal",
        compute="_compute_documents_account_journal_id",
        store=True,
        readonly=False,
        domain="['|', ('id', 'in', documents_account_suitable_journal_ids), ('id', '=', False)]",
    )
    documents_account_suitable_journal_ids = fields.Many2many(
        comodel_name="account.journal",
        compute="_compute_documents_account_suitable_journal_ids",
    )
    documents_account_move_type = fields.Char(
        compute="_compute_documents_account_move_type"
    )

    @api.constrains("model_id", "state")
    def _check_document_account_check_model(self) -> None:
        document_model_id = self.env["ir.model"]._get("document.document")
        for action in self:
            if (
                action.state == "documents_account_record_create"
                and action.model_id != document_model_id
            ):
                _debug.logic(
                    "action_state_refused", reason="wrong_model", action=action
                )
                raise ValidationError(
                    self.env._('"New Journal Entry" can only be applied to Document.')
                )

    @api.depends("model_id")
    def _compute_allowed_states(self) -> None:
        super()._compute_allowed_states()
        document_model_id = self.env["ir.model"]._get("document.document")
        for action in self:
            if action.model_id != document_model_id:
                action.allowed_states = [
                    state
                    for state in action.allowed_states
                    if state != "documents_account_record_create"
                ]

    @api.depends("documents_account_create_model")
    def _compute_documents_account_journal_id(self) -> None:
        for action in self:
            if (
                action.documents_account_journal_id
                and action.documents_account_journal_id
                not in action.documents_account_suitable_journal_ids
            ):
                _debug.logic(
                    "action_journal_reset",
                    action=action,
                    candidates=len(action.documents_account_suitable_journal_ids),
                )
                action.documents_account_journal_id = (
                    action.documents_account_suitable_journal_ids[0]
                    if action.documents_account_suitable_journal_ids
                    else False
                )

    @api.depends("documents_account_create_model")
    @api.depends_context("company")
    def _compute_documents_account_suitable_journal_ids(self) -> None:
        company_journals = self.env["account.journal"].search(
            self.env["account.journal"]._check_company_domain(self.env.company)
        )
        if not company_journals:
            _debug.logic(
                "suitable_journals_empty", reason="no_company_journal", actions=self
            )
            self.documents_account_suitable_journal_ids = False
            return
        bank_journals = company_journals.filtered(
            lambda journal: journal.type in ("bank", "credit")
        )
        self.documents_account_suitable_journal_ids = False
        for action in self:
            if action.documents_account_move_type == "statement":
                action.documents_account_suitable_journal_ids = bank_journals
            elif action.documents_account_move_type:
                action.documents_account_suitable_journal_ids = self.env[
                    "account.move"
                ]._get_suitable_journal_ids(action.documents_account_move_type)

    @api.depends("documents_account_create_model")
    def _compute_documents_account_move_type(self) -> None:
        self.documents_account_move_type = False
        for action in self:
            create_model = action.documents_account_create_model or ""
            if create_model.startswith(("account.move", "account.bank.statement")):
                action.documents_account_move_type = create_model.split(".")[-1]

    def _prepare_automated_name(self):
        self.check_singleton()
        if self.state != "documents_account_record_create":
            return super()._prepare_automated_name()
        options = dict(
            self._fields["documents_account_create_model"]._description_selection(
                self.env
            )
        )
        translated_model_name = options.get(self.documents_account_create_model, "")
        if self.documents_account_journal_id:
            return self.env._(
                "Create %(model_name)s (%(journal_name)s)",
                model_name=translated_model_name,
                journal_name=self.documents_account_journal_id.name or "",
            )
        return self.env._("Create %(model_name)s", model_name=translated_model_name)

    def _get_fields_name_depends(self):
        return super()._get_fields_name_depends() + [
            "documents_account_create_model",
            "documents_account_journal_id.name",
        ]

    def _run_action_documents_account_record_create_multi(self, eval_context=None):
        documents = eval_context.get("records") or eval_context.get("record")
        if not documents:
            return False

        create_model = self.documents_account_create_model
        if not create_model:
            raise UserError(
                self.env._(
                    "Action %(action_name)s has no accounting document type set. "
                    "Choose one on the action before running it.",
                    action_name=self.display_name,
                )
            )

        journal_id = self.documents_account_journal_id or None
        if create_model.startswith("account.move"):
            return documents.account_create_account_move(
                self.documents_account_move_type, journal_id=journal_id
            )
        elif create_model == "account.bank.statement":
            return documents.account_create_account_bank_statement(
                journal_id=journal_id
            )
        raise NotImplementedError(create_model)

    def _run_action_multi(self, eval_context=None):
        """Override to ensure correct behaviour of the docs sync mechanism.

        This is a stable-proof temporary solution to ensure a synced doc will end up
        in the correct synced accounting journal folder. The issue is that there is
        an unnecessary move action to a intermediate folder in some accounting multi-actions.

        The solution is to ensure the move action happens *before* the record creation action.
        This is done by modifying the order in which the multi-actions run.

        Since the action is not naturally available on this intermediate folder, we
        temporarily embed (pin) it there during execution to bypass permission checks.
        """
        account_actions = self._get_documents_account_actions_map()
        if self.id not in account_actions:
            return super()._run_action_multi(eval_context=eval_context)

        folder_id = account_actions[self.id]
        extra_folder = self.env["document.document"].browse(folder_id)
        new_embedding_folders = (
            extra_folder._embed_action(self.id) if extra_folder.exists() else []
        )

        res = False
        try:
            # Order as viewed in action's form view, simplest contained change for stable.
            for act in self.child_ids.sorted("sequence,id"):
                res = act.run() or res
        finally:
            for folder in new_embedding_folders:
                # Restore embedding state, whether or not a child action raised
                folder.action_folder_embed_action(folder.id, self.id)

        return res

    @ormcache()
    @api.model
    def _get_documents_account_actions_map(self) -> dict:
        """Map actions that need custom handling to ensure correct syncing behaviour.

        This configuration defines which actions require a custom execution order
        and temporary pinning in specific folders during execution.

        It is cached because the mapping relies on global data (XML IDs) and is
        independent of the current user.
        """
        taxes_folder = self.env.ref(
            "document.document_finance_taxes_folder", raise_if_not_found=False
        )
        annual_closing_folder = self.env.ref(
            "document.document_finance_annual_closing_year_current_folder",
            raise_if_not_found=False,
        )

        allowed_actions_per_folder = {
            taxes_folder: [
                "create_vendor_bill",
                "create_vendor_refund",
                "create_customer_invoice",
                "create_credit_note",
            ],
            annual_closing_folder: [
                "create_misc_entry",
                "bank_statement",
            ],
        }

        return {
            action.id: folder.id
            for folder, actions_xml_ids in allowed_actions_per_folder.items()
            for action_xmlid in actions_xml_ids
            if folder
            and (
                action := self.env.ref(
                    f"document_account.ir_actions_server_{action_xmlid}",
                    raise_if_not_found=False,
                )
            )
        }
