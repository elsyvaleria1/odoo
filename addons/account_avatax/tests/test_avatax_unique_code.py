from odoo.tests.common import tagged

from .common import TestAccountAvataxCommon


@tagged("-at_install", "post_install")
class TestAvataxUniqueCode(TestAccountAvataxCommon):
    @classmethod
    def setUpClass(cls):
        res = super().setUpClass()
        cls.partner_1 = cls.env["res.partner"].create({"name": "partner bob"})
        cls.partner_2 = cls.env["res.partner"].create({"name": "partner alice"})
        return res

    def _search_equal_and_return(self, term):
        return self.env["res.partner"].search([("avatax_unique_code", "=", term)])

    def _search_not_equal_and_return(self, term):
        return self.env["res.partner"].search([("avatax_unique_code", "!=", term)])

    def test_search_equal(self):
        self.assertEqual(
            self._search_equal_and_return(str(self.partner_1.id)), self.partner_1
        )
        self.assertFalse(
            self._search_equal_and_return(f" Contact {self.partner_1.id!s}")
        )

        not_equal = self._search_not_equal_and_return(f"Contact {self.partner_1.id!s}")
        self.assertFalse(self.partner_1 in not_equal)
        self.assertTrue(self.partner_2 in not_equal)

        self.assertFalse(self._search_equal_and_return("Contact"))
        self.assertFalse(
            self._search_equal_and_return(
                f"{self.partner_1.id!s} {self.partner_1.id!s}"
            )
        )

    def _search_ilike_and_return(self, term):
        return self.env["res.partner"].search([("avatax_unique_code", "ilike", term)])

    def _search_not_ilike_and_return(self, term):
        return self.env["res.partner"].search(
            ["!", ("avatax_unique_code", "ilike", term)]
        )

    def test_search_like(self):
        self.assertEqual(
            self._search_ilike_and_return(str(self.partner_1.id)), self.partner_1
        )

        self.assertEqual(
            self._search_ilike_and_return(f"Contact {self.partner_1.id!s}"),
            self.partner_1,
        )

        not_like = self._search_not_ilike_and_return(f"Contact {self.partner_1.id!s}")
        self.assertFalse(self.partner_1 in not_like)
        self.assertTrue(self.partner_2 in not_like)

        self.assertFalse(self._search_ilike_and_return("Contact"))
        self.assertFalse(
            self._search_ilike_and_return(
                f"{self.partner_1.id!s} {self.partner_1.id!s}"
            )
        )

    def test_search_bool(self):
        # searching True is not supported
        self.assertRaises(
            ValueError,
            self.env["res.partner"].search,
            [("avatax_unique_code", "=", True)],
        )
        # searching False results in a True domain
        self.assertTrue(
            self.env["res.partner"]
            ._search([("avatax_unique_code", "=", False)])
            .is_empty()
        )
