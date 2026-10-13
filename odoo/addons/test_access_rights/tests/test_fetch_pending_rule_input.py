from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged

DOC = "test_access_right.memo_doc"


@tagged("post_install", "-at_install")
class TestFetchPendingRuleInput(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env["res.groups"].create({"name": "Pending rule input"})
        cls.user = new_test_user(cls.env, login="pending_rule_input")
        cls.user.group_ids = [Command.link(group.id)]
        for model, domain in (
            (DOC, "[('total', '>', 0)]"),
            ("test_access_right.memo_line", False),
        ):
            cls.env["ir.access"].create(
                {
                    "name": f"pending rule input {model}",
                    "model_id": cls.env["ir.model"]._get_id(model),
                    "group_id": group.id,
                    "operation": "r",
                    "domain": domain,
                }
            )
        cls.doc = cls.env[DOC].create({"name": "d"})
        cls.line = cls.env["test_access_right.memo_line"].create(
            {"doc_id": cls.doc.id, "amount": 1}
        )

    def _as_user(self):
        self.env.flush_all()
        self.env.invalidate_all()
        return self.doc.with_user(self.user)

    def _call_read_and_get_access_denied(self, read) -> bool:
        try:
            read()
        except AccessError:
            return True
        return False

    def test_a_record_the_pending_value_refuses_is_not_fetched(self):
        doc = self._as_user()
        self.line.amount = 0
        self.assertTrue(
            self._call_read_and_get_access_denied(lambda: doc.fetch(["name", "total"]))
        )

    def test_a_record_the_pending_value_refuses_is_not_read(self):
        doc = self._as_user()
        self.line.amount = 0
        self.assertTrue(
            self._call_read_and_get_access_denied(lambda: doc.read(["name", "total"]))
        )

    def test_a_record_the_pending_value_admits_is_read(self):
        self.line.amount = 0
        doc = self._as_user()
        self.line.amount = 2
        doc.fetch(["name", "total"])
        self.assertEqual(doc.read(["name", "total"])[0]["total"], 2)
