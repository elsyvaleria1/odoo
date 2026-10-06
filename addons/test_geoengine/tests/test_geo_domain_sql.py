import logging

from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.test_geoengine.models.geo_domain_sql import Adv, Dw, Link, Pred, Ref

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "geoengine_domain")
class TestAdversarial(TransactionCase):
    M = "geoengine.adv.fixture"
    REF = "geoengine.adv.ref"
    LINK = "geoengine.adv.link"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.A, cls.R, cls.L = (
            cls.env[Adv._name],
            cls.env[Ref._name],
            cls.env[Link._name],
        )

    def _names(self, domain):
        return sorted(self.A.search(domain).mapped("name"))

    def _p(self, label, fn):
        try:
            result = fn()
        except Exception as e:
            raise AssertionError(f"{label} raised {type(e).__name__}: {e}") from e
        _logger.info("geo-domain %-52s => %r", label, result)
        return result

    BOX = "SRID=3857;POLYGON((0 0, 100 0, 100 100, 0 100, 0 0))"

    def _seed(self):
        self.A.create({"name": "in", "kind": "a", "pt": "SRID=3857;POINT(50 50)"})
        self.A.create({"name": "out", "kind": "b", "pt": "SRID=3857;POINT(500 500)"})
        self.A.create({"name": "null", "kind": "a"})
        self.A.flush_model()

    def test_negation_and_nulls(self):
        self._seed()
        self._p(
            "positive geo_intersect",
            lambda: self.A.search([("pt", "geo_intersect", self.BOX)]).mapped("name"),
        )
        self._p(
            "NOT geo_intersect (Domain ~)",
            lambda: self.A.search(~Domain("pt", "geo_intersect", self.BOX)).mapped(
                "name"
            ),
        )
        self._p(
            "['!', (...)] list form",
            lambda: self.A.search(["!", ("pt", "geo_intersect", self.BOX)]).mapped(
                "name"
            ),
        )

    def test_composition(self):
        self._seed()
        self._p(
            "OR with non-geo",
            lambda: self.A.search(
                ["|", ("pt", "geo_intersect", self.BOX), ("kind", "=", "b")]
            ).mapped("name"),
        )
        self._p(
            "AND with non-geo",
            lambda: self.A.search(
                [("pt", "geo_intersect", self.BOX), ("kind", "=", "a")]
            ).mapped("name"),
        )
        self._p(
            "two geo conditions ANDed",
            lambda: self.A.search(
                [
                    ("pt", "geo_intersect", self.BOX),
                    (
                        "pt",
                        "geo_intersect",
                        "SRID=3857;POLYGON((40 40,60 40,60 60,40 60,40 40))",
                    ),
                ]
            ).mapped("name"),
        )

    def test_filtered_domain(self):
        self._seed()
        recs = self.A.search([])
        self._p(
            "filtered_domain(geo_intersect)",
            lambda: recs.filtered_domain([("pt", "geo_intersect", self.BOX)]).mapped(
                "name"
            ),
        )

    def test_any_subquery(self):
        r = self.R.create({"name": "zone", "area": self.BOX})
        self.R.flush_model()

        L = self.L
        L.create({"name": "l1", "ref_id": r.id})
        L.flush_model()
        self._p(
            "m2o.any(geo_intersect) -- ALIASED subquery",
            lambda: L.search(
                [
                    (
                        "ref_id",
                        "any",
                        [("area", "geo_intersect", "SRID=3857;POINT(50 50)")],
                    )
                ]
            ).mapped("name"),
        )

    def test_read_group(self):
        self._seed()
        self._p(
            "_read_group with geo domain",
            lambda: self.A._read_group(
                [("pt", "geo_intersect", self.BOX)], ["kind"], ["__count"]
            ),
        )

    def test_errors_raise(self):
        self._seed()
        for label, dom in [
            ("garbage geometry", [("pt", "geo_intersect", "NOT-A-GEOMETRY")]),
            ("non-geo field", [("kind", "geo_intersect", "SRID=3857;POINT(0 0)")]),
            ("dwithin without dict", [("pt", "geo_dwithin", "SRID=3857;POINT(0 0)")]),
            (
                "dwithin bad distance",
                [
                    (
                        "pt",
                        "geo_dwithin",
                        {"geometry": "SRID=3857;POINT(0 0)", "distance": "x"},
                    )
                ],
            ),
            ("dict operand without dot", [("pt", "geo_intersect", {"nodot": []})]),
        ]:
            with self.subTest(case=label), self.assertRaises(UserError):
                self.A.search(dom).mapped("name")

        self.assertEqual(
            self._p(
                "empty geometry -> quiet []",
                lambda: self.A.search(
                    [("pt", "geo_intersect", "SRID=3857;POLYGON EMPTY")]
                ).mapped("name"),
            ),
            [],
        )
        self.assertEqual(
            self._p(
                "reference matching nothing -> quiet []",
                lambda: self.A.search(
                    [
                        (
                            "pt",
                            "geo_within",
                            {f"{self.REF}.area": [("name", "=", "nope")]},
                        )
                    ]
                ).mapped("name"),
            ),
            [],
        )

    def test_reference_queries(self):
        self._seed()
        self.R.create({"name": "z1", "area": self.BOX})
        self.R.create(
            {
                "name": "z2",
                "area": "SRID=3857;POLYGON((400 400,600 400,600 600,400 600,400 400))",
            }
        )
        self.R.flush_model()
        self.assertEqual(
            self._p(
                "within one referenced zone",
                lambda: self.A.search(
                    [("pt", "geo_within", {f"{self.REF}.area": [("name", "=", "z1")]})]
                ).mapped("name"),
            ),
            ["in"],
        )
        self.assertEqual(
            sorted(
                self._p(
                    "within union of both zones",
                    lambda: self.A.search(
                        [("pt", "geo_within", {f"{self.REF}.area": []})]
                    ).mapped("name"),
                )
            ),
            ["in", "out"],
        )

    def test_all_operators(self):
        self._seed()
        ops = [
            "geo_intersect",
            "geo_contains",
            "geo_within",
            "geo_touch",
            "geo_equal",
            "geo_overlap",
            "geo_covers",
            "geo_covered_by",
            "geo_disjoint",
            "geo_crosses",
        ]
        for op in ops:
            self._p(
                f"op {op}",
                lambda o=op: self.A.search([("pt", o, self.BOX)]).mapped("name"),
            )
        self._p(
            "op geo_dwithin",
            lambda: self.A.search(
                [
                    (
                        "pt",
                        "geo_dwithin",
                        {"geometry": "SRID=3857;POINT(0 0)", "distance": 1000},
                    )
                ]
            ).mapped("name"),
        )

    def test_geo_equal_is_topological_in_sql_and_in_memory(self):
        ring = "0 0, 10 0, 10 10, 0 10, 0 0"
        rotated = "10 10, 0 10, 0 0, 10 0, 10 10"
        self.A.create({"name": "z", "zone": f"SRID=3857;POLYGON(({ring}))"})
        self.A.create({"name": "rot", "zone": f"SRID=3857;POLYGON(({rotated}))"})
        self.A.create(
            {"name": "other", "zone": "SRID=3857;POLYGON((0 0, 5 0, 5 5, 0 0))"}
        )
        self.A.flush_model()
        domain = [("zone", "geo_equal", f"SRID=3857;POLYGON(({ring}))")]
        self.assertEqual(self._names(domain), ["rot", "z"])
        self.assertEqual(
            sorted(self.A.search([]).filtered_domain(domain).mapped("name")),
            ["rot", "z"],
        )

    def test_cross_srid(self):
        self.A.create({"name": "zurich", "pt": "SRID=3857;POINT(948695.5 6002729.5)"})
        self.A.flush_model()
        self._p(
            "4326 box against 3857 field",
            lambda: self.A.search(
                [
                    (
                        "pt",
                        "geo_intersect",
                        "SRID=4326;POLYGON((8.4 47.3,8.7 47.3,8.7 47.5,8.4 47.5,8.4 47.3))",
                    )
                ]
            ).mapped("name"),
        )

    def test_record_rules_applied(self):
        self._seed()
        user = new_test_user(self.env, login="geo_adv_user", groups="base.group_user")
        self.env["ir.access"].create(
            [
                {
                    "name": "adv all",
                    "model_id": self.env["ir.model"]._get_id(self.M),
                    "group_id": self.env.ref("base.group_user").id,
                    "kind": "permission",
                    "operation": "r",
                },
                {
                    "name": "only kind b",
                    "model_id": self.env["ir.model"]._get_id(self.M),
                    "group_id": self.env.ref("base.group_everyone").id,
                    "kind": "guard",
                    "operation": "crud",
                    "domain": "[('kind', '=', 'b')]",
                },
            ]
        )
        self.env.registry.clear_cache()
        AsUser = self.A.with_user(user)
        self._p(
            "as restricted user: all records", lambda: AsUser.search([]).mapped("name")
        )
        big = "SRID=3857;POLYGON((-1000 -1000, 1000 -1000, 1000 1000, -1000 1000, -1000 -1000))"
        self._p(
            "as restricted user: geo search (rule must apply)",
            lambda: AsUser.search([("pt", "geo_intersect", big)]).mapped("name"),
        )

    def test_active_test(self):
        self._seed()
        self.A.search([("name", "=", "out")]).active = False
        self.A.flush_model()
        big = "SRID=3857;POLYGON((-1000 -1000, 1000 -1000, 1000 1000, -1000 1000, -1000 -1000))"
        self._p(
            "active_test on (default)",
            lambda: self.A.search([("pt", "geo_intersect", big)]).mapped("name"),
        )
        self._p(
            "active_test off",
            lambda: (
                self.A.with_context(active_test=False)
                .search([("pt", "geo_intersect", big)])
                .mapped("name")
            ),
        )

    def test_injection(self):
        self._seed()
        evil = "SRID=3857;POINT(0 0)'); DROP TABLE geoengine_adv_fixture; --"
        with self.assertRaises(UserError):
            self.A.search([("pt", "geo_intersect", evil)])
        self.assertEqual(
            self._p("table still exists", lambda: self.A.search_count([])), 3
        )


