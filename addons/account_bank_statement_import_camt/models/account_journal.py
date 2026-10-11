import io
import logging

from lxml import etree

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.account_bank_statement_import_camt.lib.camt import CAMT
from odoo.addons.base.models.res_partner_bank_account import sanitize_account_number

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _get_bank_statements_available_import_formats(self):
        rslt = super()._get_bank_statements_available_import_formats()
        rslt.append("CAMT")
        return rslt

    def _get_camt_root(self, raw_file):
        try:
            root = etree.parse(io.BytesIO(raw_file)).getroot()
        except etree.XMLSyntaxError:
            return None
        if root.tag.find("camt.053") != -1:
            return root
        return None

    def _parse_bank_statement_file(self, raw_file):
        root = self._get_camt_root(raw_file)
        if root is not None:
            return self._parse_bank_statement_file_camt(root)
        return super()._parse_bank_statement_file(raw_file)

    def _parse_bank_statement_file_camt(self, root) -> list:
        ns = {"ns": root.xpath("namespace-uri(.)")}

        curr_cache = {
            c["name"]: c["id"]
            for c in self.env["res.currency"].search_read([], ["id", "name"])
        }
        statements_per_iban = {}
        currency_per_iban = {}
        unique_import_set = set()
        currency = account_no = False
        has_multi_currency = self.env.user.has_group("base.group_multi_currency")
        journal_currency = self.currency_id or self.company_id.currency_id
        for statement in root[0].findall("ns:Stmt", ns):
            statement_vals = {}
            statement_vals["name"] = (
                statement.xpath("ns:LglSeqNb/text()", namespaces=ns)
                or statement.xpath("ns:Id/text()", namespaces=ns)
            )[0]
            statement_date = CAMT._get_statement_date(statement, namespaces=ns)

            transactions = []
            sequence = 0

            account_no = sanitize_account_number(
                statement.xpath(
                    "ns:Acct/ns:Id/ns:IBAN/text() | ns:Acct/ns:Id/ns:Othr/ns:Id/text()",
                    namespaces=ns,
                )[0]
            )

            currency = statement.xpath(
                "ns:Acct/ns:Ccy/text() | ns:Bal/ns:Amt/@Ccy", namespaces=ns
            )[0]

            if currency and journal_currency and currency != journal_currency.name:
                continue

            for entry in statement.findall("ns:Ntry", ns):
                date = (
                    CAMT._get_transaction_date(entry, namespaces=ns) or statement_date
                )

                transaction_details = entry.xpath(".//ns:TxDtls", namespaces=ns)
                entry_details_sum = 0
                largest_entry_vals = {"amount": 0}
                for entry_details in transaction_details or [entry]:
                    sequence += 1
                    counter_party = CAMT._get_counter_party(
                        entry_details, entry, namespaces=ns
                    )
                    partner_name = CAMT._get_partner_name(
                        entry_details, placeholder=counter_party, namespaces=ns
                    )
                    entry_vals = {
                        "sequence": sequence,
                        "date": date,
                        "amount": CAMT._get_signed_amount(
                            entry_details,
                            entry,
                            namespaces=ns,
                            journal_currency=journal_currency,
                        ),
                        "payment_ref": CAMT._get_transaction_name(
                            entry_details, namespaces=ns, entry=entry
                        ),
                        "partner_name": partner_name,
                        "account_number": CAMT._get_account_number(
                            entry_details, placeholder=counter_party, namespaces=ns
                        ),
                        "ref": CAMT._get_ref(
                            entry_details,
                            counter_party=counter_party,
                            prefix="",
                            namespaces=ns,
                        ),
                    }

                    entry_vals["unique_import_id"] = CAMT._get_unique_import_id(
                        entry=entry_details,
                        sequence=sequence,
                        name=statement_vals["name"],
                        date=entry_vals["date"],
                        unique_import_set=unique_import_set,
                        namespaces=ns,
                    )

                    CAMT._set_amount_in_currency(
                        node=entry_details,
                        getters=CAMT._currency_amount_getters,
                        entry_vals=entry_vals,
                        currency=currency,
                        curr_cache=curr_cache,
                        has_multi_currency=has_multi_currency,
                        namespaces=ns,
                    )

                    BkTxCd = entry.xpath("ns:BkTxCd", namespaces=ns)[0]
                    entry_vals.update(CAMT._get_transaction_type(BkTxCd, namespaces=ns))
                    notes = []
                    entry_info = CAMT._get_additional_entry_info(entry, namespaces=ns)
                    if entry_info:
                        notes.append(self.env._("Entry Info: %s", entry_info))
                    text_info = CAMT._get_additional_text_info(
                        entry_details, namespaces=ns
                    )
                    if text_info:
                        notes.append(self.env._("Additional Info: %s", text_info))
                    if partner_name:
                        notes.append(
                            self.env._(
                                "Counter Party: %(partner)s", partner=partner_name
                            )
                        )
                    partner_address = CAMT._get_partner_address(
                        entry_details, ns, counter_party
                    )
                    if partner_address:
                        notes.append(self.env._("Address:\n%s", partner_address))
                    transaction_id = CAMT._get_transaction_id(
                        entry_details, namespaces=ns
                    )
                    if transaction_id:
                        notes.append(self.env._("Transaction ID: %s", transaction_id))
                    instruction_id = CAMT._get_instruction_id(
                        entry_details, namespaces=ns
                    )
                    if instruction_id:
                        notes.append(self.env._("Instruction ID: %s", instruction_id))
                    end_to_end_id = CAMT._get_end_to_end_id(
                        entry_details, namespaces=ns
                    )
                    if end_to_end_id:
                        notes.append(self.env._("End to end ID: %s", end_to_end_id))
                    mandate_id = CAMT._get_mandate_id(entry_details, namespaces=ns)
                    if mandate_id:
                        notes.append(self.env._("Mandate ID: %s", mandate_id))
                    check_number = CAMT._get_check_number(entry_details, namespaces=ns)
                    if check_number:
                        notes.append(self.env._("Check Number: %s", check_number))
                    entry_vals["narration"] = "\n".join(notes)

                    unique_import_set.add(entry_vals["unique_import_id"])
                    transactions.append(entry_vals)

                    entry_details_sum += entry_vals["amount"]
                    if abs(entry_vals["amount"]) >= abs(largest_entry_vals["amount"]):
                        largest_entry_vals = entry_vals

                transaction_amount = float(entry.find("ns:Amt", namespaces=ns).text)
                transaction_amount = (
                    -transaction_amount
                    if entry.find("ns:CdtDbtInd", namespaces=ns).text == "DBIT"
                    else transaction_amount
                )
                largest_entry_vals["amount"] += transaction_amount - entry_details_sum

            statement_vals["transactions"] = transactions
            (
                statement_vals["balance_start"],
                start_code,
            ) = CAMT._get_signed_balance_and_code(
                node=statement, namespaces=ns, getters=CAMT._start_balance_getters
            )
            (
                statement_vals["balance_end_real"],
                end_code,
            ) = CAMT._get_signed_balance_and_code(
                node=statement, namespaces=ns, getters=CAMT._end_balance_getters
            )
            statement_vals["balances_are_booked"] = {start_code, end_code} <= {
                "OPBD",
                "PRCD",
                "CLBD",
                "ITBD",
            }

            statements_per_iban.setdefault(account_no, []).append(statement_vals)
            currency_per_iban[account_no] = currency

        if len(statements_per_iban) > 1:
            account_no = sanitize_account_number(self.bank_acc_number)
            _logger.warning(
                "The following statements will not be imported because they are targeting another journal (current journal id: %s):\n- %s",
                account_no,
                "\n- ".join(
                    f"{iban}: {len(statements)} statement(s)"
                    for iban, statements in statements_per_iban.items()
                    if iban != account_no
                ),
            )
            if not account_no:
                raise UserError(
                    self.env._(
                        "Please set the IBAN account on your bank journal.\n\nThis CAMT file is targeting several IBAN accounts but none match the current journal."
                    )
                )

        statement_list = statements_per_iban.get(account_no, [])
        currency = currency_per_iban.get(account_no)

        if not currency and not statement_list:
            raise UserError(
                self.env._(
                    "Please check the currency on your bank journal.\n"
                    "No statements in currency %s were found in this CAMT file.",
                    journal_currency.name,
                )
            )
        return [[currency, account_no, statement_list]]
