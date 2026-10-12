import logging
import os

from odoo.tests import TransactionCase, tagged

from odoo.addons.base.tests import access_property

_logger = logging.getLogger(__name__)
ROUNDS = int(os.environ.get("ACCESS_PROPERTY_ROUNDS", "12"))


@tagged("post_install", "-at_install")
class TestAccessProperty(TransactionCase):
    def _run(self, seed):
        result = access_property.run(
            self.env,
            "test_access_right.property_doc",
            seed=seed,
            rounds=ROUNDS,
            records=60,
        )
        _logger.info(
            "access property, PostgreSQL: seed=%s rounds=%s rows=%s cases=%s "
            "divergences=%s visible=%s of %s",
            seed,
            result["rounds"],
            result["rows"],
            result["cases"],
            len(result["divergences"]),
            result["visible"],
            result["records"],
        )
        self.assertTrue(result["cases"])
        self.assertTrue(result["visible"][2], "no principal saw anything")
        self.assertFalse(result["divergences"], result["divergences"][:10])

    def test_seed_1(self):
        self._run(1)

    def test_seed_2(self):
        self._run(2)

    def test_seed_3(self):
        self._run(3)
