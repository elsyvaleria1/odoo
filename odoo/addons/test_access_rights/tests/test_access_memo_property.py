import logging

from odoo.tests import TransactionCase, tagged

from odoo.addons.base.tests import access_memo_property

_logger = logging.getLogger(__name__)
# two seeds per theme; ACCESS_MEMO_PROPERTY_SEEDS and _STEPS run a campaign,
# and access_memo_property.SCOPE_EPISODES sets how often an episode fills a
# user x2many slot and changes a line of it behind the ORM
SEEDS = range(
    1, (access_memo_property.SEEDS or 2 * len(access_memo_property.THEMES)) + 1
)
STEPS = access_memo_property.LONG or 140
NAMES = {
    "folder": "test_access_right.memo_folder",
    "doc": "test_access_right.memo_doc",
    "line": "test_access_right.memo_line",
    "tag": "test_access_right.memo_tag",
}


@tagged("post_install", "-at_install")
class TestAccessMemoProperty(TransactionCase):
    # the property's PostgreSQL leg: the memo under test reads the rows the
    # transaction wrote, the principal from scratch reads them back through
    # SQL, and the record verdicts are also the access domain searched in SQL

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.world = access_memo_property.build_world(
            cls.env, NAMES, "test_access_rights.memo_note", sql=True
        )

    def test_every_memoized_verdict_equals_the_verdict_from_scratch(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                stats, divergence = access_memo_property.campaign(
                    self.world, seed, STEPS
                )
                _logger.info("access memo property, PostgreSQL: %s", stats)
                self.assertTrue(stats["checks"])
                self.assertIsNone(divergence, divergence)
