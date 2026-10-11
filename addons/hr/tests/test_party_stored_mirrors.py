from odoo.tests import TransactionCase, tagged

PARTY_MODELS = frozenset(
    {
        "res.partner",
        "res.company",
        "res.users",
        "hr.employee",
        "hr.version",
        "resource.resource",
    }
)

TWO_WAY_SYNCS = frozenset(
    {
        ("resource.resource", "name"),
    }
)


@tagged("post_install", "-at_install")
class TestPartyStoredMirrors(TransactionCase):
    """One fact, one writer -- measured from the registry rather than asserted."""

    def _mirrors(self):
        found = {}
        for model_name in sorted(PARTY_MODELS):
            model = self.env[model_name]
            for fname, field in sorted(model._fields.items()):
                if not field.store:
                    continue
                depends, _context = field.get_depends(model)
                for dep in depends:
                    if "." not in dep:
                        continue
                    hop = model._fields.get(dep.split(".")[0])
                    if not hop or not hop.relational:
                        continue
                    if hop.comodel_name not in PARTY_MODELS:
                        continue
                    found[(model_name, fname)] = (
                        "related"
                        if field.related
                        else "two-way"
                        if field.compute and field.inverse
                        else "one-way"
                    )
                    break
        return found

    def test_the_only_two_way_sync_is_the_resources_name(self):
        two_way = {key for key, kind in self._mirrors().items() if kind == "two-way"}
        self.assertEqual(
            two_way,
            set(TWO_WAY_SYNCS),
            "A stored field between the party and its roles gained both a "
            "compute and an inverse, so one fact now has two writers and can "
            "disagree with itself. Delegate it, make it a plain related, or "
            "add it here with the reason it must be written from both ends.",
        )

    def test_both_of_them_agree_whichever_end_is_written(self):
        employee = self.env["hr.employee"].create(
            {"name": "Round Trip", "tz": "Europe/Brussels"}
        )
        party, resource = employee.partner_id, employee.resource_id
        self.assertEqual(
            (resource.name, resource.tz), ("Round Trip", "Europe/Brussels")
        )

        party.write({"name": "Renamed On Party", "tz": "America/Mexico_City"})
        self.assertEqual(
            (resource.name, resource.tz), ("Renamed On Party", "Europe/Brussels")
        )

        resource.write({"name": "Renamed On Resource", "tz": "Asia/Tokyo"})
        self.assertEqual(
            (party.name, party.tz), ("Renamed On Resource", "America/Mexico_City")
        )
        self.assertEqual(
            (employee.name, employee.tz), ("Renamed On Resource", "Asia/Tokyo")
        )

    def test_the_detector_sees_the_mirrors_it_is_meant_to_see(self):
        mirrors = self._mirrors()
        self.assertEqual(mirrors.get(("hr.employee", "name")), "related")
        self.assertIsNone(mirrors.get(("res.company", "name")))
        self.assertEqual(mirrors.get(("resource.resource", "name")), "two-way")
        self.assertGreater(len(mirrors), 10)