@tagged("post_install", "-at_install", "geoengine_domain")
class TestPredicate(TransactionCase):
    M = "geoengine.pred.fixture"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.P = cls.env[Pred._name]

    def test_predicate_matches_sql(self):
        box = "SRID=3857;POLYGON((0 0, 100 0, 100 100, 0 100, 0 0))"
        self.P.create({"name": "in", "pt": "SRID=3857;POINT(50 50)"})
        self.P.create({"name": "out", "pt": "SRID=3857;POINT(500 500)"})
        self.P.create({"name": "null"})
        self.P.flush_model()
        allrecs = self.P.search([])
        ops = [
            "geo_intersect",
            "geo_contains",
            "geo_within",
            "geo_touch",
            "geo_equal",
            "geo_overlap",
            "geo_covers",
            "geo_covered_by",
            "geo_disjoint",
            "geo_crosses",
        ]
        mismatches = []
        for op in ops:
            sql_r = sorted(self.P.search([("pt", op, box)]).mapped("name"))
            mem_r = sorted(allrecs.filtered_domain([("pt", op, box)]).mapped("name"))
            flag = "OK " if sql_r == mem_r else "MISMATCH"
            if sql_r != mem_r:
                mismatches.append((op, sql_r, mem_r))
            _logger.info("PRED %-8s %-16s sql=%-22r mem=%r", flag, op, sql_r, mem_r)
        d = {"geometry": "SRID=3857;POINT(0 0)", "distance": 1000}
        sql_r = sorted(self.P.search([("pt", "geo_dwithin", d)]).mapped("name"))
        mem_r = sorted(
            allrecs.filtered_domain([("pt", "geo_dwithin", d)]).mapped("name")
        )
        _logger.info(
            "PRED %-8s %-16s sql=%-22r mem=%r",
            "OK " if sql_r == mem_r else "MISMATCH",
            "geo_dwithin",
            sql_r,
            mem_r,
        )
        if sql_r != mem_r:
            mismatches.append(("geo_dwithin", sql_r, mem_r))
        self.assertFalse(mismatches, f"SQL/predicate disagreement: {mismatches}")


