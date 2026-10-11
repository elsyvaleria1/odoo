import unittest
from collections.abc import Iterable

from odoo.libs.collections import Collector


class KeysOnlyMapping:
    def keys(self) -> Iterable[str]:
        return ("a", "b")

    def __getitem__(self, key: str) -> Iterable[int]:
        return {"a": [1, 2], "b": []}[key]


class ItemsOnlyMapping:
    def items(self) -> Iterable[tuple[str, Iterable[int]]]:
        return (("a", [1, 2]), ("b", []))


class TestCollectorMappingInput(unittest.TestCase):
    def test_existing_items_only_input_remains_supported(self) -> None:
        collector = Collector(ItemsOnlyMapping())
        self.assertEqual(collector, {"a": (1, 2)})
        collector.update(ItemsOnlyMapping())
        self.assertEqual(collector, {"a": (1, 2)})

    def test_constructor_accepts_keys_only_mapping(self) -> None:
        collector = Collector(KeysOnlyMapping())
        self.assertEqual(collector, {"a": (1, 2)})
        self.assertEqual(collector["b"], ())

    def test_update_accepts_keys_only_mapping_and_keyword_overrides(self) -> None:
        collector = Collector({"a": [0], "b": [3]})
        collector.update(KeysOnlyMapping(), a=[4])
        self.assertEqual(collector, {"a": (4,)})

    def test_pairs_and_defaults_keep_their_contract(self) -> None:
        collector = Collector([("a", [1])], b=[2])
        collector.update((("c", [3]),), a=[])
        self.assertEqual(collector, {"b": (2,), "c": (3,)})
        self.assertEqual(collector.get("a"), ())
        self.assertIsNone(collector.get("a", default=None))
        self.assertEqual(collector.pop("a"), ())
        missing = object()
        self.assertIs(collector.pop("a", default=missing), missing)
