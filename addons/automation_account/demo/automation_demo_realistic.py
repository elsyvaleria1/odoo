import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AutomationRule(models.Model):
    _inherit = "automation.rule"

    @api.model
    def _install_realistic_demo_data(self, company=False):
        _logger.warning("=" * 80)
        _logger.warning("REALISTIC DEMO DATA INSTALLATION STARTED!")
        _logger.warning("This will execute actual workflows to create demo data")
        _logger.warning("=" * 80)

        try:
            self._create_completed_cash_exchange(company)

            self._create_partial_collection_in_kind(company)

            self._create_completed_fx_discount(company)

            self._create_multiple_parallel_workflows(company)

            _logger.info("✓ Realistic demo data installation completed successfully!")
            return True

        except Exception:
            _logger.exception("Failed to install realistic demo data")
            _logger.warning(
                "Skipping realistic demo data due to error (this is non-critical)"
            )
            return False

    def _create_completed_cash_exchange(self, company=False):
        _logger.info("Creating completed cash exchange workflow...")

        try:
            automation = self.env.ref(
                "automation_account.automation_cash_exchange_simple",
                raise_if_not_found=False,
            )
            if not automation:
                _logger.warning("Automation not found, skipping")
                return

            partner = self.env.ref("base.res_partner_2", raise_if_not_found=False)
            if not partner:
                partner = self.env["res.partner"].search([], limit=1)

            runtime = self.env["automation.runtime"].create(
                {
                    "automation_id": automation.id,
                    "partner_id": partner.id,
                    "amount": 1500.00,
                    "date": fields.Date.today(),
                    "reference": "REALISTIC-DEMO-CASH-001",
                }
            )

            runtime.action_start()
            _logger.info("  ✓ Workflow started with %d actions", len(runtime.line_ids))

            step = 0
            while runtime.state == "in_progress" and step < 10:
                step += 1
                _logger.info("  Executing step %d...", step)
                try:
                    runtime.action_next_step()
                except (UserError, ValidationError) as e:
                    _logger.warning("  Step %d failed: %s (continuing)", step, e)
                    break

            _logger.info(
                "  ✓ Workflow completed: state=%s, progress=%d%%",
                runtime.state,
                runtime.progress,
            )

            self.env["ir.model.data"].create(
                {
                    "name": "demo_runtime_realistic_completed_cash",
                    "module": "automation_account",
                    "model": "automation.runtime",
                    "res_id": runtime.id,
                    "noupdate": True,
                }
            )

        except Exception:
            _logger.exception("Failed to create completed cash exchange")

    def _create_partial_collection_in_kind(self, company=False):
        _logger.info("Creating partial collection in kind workflow...")

        try:
            automation = self.env.ref(
                "automation_account.automation_collection_in_kind",
                raise_if_not_found=False,
            )
            if not automation:
                _logger.warning("Automation not found, skipping")
                return

            partner = self.env.ref("base.res_partner_12", raise_if_not_found=False)
            if not partner:
                partner = self.env["res.partner"].search([], limit=1)

            runtime = self.env["automation.runtime"].create(
                {
                    "automation_id": automation.id,
                    "partner_id": partner.id,
                    "amount": 2500.00,
                    "date": fields.Date.today(),
                    "reference": "REALISTIC-DEMO-COLLECTION-001",
                }
            )

            runtime.action_start()

            try:
                runtime.action_next_step()
                _logger.info("  ✓ Executed first action, leaving workflow in progress")
            except (UserError, ValidationError) as e:
                _logger.warning("  First step failed: %s", e)

            _logger.info("  ✓ Partial workflow created: state=%s", runtime.state)

            self.env["ir.model.data"].create(
                {
                    "name": "demo_runtime_realistic_partial_collection",
                    "module": "automation_account",
                    "model": "automation.runtime",
                    "res_id": runtime.id,
                    "noupdate": True,
                }
            )

        except Exception:
            _logger.exception("Failed to create partial collection")

    def _create_completed_fx_discount(self, company=False):
        _logger.info("Creating completed FX discount workflow...")

        try:
            automation = self.env.ref(
                "automation_account.automation_customer_discount_fx",
                raise_if_not_found=False,
            )
            if not automation:
                _logger.warning("Automation not found, skipping")
                return

            partner = self.env.ref("base.res_partner_2", raise_if_not_found=False)
            if not partner:
                partner = self.env["res.partner"].search([], limit=1)

            journal_bank = self.env["account.journal"].search(
                [
                    ("type", "=", "bank"),
                    ("company_id", "=", (company or self.env.company).id),
                ],
                limit=1,
            )

            st_line = None
            if journal_bank:
                st_line = self.env["account.bank.statement.line"].create(
                    {
                        "journal_id": journal_bank.id,
                        "payment_ref": "REALISTIC-FX-PAYMENT-001",
                        "partner_id": partner.id,
                        "amount": 2000.00,
                        "date": fields.Date.today(),
                    }
                )
                _logger.info("  ✓ Created bank statement line")

            runtime_vals = {
                "automation_id": automation.id,
                "partner_id": partner.id,
                "amount": 2000.00,
                "date": fields.Date.today(),
                "reference": "REALISTIC-DEMO-FX-001",
            }
            if st_line:
                runtime_vals["st_line_id"] = st_line.id

            runtime = self.env["automation.runtime"].create(runtime_vals)

            runtime.action_start()

            step = 0
            while runtime.state == "in_progress" and step < 10:
                step += 1
                try:
                    runtime.action_next_step()
                except (UserError, ValidationError) as e:
                    _logger.warning("  Step %d failed: %s (continuing)", step, e)
                    break

            _logger.info("  ✓ FX workflow completed: state=%s", runtime.state)

            self.env["ir.model.data"].create(
                {
                    "name": "demo_runtime_realistic_fx_discount",
                    "module": "automation_account",
                    "model": "automation.runtime",
                    "res_id": runtime.id,
                    "noupdate": True,
                }
            )

        except Exception:
            _logger.exception("Failed to create FX discount workflow")

    def _create_multiple_parallel_workflows(self, company=False):
        _logger.info("Creating multiple parallel workflows...")

        try:
            automation = self.env.ref(
                "automation_account.automation_cash_exchange_simple",
                raise_if_not_found=False,
            )
            if not automation:
                _logger.warning("Automation not found, skipping")
                return

            partners = self.env["res.partner"].search(
                [("customer_rank", ">", 0)], limit=3
            )
            if not partners:
                partners = self.env["res.partner"].search([], limit=3)

            for i, partner in enumerate(partners):
                runtime = self.env["automation.runtime"].create(
                    {
                        "automation_id": automation.id,
                        "partner_id": partner.id,
                        "amount": 1000.00 + (i * 500),
                        "date": fields.Date.today() + timedelta(days=-i),
                        "reference": f"REALISTIC-DEMO-PARALLEL-{i:03d}",
                    }
                )

                runtime.action_start()
                _logger.info(
                    "  ✓ Created parallel workflow %d for %s",
                    i + 1,
                    partner.name,
                )

            _logger.info("  ✓ Created %d parallel workflows", len(partners))

        except Exception:
            _logger.exception("Failed to create parallel workflows")

    @api.model
    def _check_demo_data_integrity(self):
        _logger.info("Validating realistic demo data integrity...")

        issues = []

        completed = self.env.ref(
            "automation_account.demo_runtime_realistic_completed_cash",
            raise_if_not_found=False,
        )
        if completed:
            if completed.state != "done":
                issues.append(f"Completed workflow not done: state={completed.state}")
            if completed.progress != 100:
                issues.append(
                    f"Completed workflow progress != 100: {completed.progress}"
                )
        else:
            issues.append("Completed cash exchange demo not found")

        partial = self.env.ref(
            "automation_account.demo_runtime_realistic_partial_collection",
            raise_if_not_found=False,
        )
        if partial:
            if partial.state not in ["in_progress", "done"]:
                issues.append(f"Partial workflow unexpected state: {partial.state}")
        else:
            issues.append("Partial collection demo not found")

        if issues:
            _logger.warning("Demo data integrity issues found:")
            for issue in issues:
                _logger.warning("  - %s", issue)
        else:
            _logger.info("✓ Demo data integrity validation passed!")

        return len(issues) == 0