@tagged("post_install", "-at_install", "geoengine_domain")
class TestDwithinUnits(TransactionCase):
    M = "geoengine.dwithin.fixture"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.D = cls.env[Dw._name]

    def test_metre_query_carries_an_indexable_prefilter(self):
        query = self.D._search(
            [
                (
                    "pt",
                    "geo_dwithin",
                    {"geometry": "POINT(0 0)", "distance": 10, "unit": "m"},
                )
            ]
        )
        sql = query.select("id").code
        self.assertIn("&&", sql)
        self.assertIn("ST_MakeEnvelope", sql)
        self.assertIn("::geography", sql)

    def test_metres_vs_srid_units(self):
        self.D.create({"name": "zurich", "pt": "SRID=4326;POINT(8.54 47.37)"})
        self.D.create({"name": "geneva", "pt": "SRID=4326;POINT(6.14 46.20)"})
        self.D.flush_model()
        zurich = "SRID=4326;POINT(8.54 47.37)"

        def names(value):
            return sorted(self.D.search([("pt", "geo_dwithin", value)]).mapped("name"))

        self.assertEqual(
            names({"geometry": zurich, "distance": 1000}), ["geneva", "zurich"]
        )
        self.assertEqual(
            names({"geometry": zurich, "distance": 1000, "unit": "m"}), ["zurich"]
        )
        self.assertEqual(
            names({"geometry": zurich, "distance": 300_000, "unit": "m"}),
            ["geneva", "zurich"],
        )
        allrecs = self.D.search([])
        for value in (
            {"geometry": zurich, "distance": 1000},
            {"geometry": zurich, "distance": 1000, "unit": "m"},
            {"geometry": zurich, "distance": 300_000, "unit": "m"},
        ):
            self.assertEqual(
                sorted(
                    allrecs.filtered_domain([("pt", "geo_dwithin", value)]).mapped(
                        "name"
                    )
                ),
                names(value),
                f"SQL and in-memory disagree for {value}",
            )

    def test_bad_unit_raises(self):
        with self.assertRaises(UserError):
            self.D.search(
                [
                    (
                        "pt",
                        "geo_dwithin",
                        {
                            "geometry": "SRID=4326;POINT(0 0)",
                            "distance": 1,
                            "unit": "km",
                        },
                    )
                ]
            )
