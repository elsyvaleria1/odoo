from odoo.tests import TransactionCase


class TestSalaryBenefit(TransactionCase):
    """Cover `_compute_field`, which decides where a benefit reads and writes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.benefit_type = cls.env["hr.contract.salary.benefit.type"].create({})
        cls.structure_type = cls.env["hr.payroll.structure.type"].search([], limit=1)
        cls.wage_field = cls.env["ir.model.fields"]._get("hr.version", "wage")
        cls.salary_rule = cls.env["hr.salary.rule"].search([], limit=1)

    def _benefit(self, source):
        return self.env["hr.contract.salary.benefit"].create(
            {
                "benefit_type_id": self.benefit_type.id,
                "structure_type_id": self.structure_type.id,
                "display_type": "always",
                "source": source,
                "res_field_id": self.wage_field.id,
                "salary_rule_id": self.salary_rule.id,
            }
        )

    def test_switching_the_source_moves_the_field(self):
        """`field` must follow `source`, which the compute branches on.

        `source` was in no dependency - not this module's, not the parent's -
        so a benefit switched between sources kept the other one's field name.
        The stale name is what `_prepare_benefit_vals` writes through, and it
        never checks `source`, so a rule benefit still carrying `wage` had the
        submitted amount written onto the version's wage.
        """
        benefit = self._benefit("field")
        self.env.flush_all()
        self.assertEqual(benefit.field, self.wage_field.name)

        # Only `source` changes. No explicit invalidation: the depends must do
        # the work, and the stale value used to survive one anyway.
        benefit.write({"source": "rule"})
        self.env.flush_all()
        self.assertEqual(
            benefit.field,
            self.salary_rule.code,
            "a rule-sourced benefit must read its salary rule, not the old field",
        )

        benefit.write({"source": "field"})
        self.env.flush_all()
        self.assertEqual(
            benefit.field,
            self.wage_field.name,
            "and back again, so the fix is not one-directional",
        )


class TestSimulationOfferCleanup(TransactionCase):
    """Characterise the cron: it is the only method here that deletes."""

    def _offer(self, is_simulation, months_old=0):
        offer = self.env["hr.contract.salary.offer"].create(
            {"is_simulation_offer": is_simulation, "final_yearly_costs": 30000.0}
        )
        self.env.flush_all()
        if months_old:
            # `create_date` is not writable through the ORM.
            self.env.cr.execute(
                "UPDATE hr_contract_salary_offer SET create_date = now() - %s::interval WHERE id = %s",
                ("%s months" % months_old, offer.id),
            )
            offer.invalidate_recordset(["create_date"])
        return offer

    def test_the_cron_removes_only_aged_simulation_offers(self):
        old_simulation = self._offer(True, months_old=3)
        fresh_simulation = self._offer(True)
        old_real_offer = self._offer(False, months_old=3)

        self.env["hr.contract.salary.offer"].action_cron_remove_simulation_offers()
        self.env.flush_all()

        self.assertFalse(
            old_simulation.exists(),
            "a simulation offer past the one-month cutoff is the whole point",
        )
        self.assertTrue(
            fresh_simulation.exists(),
            "a recent simulation offer must survive",
        )
        self.assertTrue(
            old_real_offer.exists(),
            "a real offer must never be touched, however old",
        )
