import time
from datetime import timedelta
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.tests.common import BaseCase

from odoo.addons.integration.tools.session_cache import SessionCache


class TestSessionCache(BaseCase):
    def setUp(self):
        super().setUp()
        self.cache = SessionCache(max_size=3, ttl_hours=0.001)

    def test_cache_set_get(self):
        self.cache.set("key1", "value1")
        result = self.cache.get("key1")

        self.assertEqual(result, "value1")

    def test_cache_miss(self):
        result = self.cache.get("nonexistent")

        self.assertIsNone(result)

    def test_cache_expiration(self):
        self.cache.set("key1", "value1")

        time.sleep(4)

        result = self.cache.get("key1")

        self.assertIsNone(result)

    def test_cache_lru_eviction(self):
        self.cache.set("key1", "value1")
        self.cache.set("key2", "value2")
        self.cache.set("key3", "value3")

        self.cache.set("key4", "value4")

        self.assertIsNone(self.cache.get("key1"))

        self.assertEqual(self.cache.get("key2"), "value2")
        self.assertEqual(self.cache.get("key3"), "value3")
        self.assertEqual(self.cache.get("key4"), "value4")

    def test_cache_lru_order(self):
        self.cache.set("key1", "value1")
        self.cache.set("key2", "value2")
        self.cache.set("key3", "value3")

        self.cache.get("key1")

        self.cache.set("key4", "value4")

        self.assertEqual(self.cache.get("key1"), "value1")

        self.assertIsNone(self.cache.get("key2"))

    def test_cache_invalidate_single(self):
        self.cache.set("key1", "value1")
        self.cache.set("key2", "value2")

        self.cache.invalidate("key1")

        self.assertIsNone(self.cache.get("key1"))
        self.assertEqual(self.cache.get("key2"), "value2")

    def test_cache_invalidate_all(self):
        self.cache.set("key1", "value1")
        self.cache.set("key2", "value2")

        self.cache.invalidate_all()

        self.assertIsNone(self.cache.get("key1"))
        self.assertIsNone(self.cache.get("key2"))

    def test_cache_stats(self):
        self.cache.set("key1", "value1")
        self.cache.set("key2", "value2")

        stats = self.cache.get_stats()

        self.assertEqual(stats["size"], 2)
        self.assertEqual(stats["max_size"], 3)
        self.assertAlmostEqual(stats["ttl_hours"], 0.001, places=3)


class TestSessionCacheLifetime(BaseCase):
    def _at(self, minutes):
        start = fields.Datetime.to_datetime("2026-10-01 12:00:00")
        return patch.object(
            fields.Datetime, "now", return_value=start + timedelta(minutes=minutes)
        )

    def test_the_ttl_runs_from_creation_not_from_last_use(self):
        cache = SessionCache(max_size=3, ttl_hours=1)
        session = MagicMock()
        with self._at(0):
            cache.set("key", session)
        for minutes in (20, 40, 59):
            with self._at(minutes):
                self.assertIs(cache.get("key"), session)
        with self._at(61):
            self.assertIsNone(cache.get("key"), "an hour after creation, however used")
        session.close.assert_called_once_with()

    def test_an_lru_eviction_closes_the_session(self):
        cache = SessionCache(max_size=1)
        first, second = MagicMock(), MagicMock()
        cache.set("first", first)
        cache.set("second", second)
        first.close.assert_called_once_with()
        second.close.assert_not_called()

    def test_an_invalidation_closes_the_session(self):
        cache = SessionCache(max_size=3)
        one, other, matched = MagicMock(), MagicMock(), MagicMock()
        cache.set("one", one)
        cache.set("other", other)
        cache.set("matched", matched)
        cache.invalidate("one")
        cache.invalidate_matching(lambda key: key == "matched")
        one.close.assert_called_once_with()
        matched.close.assert_called_once_with()
        other.close.assert_not_called()
        cache.invalidate_all()
        other.close.assert_called_once_with()

    def test_a_replaced_session_is_closed_and_the_same_one_is_not(self):
        cache = SessionCache(max_size=3)
        first, second = MagicMock(), MagicMock()
        cache.set("key", first)
        cache.set("key", first)
        first.close.assert_not_called()
        cache.set("key", second)
        first.close.assert_called_once_with()
        self.assertIs(cache.get("key"), second)
