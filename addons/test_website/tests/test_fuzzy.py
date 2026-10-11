import logging

import psycopg

import odoo.tests
from odoo.tests.common import TransactionCase

from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.website.controllers.main import Website

_logger = logging.getLogger(__name__)


@odoo.tests.tagged("-at_install", "post_install")
class TestAutoComplete(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].browse(1)
        cls.WebsiteController = Website()

    def _autocomplete(
        self,
        term,
        expected_count,
        expected_fuzzy_term,
        search_type="test",
        options=None,
    ):
        with MockRequest(self.env, website=self.website):
            suggestions = self.WebsiteController.autocomplete(
                search_type=search_type,
                term=term,
                max_nb_chars=50,
                options=options or {},
            )
        self.assertEqual(
            expected_count, suggestions["results_count"], "Wrong number of suggestions"
        )
        self.assertEqual(
            expected_fuzzy_term,
            suggestions["fuzzy_search"],
            "Wrong fuzzy match",
        )

    def _autocomplete_page(self, term, expected_count, expected_fuzzy_term):
        self._autocomplete(
            term,
            expected_count,
            expected_fuzzy_term,
            search_type="pages",
            options={
                "displayDescription": False,
                "displayDetail": False,
                "displayExtraDetail": False,
                "displayExtraLink": False,
                "displayImage": False,
                "allowFuzzy": True,
            },
        )

    def test_01_many_records(self):
        data = [
            {
                "name": "REF%s" % count,
                "is_published": True,
            }
            for count in range(1000, 4000)
        ]
        self.env["test.model"].create(data)
        data = [
            {
                "name": "NUM%s" % count,
                "is_published": True,
            }
            for count in range(1000, 1999)
        ]
        self.env["test.model"].create(data)
        self._autocomplete("REF3000", 1, False)
        self._autocomplete(
            "RED3000", 1, "ref3000" if self.env.registry.has_trigram else "ref1003"
        )
        self._autocomplete("REF300", 10, False)
        self._autocomplete("REF1", 1000, False)
        self._autocomplete("REFX", 0, None)
        self._autocomplete("REF1230", 1, False)
        self._autocomplete("REF2230", 1, False)

        self._autocomplete("NUM000", 1, "num1000")
        self._autocomplete("NUM100", 10, False)
        self._autocomplete("NUM199", 9, False)
        self._autocomplete("NUM1998", 1, False)
        self._autocomplete("NUM1999", 1, "num1199")
        self._autocomplete("NUM200", 1, "num1200")

        self._autocomplete("XEF1000", 0, None)

    def test_02_pages_search(self):
        if not self.env.registry.has_trigram:
            try:
                self.env.cr.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                self.env.registry.has_trigram = True
            except psycopg.Error:
                _logger.warning(
                    "pg_trgm extension can't be installed, which is required to run this test"
                )
                return

        with MockRequest(self.env, website=self.env["website"].browse(1)):
            self.env["website"].browse(1)._search_with_fuzzy(
                "pages",
                "test",
                limit=5,
                order="name asc, website_id desc, id",
                options={
                    "displayDescription": False,
                    "displayDetail": False,
                    "displayExtraDetail": False,
                    "displayExtraLink": False,
                    "displayImage": False,
                    "allowFuzzy": True,
                },
            )

        test_page = self.env.ref("test_website.test_page")
        test_page.name = "testTotallyUnique"

        self._autocomplete_page("testTotallyUnique", 1, False)

        test_page.visibility = "connected"
        self._autocomplete_page("testTotallyUnique", 1, False)
        test_page.visibility = False

        test_page.group_ids = self.env.ref("base.group_public")
        self._autocomplete_page("testTotallyUnique", 1, False)
        test_page.group_ids = False

        saved_env = self.env
        self.website.env = self.env = self.env(user=self.website.user_id)
        self._autocomplete_page("testTotallyUnique", 0, None)

        test_page.website_indexed = True
        self._autocomplete_page("testTotallyUnique", 1, False)

        test_page.group_ids = self.env.ref("base.group_system")
        self._autocomplete_page("testTotallyUnique", 0, None)

        test_page.group_ids = self.env.ref("base.group_public")
        self._autocomplete_page("testTotallyUnique", 1, False)
        test_page.group_ids = False

        test_page.visibility = "password"
        self._autocomplete_page("testTotallyUnique", 0, None)

        test_page.visibility = "connected"
        self._autocomplete_page("testTotallyUnique", 0, None)

        self.website.env = self.env = saved_env

    def test_indirect(self):
        self._autocomplete("module", 4, "model")
        self._autocomplete("rechord", 3, "record")
        self._autocomplete("suborder", 1, "submodel")
        self._autocomplete("tagg", 0, None)
