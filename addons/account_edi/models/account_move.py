from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    edi_document_ids = fields.One2many(
        comodel_name="account.edi.document",
        inverse_name="move_id",
    )
    edi_state = fields.Selection(
        selection=[
            ("to_send", "To Send"),
            ("sent", "Sent"),
            ("to_cancel", "To Cancel"),
            ("cancelled", "Cancelled"),
        ],
        string="Electronic invoicing",
        compute="_compute_edi_state",
        store=True,
        help="The aggregated state of all the EDIs with web-service of this move",
    )
    edi_error_count = fields.Integer(
        compute="_compute_edi_error_count",
        help="How many EDIs are in error for this move?",
    )
    edi_blocking_level = fields.Selection(
        selection=[("info", "Info"), ("warning", "Warning"), ("error", "Error")],
        compute="_compute_edi_error_message",
    )
    edi_error_message = fields.Html(compute="_compute_edi_error_message")
    edi_web_services_to_process = fields.Text(
        compute="_compute_edi_web_services_to_process"
    )
    edi_show_cancel_button = fields.Boolean(compute="_compute_edi_show_cancel_button")
    edi_show_abandon_cancel_button = fields.Boolean(
        compute="_compute_edi_show_abandon_cancel_button"
    )
    edi_show_force_cancel_button = fields.Boolean(
        compute="_compute_edi_show_force_cancel_button"
    )

    @api.depends("edi_document_ids.state")
    def _compute_edi_state(self) -> None:
        for move in self:
            all_states = set(
                move.edi_document_ids.filtered(
                    lambda d: d.edi_format_id._is_web_service_required()
                ).mapped("state")
            )
            if all_states == {"sent"}:
                move.edi_state = "sent"
            elif all_states == {"cancelled"}:
                move.edi_state = "cancelled"
            elif "to_send" in all_states:
                move.edi_state = "to_send"
            elif "to_cancel" in all_states:
                move.edi_state = "to_cancel"
            else:
                move.edi_state = False

    @api.depends("edi_document_ids.state")
    def _compute_edi_show_force_cancel_button(self) -> None:
        for move in self:
            move.edi_show_force_cancel_button = move._can_force_cancel()

    @api.depends("edi_document_ids.error")
    def _compute_edi_error_count(self) -> None:
        for move in self:
            move.edi_error_count = len(
                move.edi_document_ids.filtered(lambda d: d.error)
            )

    @api.depends(
        "edi_error_count", "edi_document_ids.error", "edi_document_ids.blocking_level"
    )
    def _compute_edi_error_message(self) -> None:
        for move in self:
            if move.edi_error_count == 0:
                move.edi_error_message = None
                move.edi_blocking_level = None
            elif move.edi_error_count == 1:
                error_doc = move.edi_document_ids.filtered(lambda d: d.error)
                move.edi_error_message = error_doc.error
                move.edi_blocking_level = error_doc.blocking_level
            else:
                error_levels = {doc.blocking_level for doc in move.edi_document_ids}
                count = str(move.edi_error_count)
                if "error" in error_levels:
                    move.edi_error_message = self.env._(
                        "%(count)s Electronic invoicing error(s)", count=count
                    )
                    move.edi_blocking_level = "error"
                elif "warning" in error_levels:
                    move.edi_error_message = self.env._(
                        "%(count)s Electronic invoicing warning(s)", count=count
                    )
                    move.edi_blocking_level = "warning"
                else:
                    move.edi_error_message = self.env._(
                        "%(count)s Electronic invoicing info(s)", count=count
                    )
                    move.edi_blocking_level = "info"

    @api.depends(
        "edi_document_ids",
        "edi_document_ids.state",
        "edi_document_ids.blocking_level",
        "edi_document_ids.edi_format_id",
        "edi_document_ids.edi_format_id.name",
    )
    def _compute_edi_web_services_to_process(self) -> None:
        for move in self:
            to_process = move.edi_document_ids.filtered(
                lambda d: (
                    d.state in ["to_send", "to_cancel"] and d.blocking_level != "error"
                )
            )
            format_web_services = to_process.edi_format_id.filtered(
                lambda f: f._is_web_service_required()
            )
            move.edi_web_services_to_process = ", ".join(
                f.name for f in format_web_services
            )

    def _check_edi_documents_for_reset_to_draft(self):
        self.check_singleton()
        for doc in self.edi_document_ids:
            move_applicability = doc.edi_format_id._get_move_applicability(self)
            if (
                doc.edi_format_id._is_web_service_required()
                and doc.state in ("sent", "to_cancel")
                and move_applicability
                and move_applicability.get("cancel")
            ):
                return False
        return True

    @api.depends("edi_document_ids.state")
    def _compute_show_reset_to_draft_button(self) -> None:
        super()._compute_show_reset_to_draft_button()
        for move in self:
            if not move._check_edi_documents_for_reset_to_draft():
                move.show_reset_to_draft_button = False

    @api.depends("edi_document_ids.state")
    def _compute_edi_show_cancel_button(self) -> None:
        for move in self:
            if move.state != "posted":
                move.edi_show_cancel_button = False
                continue

            move.edi_show_cancel_button = False
            for doc in move.edi_document_ids:
                move_applicability = doc.edi_format_id._get_move_applicability(move)
                if (
                    doc.edi_format_id._is_web_service_required()
                    and doc.state == "sent"
                    and move_applicability
                    and move_applicability.get("cancel")
                ):
                    move.edi_show_cancel_button = True
                    break

    @api.depends("edi_document_ids.state")
    def _compute_edi_show_abandon_cancel_button(self) -> None:
        for move in self:
            move.edi_show_abandon_cancel_button = False
            for doc in move.sudo().edi_document_ids:
                move_applicability = doc.edi_format_id._get_move_applicability(move)
                if (
                    doc.edi_format_id._is_web_service_required()
                    and doc.state == "to_cancel"
                    and move_applicability
                    and move_applicability.get("cancel")
                ):
                    move.edi_show_abandon_cancel_button = True
                    break


    def _prepare_edi_tax_details(
        self,
        filter_to_apply=None,
        filter_invl_to_apply=None,
        grouping_key_generator=None,
    ):
        return self._prepare_invoice_aggregated_taxes(
            filter_invl_to_apply=filter_invl_to_apply,
            filter_tax_values_to_apply=filter_to_apply,
            grouping_key_generator=grouping_key_generator,
        )

    def _is_ready_to_be_sent(self) -> bool:
        res = super()._is_ready_to_be_sent()

        if not res:
            return False

        edi_documents_to_send = self.edi_document_ids.filtered(
            lambda x: x.state == "to_send"
        )
        return not bool(edi_documents_to_send)

    def _post_entries(self):
        posted = super()._post_entries()

        edi_document_vals_list = []
        for move in posted:
            for edi_format in move.journal_id.edi_format_ids:
                move_applicability = edi_format._get_move_applicability(move)

                if move_applicability:
                    errors = edi_format._check_move_configuration(move)
                    if errors:
                        raise UserError(
                            self.env._(
                                "Invalid invoice configuration:\n\n%s",
                                "\n".join(errors),
                            )
                        )

                    existing_edi_document = move.edi_document_ids.filtered_domain(
                        [("edi_format_id", "=", edi_format.id)]
                    )
                    if existing_edi_document:
                        existing_edi_document.sudo().write(
                            {
                                "state": "to_send",
                                "attachment_id": False,
                            }
                        )
                    else:
                        edi_document_vals_list.append(
                            {
                                "edi_format_id": edi_format.id,
                                "move_id": move.id,
                                "state": "to_send",
                            }
                        )

        self.env["account.edi.document"].create(edi_document_vals_list)
        posted.edi_document_ids._process_documents_no_web_services()
        if not self.env.context.get("skip_account_edi_cron_trigger"):
            self.env["ir.cron"]._trigger_ref("account_edi.ir_cron_edi_network")
        return posted

    def button_force_cancel(self) -> None:
        for move in self:
            to_cancel_edi_documents = move.edi_document_ids.filtered(
                lambda doc: doc.state == "to_cancel"
            )
            move.message_post(
                body=self.env._(
                    "This invoice was canceled while the EDIs %s still had a pending cancellation request.",
                    ", ".join(to_cancel_edi_documents.mapped("edi_format_id.name")),
                )
            )
        self.action_cancel()

    def action_cancel(self):
        res = super().action_cancel()

        self.edi_document_ids.filtered(lambda doc: doc.state != "sent").write(
            {"state": "cancelled", "error": False, "blocking_level": False}
        )
        self.edi_document_ids.filtered(lambda doc: doc.state == "sent").write(
            {"state": "to_cancel", "error": False, "blocking_level": False}
        )
        self.edi_document_ids._process_documents_no_web_services()
        self.env["ir.cron"]._trigger_ref("account_edi.ir_cron_edi_network")

        return res

    def _edi_allow_action_draft(self):
        self.check_singleton()
        return not self.edi_show_cancel_button

    def action_draft(self):
        for move in self:
            if not move._edi_allow_action_draft():
                raise UserError(
                    self.env._(
                        "You can't edit the following journal entry %s because an electronic document has already been "
                        "sent. Please use the 'Request EDI Cancellation' button instead.",
                        move.display_name,
                    )
                )

        res = super().action_draft()

        self.edi_document_ids.write({"error": False, "blocking_level": False})
        self.edi_document_ids.filtered(lambda doc: doc.state == "to_send").unlink()

        return res

    def button_cancel_posted_moves(self):
        to_cancel_documents = self.env["account.edi.document"]
        for move in self:
            move._check_fiscal_lock_dates()
            is_move_marked = False
            for doc in move.edi_document_ids:
                move_applicability = doc.edi_format_id._get_move_applicability(move)
                if (
                    doc.edi_format_id._is_web_service_required()
                    and doc.state == "sent"
                    and move_applicability
                    and move_applicability.get("cancel")
                ):
                    to_cancel_documents |= doc
                    is_move_marked = True
            if is_move_marked:
                move.message_post(
                    body=self.env._("A cancellation of the EDI has been requested.")
                )

        to_cancel_documents.write(
            {"state": "to_cancel", "error": False, "blocking_level": False}
        )

    def button_abandon_cancel_posted_posted_moves(self) -> None:
        documents = self.env["account.edi.document"]
        for move in self:
            is_move_marked = False
            for doc in move.edi_document_ids:
                move_applicability = doc.edi_format_id._get_move_applicability(move)
                if (
                    doc.state == "to_cancel"
                    and move_applicability
                    and move_applicability.get("cancel")
                ):
                    documents |= doc
                    is_move_marked = True
            if is_move_marked:
                move.message_post(
                    body=self.env._(
                        "A request for cancellation of the EDI has been called off."
                    )
                )

        documents.write({"state": "sent", "error": False, "blocking_level": False})

    def _get_edi_document(self, edi_format):
        return self.edi_document_ids.filtered(lambda d: d.edi_format_id == edi_format)

    def _get_edi_attachment(self, edi_format):
        return self._get_edi_document(edi_format).sudo().attachment_id

    def _message_set_main_attachment_id(
        self, attachments, force=False, filter_xml=True
    ) -> None:
        if (
            not force
            and len(attachments) > 1
            and self.message_main_attachment_id in self.edi_document_ids.attachment_id
        ):
            force = True
        super()._message_set_main_attachment_id(
            attachments, force=force, filter_xml=filter_xml
        )


    def button_process_edi_web_services(self) -> None:
        self.check_singleton()
        self.action_process_edi_web_services(with_commit=False)

    def action_process_edi_web_services(self, with_commit=True) -> None:
        docs = self.edi_document_ids.filtered(
            lambda d: (
                d.state in ("to_send", "to_cancel") and d.blocking_level != "error"
            )
        )
        docs._process_documents_web_services(with_commit=with_commit)

    def _retry_edi_documents_error(self):
        self.edi_document_ids.write({"error": False, "blocking_level": False})

    def action_retry_edi_documents_error(self) -> None:
        self._retry_edi_documents_error()
        self.action_process_edi_web_services()


    def _process_attachments_for_template_post(self, mail_template):
        result = super()._process_attachments_for_template_post(mail_template)
        for move in self.filtered("edi_document_ids"):
            move_result = result.setdefault(move.id, {})
            for edi_doc in move.edi_document_ids:
                edi_attachments = edi_doc._filter_edi_attachments_for_mailing()
                move_result.setdefault("attachment_ids", []).extend(
                    edi_attachments.get("attachment_ids", [])
                )
                move_result.setdefault("attachments", []).extend(
                    edi_attachments.get("attachments", [])
                )
        return result
