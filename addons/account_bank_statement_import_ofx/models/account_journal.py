import importlib.util
import io
import logging
import re
import unicodedata
from xml.etree import ElementTree as ET

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
if not importlib.util.find_spec("ofxparse"):
    _logger.warning(
        "The ofxparse python library is not installed, ofx import will not work."
    )


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _get_bank_statements_available_import_formats(self):
        rslt = super()._get_bank_statements_available_import_formats()
        rslt.append("OFX")
        return rslt

    def _is_ofx(self, raw_file) -> bool:
        if (raw_file or b"").startswith(b"OFXHEADER"):
            return True
        try:
            return b"<ofx>" in (raw_file or b"").lower()
        except ET.ParseError:
            return False

    def _prepare_transaction_vals_line_ofx(
        self, transaction, length_transactions, partner_bank
    ):
        return {
            "date": transaction.date,
            "payment_ref": transaction.payee
            + ((transaction.memo and ": " + transaction.memo) or ""),
            "ref": transaction.id,
            "amount": float(transaction.amount),
            "unique_import_id": transaction.id,
            "account_number": partner_bank.acc_number,
            "partner_id": partner_bank.partner_id.id,
            "sequence": length_transactions + 1,
        }

    def _parse_bank_statement_file(self, raw_file):
        if not self._is_ofx(raw_file):
            return super()._parse_bank_statement_file(raw_file)
        try:
            from odoo.addons.account_bank_statement_import_ofx.ofx_parser import (
                OfxParser,
            )
        except ImportError as e:
            raise UserError(
                self.env._(
                    "The library 'ofxparse' is missing, OFX import cannot proceed."
                )
            ) from e

        try:
            ofx = OfxParser.parse(io.BytesIO(raw_file))
        except UnicodeDecodeError:
            encoding = re.findall(rb'encoding="(.*?)"', raw_file)
            encoding = encoding[0].decode("ascii") if encoding else "utf-8"
            try:
                raw_file = unicodedata.normalize(
                    "NFKD", raw_file.decode(encoding)
                ).encode("ascii", "ignore")
                ofx = OfxParser.parse(io.BytesIO(raw_file))
            except UnicodeDecodeError as e:
                raise UserError(
                    self.env._(
                        "There was an issue decoding the file. Please check the file encoding."
                    )
                ) from e
        vals_bank_statement = []
        account_lst = set()
        currency_lst = set()
        transaction_payees = [
            transaction.payee
            for account in ofx.accounts
            for transaction in account.statement.transactions
        ]
        partner_banks_dict = {
            partner_bank.partner_id.name: partner_bank
            for partner_bank in self.env["res.partner.bank.account"].search(
                [("partner_id.name", "in", transaction_payees)]
            )
        }
        for account in ofx.accounts:
            account_lst.add(account.number)
            currency_lst.add(account.statement.currency)
            transactions = []
            total_amt = 0.00
            for transaction in account.statement.transactions:
                partner_bank = partner_banks_dict.get(
                    transaction.payee, self.env["res.partner.bank.account"]
                )
                vals_line = self._prepare_transaction_vals_line_ofx(
                    transaction, len(transactions), partner_bank
                )
                total_amt += float(transaction.amount)
                transactions.append(vals_line)

            vals_bank_statement.append(
                {
                    "transactions": transactions,
                    "balance_start": float(account.statement.balance) - total_amt,
                    "balance_end_real": account.statement.balance,
                }
            )

        if account_lst and len(account_lst) == 1:
            account_lst = account_lst.pop()
            currency_lst = currency_lst.pop()
        else:
            account_lst = None
            currency_lst = None

        return [[currency_lst, account_lst, vals_bank_statement]]
