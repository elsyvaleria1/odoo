from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAccessDecisionsIgnoreTheCache(TransactionCase):
    # a read raises only when the value is fetched: once a sudo read has
    # cached it, the same read returns it. A decision taken by trying the read
    # therefore depends on what ran before; each case below is judged with
    # the value cached and without

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login="decisions",
            groups="base.group_user,base.group_erp_manager",
        )
        cls.parameter = cls.env["ir.config_parameter"].create(
            {"key": "decisions.hidden", "value": "x"}
        )
        cls.xid = cls.env["ir.model.data"].create(
            {
                "module": "base",
                "name": "decisions_hidden",
                "model": "ir.config_parameter",
                "res_id": cls.parameter.id,
            }
        )

    def test_an_xml_id_of_a_record_its_reader_cannot_read_shows_its_own_name(self):
        self.assertTrue(self.xid.with_user(self.user).has_access("read"))
        self.assertFalse(
            self.parameter.with_user(self.user).has_access("read"),
            "the premise: the reader reads xml ids, not system parameters",
        )
        for cached in (False, True):
            with self.subTest(cached=cached):
                self.env.invalidate_all()
                if cached:
                    self.parameter.sudo().mapped("display_name")
                xid = self.xid.with_user(self.user)
                self.assertEqual(xid.display_name, xid.complete_name)
