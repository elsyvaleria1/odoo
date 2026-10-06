import logging
from datetime import timedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AutomationRule(models.Model):
    _inherit = "automation.rule"

    @api.model
    def _install_demo_data(self, company=False):
        _logger.warning("=" * 80)
        _logger.warning("DEMO DATA INSTALLATION STARTED - _install_demo_data called!")
        _logger.warning("Company parameter: %s", company)
        _logger.warning("=" * 80)
        _logger.info("Installing automation demo data...")

        demo_data = self._prepare_demo_data(company)
        created_records = {}

        for model_name, records_data in demo_data.items():
            if not records_data:
                continue

            _logger.info("Creating %d %s records", len(records_data), model_name)
            model = self.env[model_name]

            for xml_id, values in records_data.items():
                resolved_values = self._resolve_demo_references(values, created_records)
                predecessors = resolved_values.pop("_predecessors", [])

                try:
                    _logger.info("Creating %s (%s)...", xml_id, model_name)
                    record = model.create(resolved_values)
                    created_records[xml_id] = record
                    self._create_demo_edges(record, predecessors)

                    self.env["ir.model.data"].create(
                        {
                            "name": xml_id,
                            "module": "automation_account",
                            "model": model_name,
                            "res_id": record.id,
                            "noupdate": True,
                        }
                    )
                    _logger.info("✓ Created %s (ID: %s)", xml_id, record.id)

                except Exception:
                    _logger.exception("Failed to create %s (%s)", xml_id, model_name)
                    raise

        self._link_created_records(created_records)

        self._post_load_demo_data(company, created_records)

        _logger.info("Demo data installation completed!")
        return True

    def _create_demo_edges(self, line, predecessors):
        if not predecessors or line._name != "automation.runtime.line":
            return self.env["automation.runtime.edge"]

        return self.env["automation.runtime.edge"].create(
            [
                {
                    "runtime_id": line.runtime_id.id,
                    "source_line_id": predecessor.id,
                    "target_line_id": line.id,
                }
                for predecessor in predecessors
            ],
        )

    def _resolve_demo_references(self, values, created_records):
        resolved = {}

        for key, value in values.items():
            if key == "_predecessor_ids" and isinstance(value, list):
                resolved["_predecessors"] = [
                    created_records[xml_id]
                    for xml_id in value
                    if xml_id in created_records
                ]

            elif isinstance(value, str) and value in created_records:
                resolved[key] = created_records[value].id

            elif isinstance(value, str) and "." in value:
                try:
                    ref_record = self.env.ref(value, raise_if_not_found=False)
                    if ref_record:
                        resolved[key] = ref_record.id
                        _logger.debug(
                            "✓ Resolved %s: %s -> ID %s",
                            key,
                            value,
                            ref_record.id,
                        )
                    else:
                        _logger.error(
                            "✗ XML ID not found: %s = %s (field will be set to string, causing DB error!)",
                            key,
                            value,
                        )
                        raise ValueError(f"XML ID not found: {value} for field {key}")
                except ValueError:
                    raise
                except KeyError as e:
                    _logger.debug(
                        "Not an XML ID (keeping as string): %s=%s (%s)",
                        key,
                        value,
                        e,
                    )
                    resolved[key] = value

            else:
                resolved[key] = value

        return resolved

    def _link_created_records(self, created_records):
        _logger.info("Linking created_record_ref...")

        ref_mapping = {
            "demo_runtime_line_completed_01_action1": "demo_move_invoice_01",
            "demo_runtime_line_completed_01_action3": "demo_move_bill_01",
            "demo_runtime_line_completed_01_action4": "demo_payment_01",
            "demo_runtime_line_inprogress_action2": "demo_move_invoice_02",
            "demo_runtime_line_multi_action1": "demo_move_bill_02",
            "demo_runtime_line_multi_action3": "demo_move_bill_03",
            "demo_runtime_line_multi_action4": "demo_payment_02",
            "demo_runtime_line_fx_action2": "demo_move_invoice_03",
            "demo_runtime_line_fx_action4": "demo_move_refund_01",
        }

        for line_xml_id, doc_xml_id in ref_mapping.items():
            line_record = created_records.get(line_xml_id)
            doc_record = created_records.get(doc_xml_id)

            if line_record and doc_record:
                line_record.created_record_ref = f"{doc_record._name},{doc_record.id}"
                _logger.info("Linked %s to %s", line_xml_id, doc_xml_id)

    @api.model
    def _prepare_demo_data(self, company=False):
        return {
            "automation.runtime": self._prepare_demo_data_runtime(company),
            "automation.runtime.line": self._prepare_demo_data_runtime_line(company),
            "account.move": self._prepare_demo_data_move(company),
            "account.payment": self._prepare_demo_data_payment(company),
            "account.bank.statement.line": self._prepare_demo_data_statement_line(
                company
            ),
        }

    def _post_load_demo_data(self, company=False, created_records=None):
        if not created_records:
            return

        move_xml_ids = [
            "demo_move_invoice_01",
            "demo_move_bill_01",
            "demo_move_bill_02",
            "demo_move_invoice_02",
            "demo_move_bill_03",
            "demo_move_invoice_03",
            "demo_move_refund_01",
        ]

        for xml_id in move_xml_ids:
            move = created_records.get(xml_id)
            if move and move._name == "account.move":
                try:
                    move.action_post()
                    _logger.info("Posted demo move: %s", xml_id)
                except (UserError, ValidationError) as e:
                    _logger.warning("Could not post demo move %s: %s", xml_id, e)

        payment_xml_ids = ["demo_payment_01", "demo_payment_02"]

        for xml_id in payment_xml_ids:
            payment = created_records.get(xml_id)
            if payment and payment._name == "account.payment":
                try:
                    payment.action_post()
                    _logger.info("Posted demo payment: %s", xml_id)
                except (UserError, ValidationError) as e:
                    _logger.warning("Could not post demo payment %s: %s", xml_id, e)

    @api.model
    def _prepare_demo_data_runtime(self, company=False):
        return {
            "demo_runtime_completed_01": {
                "name": "DEMO-COMPLETED-001",
                "automation_id": "automation_account.automation_cash_exchange_simple",
                "partner_id": "base.res_partner_2",
                "amount": 1500.00,
                "date": fields.Date.today().strftime("%Y-%m-%d"),
                "reference": "Cash exchange for Azure Interior",
                "state": "done",
            },
            "demo_runtime_inprogress_01": {
                "name": "DEMO-INPROG-001",
                "automation_id": "automation_account.automation_collection_in_kind",
                "partner_id": "base.res_partner_12",
                "amount": 2500.00,
                "date": fields.Date.today().strftime("%Y-%m-%d"),
                "reference": "Collection in kind for Ready Mat",
                "state": "in_progress",
            },
            "demo_runtime_draft_01": {
                "name": "DEMO-DRAFT-001",
                "automation_id": "automation_account.automation_cash_to_bank",
                "partner_id": "base.res_partner_2",
                "amount": 5000.00,
                "date": fields.Date.today().strftime("%Y-%m-%d"),
                "reference": "Internal cash transfer",
                "state": "draft",
            },
            "demo_runtime_multi_completed_01": {
                "name": "DEMO-MULTI-COMPLETED-001",
                "automation_id": "automation_account.automation_cash_exchange_multicompany",
                "partner_id": "base.res_partner_3",
                "amount": 3000.00,
                "date": (fields.Date.today() + timedelta(days=-5)).strftime("%Y-%m-%d"),
                "reference": "Multi-company cash exchange",
                "state": "done",
            },
            "demo_runtime_fx_completed_01": {
                "name": "DEMO-FX-COMPLETED-001",
                "automation_id": "automation_account.automation_customer_discount_fx",
                "partner_id": "base.res_partner_2",
                "amount": 2000.00,
                "date": (fields.Date.today() + timedelta(days=-3)).strftime("%Y-%m-%d"),
                "reference": "FX discount workflow",
                "state": "done",
            },
            "demo_runtime_cancelled_01": {
                "name": "DEMO-CANCELLED-001",
                "automation_id": "automation_account.automation_undeductible_expense",
                "partner_id": "base.res_partner_4",
                "amount": 750.00,
                "date": (fields.Date.today() + timedelta(days=-10)).strftime(
                    "%Y-%m-%d"
                ),
                "reference": "Cancelled expense workflow",
                "state": "cancel",
            },
        }

    @api.model
    def _prepare_demo_data_runtime_line(self, company=False):
        return {
            "demo_runtime_line_completed_01_action1": {
                "name": "Create Customer Invoice",
                "runtime_id": "demo_runtime_completed_01",
                "action_id": "automation_account.action_cash_exch_simple_invoice",
                "sequence": 10,
                "state": "done",
            },
            "demo_runtime_line_completed_01_action2": {
                "name": "Reconcile Payment",
                "runtime_id": "demo_runtime_completed_01",
                "action_id": "automation_account.action_cash_exch_simple_reconcile",
                "sequence": 20,
                "state": "done",
                "_predecessor_ids": ["demo_runtime_line_completed_01_action1"],
            },
            "demo_runtime_line_completed_01_action3": {
                "name": "Create Vendor Bill",
                "runtime_id": "demo_runtime_completed_01",
                "action_id": "automation_account.action_cash_exch_simple_bill",
                "sequence": 30,
                "state": "done",
                "_predecessor_ids": ["demo_runtime_line_completed_01_action2"],
            },
            "demo_runtime_line_completed_01_action4": {
                "name": "Pay Vendor Bill",
                "runtime_id": "demo_runtime_completed_01",
                "action_id": "automation_account.action_cash_exch_simple_payment",
                "sequence": 40,
                "state": "done",
                "_predecessor_ids": ["demo_runtime_line_completed_01_action3"],
            },
            "demo_runtime_line_inprogress_action1": {
                "name": "Collection Entry",
                "runtime_id": "demo_runtime_inprogress_01",
                "action_id": "automation_account.action_coll_kind_entry",
                "sequence": 10,
                "state": "done",
            },
            "demo_runtime_line_inprogress_action2": {
                "name": "Create Vendor Bill",
                "runtime_id": "demo_runtime_inprogress_01",
                "action_id": "automation_account.action_coll_kind_vendor_bill",
                "sequence": 20,
                "state": "done",
                "_predecessor_ids": ["demo_runtime_line_inprogress_action1"],
            },
            "demo_runtime_line_inprogress_action3": {
                "name": "Create Refund",
                "runtime_id": "demo_runtime_inprogress_01",
                "action_id": "automation_account.action_coll_kind_refund",
                "sequence": 30,
                "state": "ready",
                "_predecessor_ids": ["demo_runtime_line_inprogress_action2"],
            },
            "demo_runtime_line_draft_action1": {
                "name": "Bank Statement Line",
                "runtime_id": "demo_runtime_draft_01",
                "action_id": "automation_account.action_cash_bank_bsl",
                "sequence": 10,
                "state": "ready",
            },
            "demo_runtime_line_draft_action2": {
                "name": "Journal Entry",
                "runtime_id": "demo_runtime_draft_01",
                "action_id": "automation_account.action_cash_bank_entry",
                "sequence": 20,
                "state": "waiting",
                "_predecessor_ids": ["demo_runtime_line_draft_action1"],
            },
            "demo_runtime_line_multi_action1": {
                "name": "Create Invoice",
                "runtime_id": "demo_runtime_multi_completed_01",
                "action_id": "automation_account.action_cash_exch_multi_invoice",
                "sequence": 10,
                "state": "done",
            },
            "demo_runtime_line_multi_action2": {
                "name": "Reconcile",
                "runtime_id": "demo_runtime_multi_completed_01",
                "action_id": "automation_account.action_cash_exch_multi_reconcile",
                "sequence": 20,
                "state": "done",
                "_predecessor_ids": ["demo_runtime_line_multi_action1"],
            },
            "demo_runtime_line_multi_action3": {
                "name": "Create Bill",
                "runtime_id": "demo_runtime_multi_completed_01",
                "action_id": "automation_account.action_cash_exch_multi_bill",
                "sequence": 30,
                "state": "done",
                "_predecessor_ids": ["demo_runtime_line_multi_action2"],
            },
            "demo_runtime_line_multi_action4": {
                "name": "Pay Bill",
                "runtime_id": "demo_runtime_multi_completed_01",
                "action_id": "automation_account.action_cash_exch_multi_payment",
                "sequence": 40,
                "state": "done",
                "_predecessor_ids": ["demo_runtime_line_multi_action3"],
            },
            "demo_runtime_line_fx_action1": {
                "name": "Bank Statement",
                "runtime_id": "demo_runtime_fx_completed_01",
                "action_id": "automation_account.action_cust_discount_fx_bsl",
                "sequence": 10,
                "state": "done",
            },
            "demo_runtime_line_fx_action2": {
                "name": "Create Invoice",
                "runtime_id": "demo_runtime_fx_completed_01",
                "action_id": "automation_account.action_cust_discount_fx_invoice",
                "sequence": 20,
                "state": "done",
                "_predecessor_ids": ["demo_runtime_line_fx_action1"],
            },
            "demo_runtime_line_fx_action3": {
                "name": "Reconcile Payment",
                "runtime_id": "demo_runtime_fx_completed_01",
                "action_id": "automation_account.action_cust_discount_fx_reconcile",
                "sequence": 30,
                "state": "done",
                "_predecessor_ids": ["demo_runtime_line_fx_action2"],
            },
            "demo_runtime_line_fx_action4": {
                "name": "Create Credit Note",
                "runtime_id": "demo_runtime_fx_completed_01",
                "action_id": "automation_account.action_cust_discount_fx_credit_note",
                "sequence": 40,
                "state": "done",
                "_predecessor_ids": ["demo_runtime_line_fx_action3"],
            },
        }

    @api.model
    def _prepare_demo_data_move(self, company=False):
        return {
            "demo_move_invoice_01": {
                "move_type": "out_invoice",
                "partner_id": "base.res_partner_2",
                "date": fields.Date.today().strftime("%Y-%m-%d"),
                "invoice_date": fields.Date.today().strftime("%Y-%m-%d"),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Demo Service - Cash Exchange",
                            "quantity": 1,
                            "price_unit": 1500.00,
                        }
                    ),
                ],
            },
            "demo_move_bill_01": {
                "move_type": "in_invoice",
                "partner_id": "base.res_partner_2",
                "date": fields.Date.today().strftime("%Y-%m-%d"),
                "invoice_date": fields.Date.today().strftime("%Y-%m-%d"),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Demo Expense - Cash Exchange",
                            "quantity": 1,
                            "price_unit": 1500.00,
                        }
                    ),
                ],
            },
            "demo_move_invoice_02": {
                "move_type": "out_invoice",
                "partner_id": "base.res_partner_12",
                "date": fields.Date.today().strftime("%Y-%m-%d"),
                "invoice_date": fields.Date.today().strftime("%Y-%m-%d"),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Demo Service - Collection in Kind",
                            "quantity": 1,
                            "price_unit": 2500.00,
                        }
                    ),
                ],
            },
            "demo_move_bill_02": {
                "move_type": "in_invoice",
                "partner_id": "base.res_partner_3",
                "date": (fields.Date.today() + timedelta(days=-5)).strftime("%Y-%m-%d"),
                "invoice_date": (fields.Date.today() + timedelta(days=-5)).strftime(
                    "%Y-%m-%d"
                ),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Demo Service - Multi-company Exchange",
                            "quantity": 1,
                            "price_unit": 3000.00,
                        }
                    ),
                ],
            },
            "demo_move_bill_03": {
                "move_type": "in_invoice",
                "partner_id": "base.res_partner_3",
                "date": (fields.Date.today() + timedelta(days=-5)).strftime("%Y-%m-%d"),
                "invoice_date": (fields.Date.today() + timedelta(days=-5)).strftime(
                    "%Y-%m-%d"
                ),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Demo Expense - Multi-company Transfer",
                            "quantity": 1,
                            "price_unit": 3000.00,
                        }
                    ),
                ],
            },
            "demo_move_invoice_03": {
                "move_type": "out_invoice",
                "partner_id": "base.res_partner_2",
                "date": (fields.Date.today() + timedelta(days=-3)).strftime("%Y-%m-%d"),
                "invoice_date": (fields.Date.today() + timedelta(days=-3)).strftime(
                    "%Y-%m-%d"
                ),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Demo Service - FX Transaction",
                            "quantity": 1,
                            "price_unit": 2000.00,
                        }
                    ),
                ],
            },
            "demo_move_refund_01": {
                "move_type": "out_refund",
                "partner_id": "base.res_partner_2",
                "date": (fields.Date.today() + timedelta(days=-3)).strftime("%Y-%m-%d"),
                "invoice_date": (fields.Date.today() + timedelta(days=-3)).strftime(
                    "%Y-%m-%d"
                ),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Demo Discount - FX Difference",
                            "quantity": 1,
                            "price_unit": 100.00,
                        }
                    ),
                ],
            },
        }

    @api.model
    def _prepare_demo_data_payment(self, company=False):
        payment_journal = self.env["account.journal"].search(
            [
                ("type", "in", ["bank", "cash"]),
                ("company_id", "=", (company or self.env.company).id),
            ],
            limit=1,
        )

        return {
            "demo_payment_01": {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": "base.res_partner_2",
                "amount": 1500.00,
                "date": fields.Date.today().strftime("%Y-%m-%d"),
                "journal_id": payment_journal.id if payment_journal else False,
            },
            "demo_payment_02": {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": "base.res_partner_3",
                "amount": 3000.00,
                "date": (fields.Date.today() + timedelta(days=-5)).strftime("%Y-%m-%d"),
                "journal_id": payment_journal.id if payment_journal else False,
            },
        }

    @api.model
    def _prepare_demo_data_statement_line(self, company=False):
        bank_journal = self.env["account.journal"].search(
            [
                ("type", "=", "bank"),
                ("company_id", "=", (company or self.env.company).id),
            ],
            limit=1,
        )

        if not bank_journal:
            _logger.warning(
                "No bank journal found for demo data - skipping statement lines"
            )
            return {}

        return {
            "demo_bank_statement_line_01": {
                "journal_id": bank_journal.id,
                "payment_ref": "DEMO-BANK-PAYMENT-001",
                "partner_id": "base.res_partner_2",
                "amount": 1500.00,
                "date": fields.Date.today().strftime("%Y-%m-%d"),
            },
            "demo_bank_statement_line_02": {
                "journal_id": bank_journal.id,
                "payment_ref": "DEMO-BANK-PAYMENT-002",
                "partner_id": "base.res_partner_4",
                "amount": -2000.00,
                "date": (fields.Date.today() + timedelta(days=-2)).strftime("%Y-%m-%d"),
            },
            "demo_bank_statement_line_03": {
                "journal_id": bank_journal.id,
                "payment_ref": "DEMO-CASH-DEPOSIT-001",
                "amount": 5000.00,
                "date": fields.Date.today().strftime("%Y-%m-%d"),
            },
            "demo_bank_statement_line_04": {
                "journal_id": bank_journal.id,
                "payment_ref": "DEMO-FX-PAYMENT-AGRO",
                "partner_id": "base.res_partner_3",
                "amount": 3500.00,
                "date": (fields.Date.today() + timedelta(days=-5)).strftime("%Y-%m-%d"),
            },
        }
