import hashlib
import threading
import time
from types import SimpleNamespace

from odoo.http.core import _request_stack
from odoo.tests import TransactionCase, tagged

from odoo.addons.web.controllers.binary import Binary

BUNDLE = "web.assets_frontend"
FILENAME = f"{BUNDLE}.min.css"
URL_PATTERN = f"/web/assets/%/{FILENAME}"


@tagged("post_install", "-at_install", "web_assets")
class TestConcurrentAssetGeneration(TransactionCase):
    def _get_committed_attachment_ids(self, cr):
        cr.execute(
            "SELECT id FROM ir_attachment WHERE url LIKE %s ORDER BY id", [URL_PATTERN]
        )
        return [row[0] for row in cr.fetchall()]

    def _generate(self, version, outcome):
        with self.registry.cursor(readonly=True) as request_cr:
            _request_stack.push(
                SimpleNamespace(env=self.env(cr=request_cr), session={})
            )
            try:
                Binary()._get_generated_asset_stream(FILENAME, version, False, {})
            finally:
                _request_stack.pop()
        outcome["done"] = True

    def test_a_request_queued_on_the_lock_reuses_what_the_holder_saved(self):
        digest = hashlib.blake2b(FILENAME.encode(), digest_size=8).digest()
        with self.leave_registry_test_mode():
            with self.registry.cursor() as cr:
                cr.execute("DELETE FROM ir_attachment WHERE url LIKE %s", [URL_PATTERN])
            outcome = {}
            with self.registry.cursor() as holder:
                holder.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    [int.from_bytes(digest, "big", signed=True)],
                )
                bundle = self.env(cr=holder)["ir.qweb"]._get_asset_bundle(
                    BUNDLE, css=True, js=False
                )
                saved = bundle.css()
                queued = threading.Thread(
                    target=self._generate, args=(bundle.get_version("css"), outcome)
                )
                queued.start()
                time.sleep(0.5)
                self.assertTrue(queued.is_alive(), "the request waits on the lock")
                holder.commit()
            queued.join(60)
            with self.registry.cursor() as cr:
                committed = self._get_committed_attachment_ids(cr)
        self.assertEqual(outcome, {"done": True})
        self.assertEqual(
            committed,
            [saved.id],
            "the queued request read under the lock a snapshot older than the "
            "holder's commit, and generated and stored the bundle again",
        )
