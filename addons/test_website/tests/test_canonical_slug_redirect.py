from odoo.libs.json import loads as json_loads
from odoo.tests import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestCanonicalSlugRedirect(HttpCase):

    EP = "/ignore_args/converteronly/"

    def _serve(self, encoded_segment):
        return self.url_open(self.EP + encoded_segment, allow_redirects=False)

    def test_percent_escape_lookalike_segments_do_not_loop(self):
        for encoded, expected in [
            ("a%2520b", "a%20b"),
            ("a%252Bb", "a%2Bb"),
            ("a%2520b%2520c", "a%20b%20c"),
            ("a%253Db", "a%3Db"),
        ]:
            with self.subTest(segment=encoded):
                response = self._serve(encoded)
                self.assertEqual(
                    response.status_code,
                    200,
                    "must be served, not 301'd back at itself",
                )
                self.assertEqual(json_loads(response.content)["a"], expected)

    def test_ordinary_segments_are_still_served(self):
        for encoded, expected in [
            ("plain", "plain"),
            ("a%2Bb", "a+b"),
            ("a%20b", "a b"),
            ("caf%C3%A9", "café"),
        ]:
            with self.subTest(segment=encoded):
                response = self._serve(encoded)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(json_loads(response.content)["a"], expected)

    def test_bare_id_is_still_canonicalised(self):
        country = self.env["res.country"].search([("code", "=", "AD")], limit=1)
        self.assertTrue(country, "res.country AD is a base data record")
        response = self.url_open(
            "/test_lang_url/%s" % country.id, allow_redirects=False
        )
        self.assertEqual(response.status_code, 301)
        self.assertURLEqual(
            response.headers.get("Location"),
            "/test_lang_url/%s" % self.env["ir.http"]._slug(country),
        )
