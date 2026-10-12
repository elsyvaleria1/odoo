import re

from odoo.tests.common import HttpCase, tagged


@tagged("-standard", "external", "post_install", "-at_install")
class TestDocLinks(HttpCase):
    def setUp(self):
        super().setUp()
        self.re = re.compile(r'<a href="(\S+/documentation/\S+)"')
        self.links = set()

    def test_01_links(self):
        self._parse_view(self.env.ref("helpdesk.helpdesk_team_view_form"))

        for link in self.links:
            self._check_link(link)

    def _check_link(self, link):
        res = self.url_open(url=link)

        self.assertEqual(
            res.status_code, 200, "The following link is broken: '%s'" % (link)
        )

    def _parse_view(self, view):

        for match in re.finditer(self.re, view.arch):
            self.links.add(match.group(1))

        for child in view.inherit_children_ids:
            self._parse_view(child)
