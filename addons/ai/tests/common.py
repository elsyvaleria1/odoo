from odoo.tests import TransactionCase


class AICommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_user = cls.env["res.users"].create(
            {
                "name": "Test User",
                "login": "user",
                "email": "user@user.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
