from collections import defaultdict

from odoo import Command, models
from odoo.exceptions import RedirectWarning, UserError
from odoo.tools import float_compare

from odoo.addons.base.models.res_partner_bank_account import sanitize_account_number

# French IBANs are 27 characters long. BNP and Credit Lyonnais (LCL) banks
# sometimes report only the local account number instead of the full IBAN,
# at different offsets within it (used in _statement_import_check_bank_account).
FR_IBAN_LEN = 27
FR_BNP_LOCAL_LEN = 11
FR_BNP_LOCAL_SLICE = slice(14, -2)
FR_LCL_LOCAL_LEN = 7
FR_LCL_LOCAL_SLICE = slice(18, -2)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _get_bank_statements_available_import_formats(self):
        """Returns a list of strings representing the supported import formats."""
        return []

    def _selection_bank_statements_source(self):
        rslt = super()._selection_bank_statements_source()
        formats_list = self._get_bank_statements_available_import_formats()
        if formats_list:
            formats_list.sort()
            import_formats_str = ", ".join(formats_list)
            rslt.append(
                (
                    "file_import",
                    self.env._(
                        "Manual (or import %(import_formats)s)",
                        import_formats=import_formats_str,
                    ),
                )
            )
        return rslt

    def create_document_from_attachment(self, attachment_ids=None):
        journal = self or self.browse(self.env.context.get("default_journal_id"))
        if journal.type in ("bank", "credit", "cash"):
            attachments = self.env["ir.attachment"].browse(attachment_ids)
            if not attachments:
                raise UserError(self.env._("No attachment was provided"))
            return journal._import_bank_statement(attachments)
        return super().create_document_from_attachment(attachment_ids)

    def _import_bank_statement(self, attachments):
        """Process the file chosen in the wizard, create bank statement(s) and go to reconciliation."""
        if any(not a.raw for a in attachments):
            raise UserError(self.env._("You uploaded an invalid or empty file."))

        statement_ids_all = []
        notifications_all = {}
        errors = defaultdict(list)
        # Let the appropriate implementation module parse the file and return the required data
        for attachment in attachments:
            try:
                iban_bank_statement_data = self._parse_bank_statement_attachment(
                    attachment
                )
                # By calling _find_additional_data on an empty recordset we force finding a journal
                # using values extracted from the statement when self is a recordset but there are
                # statements for multiple accounts
                journal_for_data = (
                    len(iban_bank_statement_data) == 1 and self
                ) or self.env["account.journal"]
                attachment_ignored_qty = 0
                for (
                    currency_code,
                    account_number,
                    stmts_vals,
                ) in iban_bank_statement_data:
                    try:
                        # Check raw data
                        self._check_parsed_data(stmts_vals, account_number)
                        # Try to find the currency and journal in odoo
                        journal = journal_for_data._find_additional_data(
                            currency_code, account_number
                        )
                        # If the journal has no Default Account, record an error and skip it
                        if not journal.default_account_id:
                            errors[attachment.name].append(
                                self.env._(
                                    "You have to set a Default Account for the journal: %s",
                                    journal.name,
                                )
                            )
                            continue
                        # Prepare statement data to be used for bank statements creation
                        stmts_vals = self._complete_bank_statement_vals(
                            stmts_vals, journal, account_number, attachment
                        )
                        # Create the bank statements
                        statement_ids, ignored_qty = self._create_bank_statements(
                            stmts_vals
                        )
                        attachment_ignored_qty += ignored_qty
                        statement_ids_all.extend(statement_ids)

                        # Now that the import worked out, set it as the bank_statements_source of the
                        # journal, but only if it had none yet: a journal already on another source
                        # (e.g. "online_sync") must not be silently reclassified, since that flip
                        # makes account_online_synchronization's write() override unlink the journal's
                        # live sync connection as a side effect.
                        if journal.bank_statements_source == "undefined":
                            # Use sudo() because only 'account.group_account_manager'
                            # has write access on 'account.journal', but 'account.group_account_user'
                            # must be able to import bank statement files
                            journal.sudo().bank_statements_source = "file_import"

                    except (UserError, RedirectWarning) as e:
                        errors[attachment.name].append(e.args[0])
                if attachment_ignored_qty:
                    notifications_all[attachment.name] = (
                        self.env._(
                            "%d transactions had already been imported and were ignored.",
                            attachment_ignored_qty,
                        )
                        if attachment_ignored_qty > 1
                        else self.env._(
                            "1 transaction had already been imported and was ignored."
                        )
                    )
            except (UserError, RedirectWarning) as e:
                errors[attachment.name].append(e.args[0])

        statements = self.env["account.bank.statement"].browse(statement_ids_all)

        result = self.env[
            "account.bank.statement.line"
        ]._action_view_bank_reconciliation_widget(
            extra_domain=[("statement_id", "in", statements.ids)],
            default_context={
                "search_default_not_matched": True,
                "default_journal_id": statements[:1].journal_id.id,
                "notifications": notifications_all,
            },
        )

        if errors:
            error_msg = self.env._(
                "All or part of the following file(s) could not be imported:\n"
            )
            error_msg += "\n".join(
                [
                    "- %s: %s" % (attachment_name, "\n".join(msg))
                    for attachment_name, msg in errors.items()
                ]
            )
            if not statements:
                raise UserError(error_msg)
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "warning",
                    "sticky": True,
                    "title": self.env._("Partial import"),
                    "message": error_msg,
                    "next": result,
                },
            }
        return result

    def _parse_bank_statement_attachment(self, attachment) -> list:
        """Parse an attachment, falling back to files embedded inside it (e.g. a PDF-embedded statement)."""
        try:
            return self._parse_bank_statement_file(attachment.raw)
        except UserError, RedirectWarning:
            embedded = self._get_embedded_statement_files(attachment)
            if not embedded:
                raise
            for raw in embedded:
                try:
                    return self._parse_bank_statement_file(raw)
                except UserError, RedirectWarning:
                    continue
            raise

    def _get_embedded_statement_files(self, attachment) -> list:
        """Return the files embedded inside attachment, delegating to the bill-import mixin's unwrapping."""
        importer = self.env["mixin.account.document.import"]
        files_data = importer._to_files_data(attachment)
        return [
            embedded["raw"]
            for embedded in importer._unwrap_attachments(files_data)
            if embedded["raw"]
        ]

    def _parse_bank_statement_file(self, raw_file) -> list:
        """Parse raw_file, resulting in a chain of responsibility across the modules that extend this method.

        :param bytes raw_file: the file's raw content
        :return: a list of triplets (if a value can't be retrieved, use None)
            - currency code: string (e.g: 'EUR')
                The ISO 4217 currency code, case insensitive
            - account number: string (e.g: 'BE1234567890')
                The number of the bank account which the statement belongs to
            - bank statements data: list of dict containing (optional items marked by o) :
                - 'name': string (e.g: '000000123')
                - 'date': date (e.g: 2013-06-26)
                -o 'balance_start': float (e.g: 8368.56)
                -o 'balance_end_real': float (e.g: 8888.88)
                -o 'balances_are_booked': bool -- True only when both balances
                   above are *booked* rather than available, i.e. when
                   balance_start + sum(amounts) == balance_end_real is an
                   identity the file must satisfy. Set it and the import
                   refuses a statement that does not add up; leave it out and
                   nothing is checked.
                - 'transactions': list of dict containing :
                    - 'name': string (e.g: 'KBC-INVESTERINGSKREDIET 787-5562831-01')
                    - 'date': date
                    - 'amount': float
                    - 'unique_import_id': string
                    -o 'account_number': string
                        Will be used to find/create the res.partner.bank.account in odoo
                    -o 'note': string
                    -o 'partner_name': string
                    -o 'ref': string
        :rtype: list
        """
        raise RedirectWarning(
            message=self.env._(
                "Could not make sense of the given file.\nDid you install the module to support this type of file?"
            ),
            action=self.env.ref("base.open_module_tree").id,
            button_text=self.env._("Go to Apps"),
            additional_context={
                "search_default_name": "account_bank_statement_import",
                "search_default_extra": True,
            },
        )

    def _check_parsed_data(self, stmts_vals, account_number) -> None:
        """Basic and structural verifications"""
        if len(stmts_vals) == 0:
            raise UserError(
                self.env._(
                    "This file doesn't contain any statement for account %s.\nIf it contains transactions for more than one account, it must be imported on each of them.",
                    account_number,
                )
            )

        if not any(vals["transactions"] for vals in stmts_vals):
            raise UserError(
                self.env._(
                    "This file doesn't contain any transaction for account %s.\nIf it contains transactions for more than one account, it must be imported on each of them.",
                    account_number,
                )
            )

        self._check_parsed_balances(stmts_vals, account_number)

    def _check_parsed_balances(self, stmts_vals, account_number) -> None:
        """Opening + transactions must reach the stated closing balance.

        The check a truncated or partially-parsed statement fails, and the one
        no format was checking. It runs only where the parser says both
        balances are **booked**: an available balance excludes holds and
        includes float, so it does not bracket the entries and a file carrying
        one is consistent while its arithmetic is not. A parser that does not
        say stays silent -- which is every format but CAMT today, three of them
        because they derive one balance from the other and the identity is true
        by construction.
        """
        for vals in stmts_vals:
            if not vals.get("balances_are_booked"):
                continue
            start = vals.get("balance_start")
            end = vals.get("balance_end_real")
            if start is None or end is None:
                continue
            moved = sum(
                transaction["amount"] for transaction in vals.get("transactions") or []
            )
            if float_compare(start + moved, end, precision_digits=2) != 0:
                raise UserError(
                    self.env._(
                        "The statement %(name)s for account %(account)s does not "
                        "add up: it opens at %(start)s, moves %(moved)s and states "
                        "a closing balance of %(end)s, which is %(difference)s "
                        "away. Importing it would put that difference into the "
                        "books.",
                        name=vals.get("name") or vals.get("reference") or "",
                        account=account_number,
                        start=start,
                        moved=moved,
                        end=end,
                        difference=round(end - start - moved, 2),
                    )
                )

    def _statement_import_check_bank_account(self, account_number):
        # Needed for CH to accommodate for non-unique account numbers
        sanitized_acc_number = self.bank_account_id.sanitized_acc_number.split(" ")[0]
        # Needed for BNP France
        if (
            len(sanitized_acc_number) == FR_IBAN_LEN
            and len(account_number) == FR_BNP_LOCAL_LEN
            and sanitized_acc_number[:2].upper() == "FR"
        ):
            return sanitized_acc_number[FR_BNP_LOCAL_SLICE] == account_number

        # Needed for Credit Lyonnais (LCL)
        if (
            len(sanitized_acc_number) == FR_IBAN_LEN
            and len(account_number) == FR_LCL_LOCAL_LEN
            and sanitized_acc_number[:2].upper() == "FR"
        ):
            return sanitized_acc_number[FR_LCL_LOCAL_SLICE] == account_number

        return sanitized_acc_number == account_number

    def _find_additional_data(self, currency_code, account_number):
        """Look for the account.journal using values extracted from the
        statement and make sure it's consistent.
        """
        company_currency = self.env.company.currency_id
        currency = None
        sanitized_account_number = sanitize_account_number(account_number)

        if currency_code:
            currency = self.env["res.currency"].search(
                [("name", "=ilike", currency_code)], limit=1
            )
            if not currency:
                raise UserError(
                    self.env._("No currency found matching '%s'.", currency_code)
                )
            if currency == company_currency:
                currency = False

        journal = self
        if account_number:
            # No bank account on the journal : create one from the account number of the statement
            if journal and not journal.bank_account_id:
                journal.set_bank_account(account_number)
            # No journal passed to the wizard : try to find one using the account number of the statement
            elif not journal:
                journal = self.search(
                    [
                        (
                            "bank_account_id.sanitized_acc_number",
                            "=",
                            sanitized_account_number,
                        )
                    ]
                )
                if len(journal) > 1:
                    raise UserError(
                        self.env._(
                            "Several journals match the account number %s. Please manually select the journal to import into.",
                            account_number,
                        )
                    )
                if not journal:
                    # Sometimes the bank returns only part of the full account number (e.g. local account number instead of full IBAN)
                    partial_match = self.search(
                        [
                            (
                                "bank_account_id.sanitized_acc_number",
                                "ilike",
                                sanitized_account_number,
                            )
                        ]
                    )
                    if len(partial_match) == 1:
                        journal = partial_match
                # Both searches above are bound by the journal company guard, which
                # scopes to the *enabled* companies rather than the active one. A
                # user working in one company while another is enabled -- the
                # normal state, since http routes leave allowed_company_ids unset
                # and widen env.companies to all of them -- would otherwise import
                # the statement into the other company's books without a word.
                if journal and journal.company_id != self.env.company:
                    raise UserError(
                        self.env._(
                            "The only journal matching the account number %(account)s belongs to %(other)s, but you are working in %(active)s. Switch to %(other)s, or select the journal to import into manually.",
                            account=account_number,
                            other=journal.company_id.display_name,
                            active=self.env.company.display_name,
                        )
                    )
            # Already a bank account on the journal : check it's the same as on the statement
            elif not self._statement_import_check_bank_account(
                sanitized_account_number
            ):
                raise UserError(
                    self.env._(
                        "The account of this statement (%(account)s) is not the same as the journal (%(journal)s).",
                        account=account_number,
                        journal=journal.bank_account_id.acc_number,
                    )
                )

        # If importing into an existing journal, its currency must be the same as the bank statement
        if journal:
            journal_currency = journal.currency_id or journal.company_id.currency_id
            if currency is None:
                currency = journal_currency
            if currency and currency != journal_currency:
                statement_cur_code = (
                    not currency and company_currency.name
                ) or currency.name
                journal_cur_code = (
                    not journal_currency and company_currency.name
                ) or journal_currency.name
                raise UserError(
                    self.env._(
                        "The currency of the bank statement (%(code)s) is not the same as the currency of the journal (%(journal)s).",
                        code=statement_cur_code,
                        journal=journal_cur_code,
                    )
                )

        if not journal:
            if account_number:
                message = self.env._(
                    "Cannot find in which journal to import the statement for account %s. Please configure the journal first.",
                    account_number,
                )
            else:
                message = self.env._(
                    "Cannot find in which journal to import this statement. Please manually select a journal."
                )
            raise UserError(message)
        return journal

    def _complete_bank_statement_vals(
        self, stmts_vals, journal, account_number, attachment
    ):
        for st_vals in stmts_vals:
            if not st_vals.get("reference"):
                st_vals["reference"] = attachment.name
            st_vals["attachment_ids"] = [Command.set(attachment.ids)]
            for line_vals in st_vals["transactions"]:
                line_vals["journal_id"] = journal.id
                unique_import_id = line_vals.get("unique_import_id")
                if unique_import_id:
                    sanitized_account_number = sanitize_account_number(account_number)
                    account_prefix = (
                        f"{sanitized_account_number}-"
                        if sanitized_account_number
                        else ""
                    )
                    line_vals["unique_import_id"] = (
                        f"{account_prefix}{journal.id}-{unique_import_id}"
                    )

                if not line_vals.get("bank_account_id"):
                    # Find the partner and his bank account or create the bank account. The partner selected during the
                    # reconciliation process will be linked to the bank when the statement is closed.
                    identifying_string = line_vals.get("account_number")
                    if identifying_string:
                        if line_vals.get("partner_id"):
                            partner_bank = self.env["res.partner.bank.account"].search(
                                [
                                    ("acc_number", "=", identifying_string),
                                    ("partner_id", "=", line_vals["partner_id"]),
                                ]
                            )
                        else:
                            partner_bank = self.env["res.partner.bank.account"].search(
                                [
                                    ("acc_number", "=", identifying_string),
                                    (
                                        "company_id",
                                        "in",
                                        (False, journal.company_id.id),
                                    ),
                                ]
                            )
                        # If multiple partners share the same account number, do not try to guess and just avoid setting it
                        if partner_bank and len(partner_bank) == 1:
                            line_vals["bank_account_id"] = partner_bank.id
                            line_vals["partner_id"] = partner_bank.partner_id.id
        return stmts_vals

    def _create_bank_statements(self, stmts_vals, raise_no_imported_file=True) -> tuple:
        """Create bank statements from imported values (skipping already-imported transactions) and return (statement_ids, ignored_qty)."""
        BankStatement = self.env["account.bank.statement"]
        BankStatementLine = self.env["account.bank.statement.line"]

        # Filter out already imported transactions and create statements.
        # Prefetch the already-imported ids in one query instead of one
        # search() per transaction line: a large statement file would
        # otherwise issue one point query per line.
        all_import_ids = [
            line_vals["unique_import_id"]
            for st_vals in stmts_vals
            for line_vals in st_vals["transactions"]
            if line_vals.get("unique_import_id")
        ]
        imported_ids = (
            {
                res["unique_import_id"]
                for res in BankStatementLine.sudo().search_read(
                    [("unique_import_id", "in", all_import_ids)],
                    ["unique_import_id"],
                )
            }
            if all_import_ids
            else set()
        )
        statement_ids = []
        statement_line_ids = []
        ignored_qty = 0
        for st_vals in stmts_vals:
            filtered_st_lines = []
            for line_vals in st_vals["transactions"]:
                if line_vals["amount"] == 0:
                    # Informational zero-amount lines were never imported, so they
                    # must not inflate the "already been imported" notification
                    # count; skipping them leaves balance_start unchanged anyway.
                    continue
                unique_import_id = line_vals.get("unique_import_id")
                if not unique_import_id or unique_import_id not in imported_ids:
                    filtered_st_lines.append(line_vals)
                    if unique_import_id:
                        # Keep an id repeated within this same import filtered,
                        # exactly as it was when each line ran its own search
                        # against the statements already created by this call.
                        imported_ids.add(unique_import_id)
                else:
                    ignored_qty += 1
                    if st_vals.get("balance_start") is not None:
                        st_vals["balance_start"] += float(line_vals["amount"])

            if len(filtered_st_lines) > 0:
                # Remove values that won't be used to create records
                st_vals.pop("transactions", None)
                st_vals.pop("balances_are_booked", None)
                # Create the statement
                st_vals["line_ids"] = [
                    Command.create(line) for line in filtered_st_lines
                ]
                statement = BankStatement.with_context(
                    default_journal_id=self.id,
                    auto_statement_processing=True,
                ).create(st_vals)
                if not statement.name:
                    statement.name = st_vals["reference"]
                statement_ids.append(statement.id)
                statement_line_ids.extend(statement.line_ids.ids)

        if len(statement_line_ids) == 0 and raise_no_imported_file:
            raise UserError(self.env._("You already have imported that file."))

        return statement_ids, ignored_qty
