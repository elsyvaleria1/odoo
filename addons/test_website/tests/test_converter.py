import threading
from contextlib import contextmanager

from odoo.tests.common import TransactionCase, tagged


@contextmanager
def _thread_without_database():
    thread = threading.current_thread()
    dbname = thread.dbname
    del thread.dbname
    try:
        yield
    finally:
        thread.dbname = dbname


@tagged("post_install", "-at_install")
class TestConverterOffRequestThread(TransactionCase):
    def test_view_depends_check_builds_the_routing_map_without_a_thread_database(self):
        self.env.registry.clear_cache("routing")
        with _thread_without_database():
            undeclared = self.registry.get_undeclared_view_reads(
                self.env.cr, ["website.technical.page"]
            )
            routing_map = self.env["ir.http"].routing_map()
        self.assertEqual(undeclared, {})
        rule = next(
            rule
            for rule in routing_map.iter_rules()
            if rule.rule == '/test_website/country/<model("res.country"):country>'
        )
        country = self.env.ref("base.be")
        self.assertEqual(
            rule._converters["country"].to_url(country), f"belgium-{country.id}"
        )
