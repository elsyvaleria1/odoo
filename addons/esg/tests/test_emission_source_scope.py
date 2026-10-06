from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEmissionSourceScope(TransactionCase):
    def test_a_child_source_takes_its_parents_scope(self):
        parent = self.env["esg.emission.source"].create(
            {"name": "Purchased electricity", "scope": "indirect"}
        )

        child = self.env["esg.emission.source"].create(
            {"name": "Office electricity", "parent_id": parent.id}
        )

        self.assertEqual(child.scope, "indirect")

    def test_a_source_without_parent_is_direct(self):
        source = self.env["esg.emission.source"].create({"name": "Boiler"})

        self.assertEqual(source.scope, "direct")
