from odoo.tests.common import TransactionCase, tagged
from odoo.tools.constants import CACHES_BY_KEY

_NARROW_KEYS = ("default", "groups", "stable")


@tagged("post_install", "-at_install")
class DryRunClearsOnlyWhatItDirtied(TransactionCase):
    _OPTS = {"has_headers": True, "quoting": '"', "separator": ",", "encoding": "utf-8"}

    def _seed_sentinels(self):
        self.env.registry.cache_invalidated.clear()
        lrus = self.env.registry.ormcache_lrus
        for name, lru in lrus.items():
            lru[("SENTINEL", name)] = 1
        self.addCleanup(self._drop_sentinels)
        return lrus

    def _drop_sentinels(self):
        for name, lru in self.env.registry.ormcache_lrus.items():
            lru.pop(("SENTINEL", name), None)

    def _survivors(self):
        return {
            name
            for name, lru in self.env.registry.ormcache_lrus.items()
            if ("SENTINEL", name) in lru
        }

    def _dryrun(self, res_model, csv, fields_, columns):
        imp = self.env["base_import.import"].create(
            {
                "res_model": res_model,
                "file": csv,
                "file_type": "text/csv",
                "file_name": "dryrun.csv",
            }
        )
        result = imp.execute_import(fields_, columns, dict(self._OPTS), dryrun=True)
        self.assertFalse(result["messages"])

    def test_dryrun_keeps_the_caches_it_cannot_have_dirtied(self):
        lrus = self._seed_sentinels()

        self._dryrun("res.partner", b"name\nImported Row\n", ["name"], ["Name"])

        cleared = set()
        for key in _NARROW_KEYS:
            cleared |= set(CACHES_BY_KEY[key])
        expected = set(lrus) - cleared

        self.assertEqual(
            self._survivors(),
            expected,
            "a dry-run cleared more of the ormcache than the rows it rolled back",
        )
        self.assertIn("routing", expected)
        self.assertIn("assets", expected)

    def test_dryrun_still_clears_a_cache_the_import_invalidated(self):
        self._seed_sentinels()
        seen = {}
        registry = self.env.registry
        original = registry.reset_changes

        def spy():
            seen.setdefault("cache_invalidated", set(registry.cache_invalidated))
            return original()

        self.patch(registry, "reset_changes", spy)

        self._dryrun(
            "ir.asset",
            b"name,bundle,path\nzzz_probe,web.assets_backend,/web/static/src/probe.js\n",
            ["name", "bundle", "path"],
            ["name", "bundle", "path"],
        )

        self.assertIn(
            "assets",
            seen.get("cache_invalidated", set()),
            "ir.asset.write must report `assets` so reset_changes() re-clears it",
        )
        self.assertNotIn(
            "assets",
            self._survivors(),
            "the import wrote ir.asset, so the assets cache had to be dropped",
        )
