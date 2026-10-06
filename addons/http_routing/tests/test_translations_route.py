from odoo.libs.json import loads as json_loads
from odoo.tests import HttpCase, tagged

from .common import setup_frontend_langs


@tagged("-at_install", "post_install")
class TestWebsiteTranslations(HttpCase):
    EP = "/website/translations"

    def _modules(self, url):
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        return set(json_loads(response.content).get("modules", {}))

    def test_serves_the_frontend_allow_list(self):
        self.assertIn("web", self._modules(self.EP))

    def test_caller_supplied_mods_cannot_widen_the_bundle(self):
        baseline = self._modules(self.EP)
        widened = self._modules(self.EP + "?mods=base,mail,web_tour")
        self.assertEqual(widened, baseline)

    def test_unknown_mods_do_not_mint_cache_entries(self):
        lru = self.env.registry.ormcache_lrus["default"]
        self.url_open(self.EP)
        before = len(lru.snapshot)
        for i in range(25):
            self.url_open(f"{self.EP}?mods=web,probe{i}")
        self.assertEqual(
            len(lru.snapshot),
            before,
            "the public translations route must not let its caller grow the "
            "shared ormcache",
        )

    def test_hash_is_stable_across_mods(self):
        plain = json_loads(self.url_open(self.EP).content)
        with_mods = json_loads(self.url_open(self.EP + "?mods=base").content)
        self.assertEqual(plain["hash"], with_mods["hash"])

    def test_the_language_is_the_callers_not_the_visitors(self):
        french = self.env["res.lang"]._activate_lang("fr_FR")
        french.url_code = "fr"
        english = self.env.ref("base.lang_en")
        setup_frontend_langs(self.env, english + french, english)
        for cookie, lang in (("fr_FR", "en_US"), ("en_US", "fr_FR")):
            with self.subTest(cookie=cookie, lang=lang):
                response = self.url_open(
                    f"{self.EP}?lang={lang}",
                    allow_redirects=False,
                    cookies={"frontend_lang": cookie},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(json_loads(response.content)["lang"], lang)
                self.assertNotIn("frontend_lang", response.cookies)
