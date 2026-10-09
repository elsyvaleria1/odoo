import lxml.html

from odoo.tests import tagged

from odoo.addons.website.tests.test_lang_url import TestLangUrlCommon

HEADER = {"X-Odoo-Partial-Navigation": "website.list_website_public_pages"}


@tagged("-at_install", "post_install")
class TestPartialNavigationResponse(TestLangUrlCommon):
    def _page(self, url, headers=None):
        response = self.url_open(url, headers=headers)
        self.assertEqual(response.status_code, 200)
        return response, lxml.html.fromstring(response.content)

    def test_a_page_asked_in_place_leaves_out_header_and_footer(self):
        _response, full = self._page("/pages")
        response, partial = self._page("/pages", HEADER)

        self.assertTrue(full.xpath("//header[@id='top']"))
        self.assertTrue(full.xpath("//footer[@id='bottom']"))
        self.assertFalse(partial.xpath("//header[@id='top']"))
        self.assertFalse(partial.xpath("//footer[@id='bottom']"))
        self.assertTrue(
            partial.xpath("//*[@data-fragment='website.list_website_public_pages']")
        )
        self.assertIn("X-Odoo-Partial-Navigation", response.headers.get("Vary", ""))

    def test_the_language_links_come_along_without_the_header(self):
        _response, full = self._page("/pages?search=contact")
        _response, partial = self._page("/pages?search=contact", HEADER)

        def links(tree):
            return {
                a.get("data-fragment"): a.get("href")
                for a in tree.xpath("//a[@data-partial-navigation-oob='href']")
            }

        self.assertEqual(
            links(partial),
            links(full),
            "the carrier holds the same targets as the header's language links",
        )
        self.assertEqual(
            links(partial)["portal.language_link.fr"], "/fr/pages?search=contact"
        )

    def test_a_cached_page_is_not_served_to_the_other_kind_of_request(self):
        _response, full = self._page("/contactus")
        _response, partial = self._page("/contactus", HEADER)
        _response, full_again = self._page("/contactus")

        self.assertTrue(full.xpath("//header[@id='top']"))
        self.assertFalse(partial.xpath("//header[@id='top']"))
        self.assertTrue(full_again.xpath("//header[@id='top']"))
