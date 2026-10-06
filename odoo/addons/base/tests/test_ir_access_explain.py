from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestExplainRecord(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env["res.groups"].create({"name": "Probe: industry readers"})
        cls.reader = new_test_user(cls.env, login="reader", groups="base.group_user")
        cls.reader.group_ids = [(4, cls.group.id)]
        cls.outsider = new_test_user(
            cls.env, login="outsider", groups="base.group_portal"
        )
        cls.admin = new_test_user(
            cls.env, login="access_admin", groups="base.group_erp_manager"
        )
        model_id = cls.env["ir.model"]._get_id("res.partner.industry")
        Access = cls.env["ir.access"]
        cls.permission = Access.create(
            {
                "name": "Probe: readers read the a-industries",
                "model_id": model_id,
                "group_id": cls.group.id,
                "kind": "permission",
                "operation": "r",
                "domain": "[('name', '=like', 'a%')]",
            }
        )
        cls.guard = Access.create(
            {
                "name": "Probe: nobody reads a blocked industry",
                "model_id": model_id,
                "group_id": cls.env.ref("base.group_everyone").id,
                "kind": "guard",
                "operation": "r",
                "domain": "[('name', '!=', 'a blocked one')]",
            }
        )
        Industry = cls.env["res.partner.industry"]
        cls.readable = Industry.create({"name": "agriculture"})
        cls.blocked = Industry.create({"name": "a blocked one"})
        cls.unreached = Industry.create({"name": "banking"})

    def explain(self, user, record, operation="read"):
        return (
            self.env["ir.access"]
            .with_user(user)
            ._explain_record(record.with_user(user), operation)
        )

    def entry(self, entries, row):
        [found] = [entry for entry in entries if entry["row"] == row.id]
        return found

    def test_a_reached_record_names_the_permission_and_its_grant(self):
        explanation = self.explain(self.reader, self.readable)
        self.assertTrue(explanation["allowed"])
        permission = self.entry(explanation["permissions"], self.permission)
        self.assertTrue(permission["admits"])
        [grant] = [
            grant
            for grant in permission["held_through"]
            if grant["group"] == self.group.id
        ]
        self.assertEqual(grant["cause"], "manual")
        self.assertTrue(self.entry(explanation["guards"], self.guard)["admits"])

    def test_a_refusing_guard_is_the_one_that_does_not_admit(self):
        explanation = self.explain(self.reader, self.blocked)
        self.assertFalse(explanation["allowed"])
        self.assertTrue(
            self.entry(explanation["permissions"], self.permission)["admits"]
        )
        self.assertFalse(self.entry(explanation["guards"], self.guard)["admits"])

    def test_the_explanation_agrees_with_the_decision_on_every_record(self):
        Access = self.env["ir.access"]
        records = self.env["res.partner.industry"].search([])
        for user in (self.reader, self.admin, self.outsider):
            for record in records:
                mine = record.with_user(user)
                explanation = self.explain(user, record)
                self.assertEqual(explanation["allowed"], mine.has_access("read"))
                if explanation["allowed"] or not explanation["model_allowed"]:
                    continue
                failing = {
                    row.name
                    for row in Access.with_user(user)._get_failed_accesses(mine, "read")
                }
                refusing = {
                    entry["name"]
                    for entry in explanation["guards"]
                    if not entry["admits"]
                }
                if not any(entry["admits"] for entry in explanation["permissions"]):
                    refusing |= {entry["name"] for entry in explanation["permissions"]}
                self.assertEqual(refusing, failing, f"{user.login} on {record.name}")

    def test_who_can_is_the_users_the_decision_lets_through(self):
        who = {
            entry["user"]
            for entry in self.env["ir.access"]._who_can(self.readable, "read")
        }
        self.assertIn(self.reader.id, who)
        self.assertNotIn(self.outsider.id, who)
        self.assertNotIn(
            self.reader.id,
            {
                entry["user"]
                for entry in self.env["ir.access"]._who_can(self.blocked, "read")
            },
        )

    def test_explaining_someone_else_is_an_administrators_and_logged(self):
        Explain = self.env["wizard.base.explain.access"]
        record_ref = f"res.partner.industry,{self.readable.id}"
        nosy = Explain.with_user(self.reader).create(
            {"user_id": self.admin.id, "record_ref": record_ref}
        )
        with self.assertRaises(AccessError):
            nosy.action_explain()
        with self.assertRaises(AccessError):
            Explain.with_user(self.reader).create(
                {"record_ref": record_ref}
            ).action_who_can()
        Explain.with_user(self.admin).create(
            {"user_id": self.reader.id, "record_ref": record_ref}
        ).action_explain()
        log = self.env["ir.access.log"].search(
            [("event", "=", "explained_other"), ("actor_id", "=", self.admin.id)]
        )
        self.assertEqual(log.subject_user_id, self.reader)
        self.assertEqual(log.res_ids, str(self.readable.id))

    def test_a_person_is_told_whom_to_ask_and_an_administrator_the_rows(self):
        Explain = self.env["wizard.base.explain.access"]
        mine = Explain.with_user(self.reader).create(
            {"record_ref": f"res.partner.industry,{self.blocked.id}"}
        )
        mine.action_explain()
        self.assertIn("may not read a record you cannot read", mine.explanation)
        self.assertIn(f"Refused by: {self.guard.name}", mine.explanation)
        self.assertIn("Ask:", mine.explanation)
        self.assertNotIn(self.permission.name, mine.explanation)
        theirs = Explain.with_user(self.admin).create(
            {
                "user_id": self.reader.id,
                "record_ref": f"res.partner.industry,{self.blocked.id}",
            }
        )
        theirs.action_explain()
        self.assertIn(f"! {self.guard.name}: refuses", theirs.explanation)
        self.assertIn(f"+ {self.permission.name}: reaches it", theirs.explanation)

    def test_the_access_error_names_the_refusing_guard_and_whom_to_ask(self):
        self.reader.group_ids = [(4, self.env.ref("base.group_no_one").id)]
        blocked = self.blocked.with_user(self.reader)
        with self.assertRaises(AccessError) as refusal:
            blocked.read(["name"])
        message = refusal.exception.args[0]
        self.assertIn(f"Refused by: {self.guard.name}", message)
        self.assertIn("Ask: ", message)
        self.assertNotIn("Blame the following accesses", message)
        with self.debug_mode(), self.assertRaises(AccessError) as refusal:
            blocked.read(["name"])
        self.assertIn("Blame the following accesses", refusal.exception.args[0])
