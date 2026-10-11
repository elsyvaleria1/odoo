import threading
from contextlib import contextmanager

from odoo.modules.registry import Registry
from odoo.tests.common import BaseCase, TransactionCase, tagged


@contextmanager
def _thread_without_database():
    thread = threading.current_thread()
    dbname = thread.dbname
    del thread.dbname
    try:
        yield
    finally:
        thread.dbname = dbname


class TestSlugUnslug(BaseCase):
    def test_unslug(self):
        tests = {
            "": (None, None),
            "foo": (None, None),
            "foo-": (None, None),
            "-": (None, None),
            "foo-1": ("foo", 1),
            "foo-bar-1": ("foo-bar", 1),
            "foo--1": ("foo", -1),
            "1": (None, 1),
            "1-1": ("1", 1),
            "--1": (None, None),
            "foo---1": (None, None),
            "foo1": (None, None),
            "foo-1/": ("foo", 1),
            "foo-1/?qs=1": ("foo", 1),
            "foo-1/#anchor": ("foo", 1),
            "foo-1?qs=1": ("foo", 1),
            "foo-1#anchor": ("foo", 1),
        }

        unslug = Registry(threading.current_thread().dbname)["ir.http"]._unslug

        for slug, expected in tests.items():
            self.assertEqual(unslug(slug), expected, "%r case failed" % slug)

    def test_slug(self):
        tests = {
            "foo-1": (1, "foo"),
            "foo-bar-1": (1, "foo-bar"),
            "foo--1": (-1, "foo"),
            "1-2": (2, "1"),
        }

        slug = Registry(threading.current_thread().dbname)["ir.http"]._slug

        for expected, value in tests.items():
            self.assertEqual(slug(value), expected, "%r case failed" % (value,))


class TestTitleToSlug(BaseCase):
    def _slugify(self, value):
        _slugify = Registry(threading.current_thread().dbname)["ir.http"]._slugify
        return _slugify(value)

    def test_spaces(self):
        self.assertEqual("spaces", self._slugify("   spaces   "))

    def test_unicode(self):
        self.assertEqual("heterogeneite", self._slugify("hétérogénéité"))

    def test_underscore(self):
        self.assertEqual("one-two", self._slugify("one_two"))

    def test_caps(self):
        self.assertEqual("camelcase", self._slugify("CamelCase"))

    def test_special_chars(self):
        self.assertEqual("hello", self._slugify("^h☺e$#!l(%l}o☞☞"))

    def test_str_to_unicode(self):
        self.assertEqual("espana", self._slugify("España"))

    def test_numbers(self):
        self.assertEqual("article-1", self._slugify("Article 1"))

    def test_non_ascii(self):
        self.assertEqual("你好-再見", self._slugify("你好 再見"))

    def test_multiple_dashes(self):
        self.assertEqual("d-a-sh-e-s", self._slugify("d-----a----sh--e-------s"))

    def test_leading_trailing_dashes_spaces_underscores(self):
        self.assertEqual("mi-dd-le", self._slugify("_-__   -- -mi-dd-le- -- _ _-_- - "))

    def test_normalized_composed(self):
        self.assertEqual(
            "\N{HANGUL SYLLABLE GA}", self._slugify("\N{HANGUL SYLLABLE GA}")
        )

    def test_normalized_decomposed(self):
        self.assertEqual(
            "\N{HANGUL SYLLABLE GA}",
            self._slugify("\N{HANGUL CHOSEONG KIYEOK}\N{HANGUL JUNGSEONG A}"),
        )

    def test_all(self):
        self.assertEqual(
            "do-you-know-馬丁娜-a-la-海灘",
            self._slugify(" Do (YOU) ☞☞ know '馬丁娜 à la 海灘' ? "),
        )


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
            if rule.rule == '/website/country_infos/<model("res.country"):country>'
        )
        country = self.env.ref("base.be")
        self.assertEqual(
            rule._converters["country"].to_url(country), f"belgium-{country.id}"
        )
