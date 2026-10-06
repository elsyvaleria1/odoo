from odoo.tests.common import TransactionCase


class TestPostalCodeNameSearch(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        state = cls.env["res.country.state"].search(
            [("country_id", "=", cls.env.ref("base.mx").id)], limit=1
        )
        PostalCode = cls.env["l10n_mx.postal_code"]
        cls.centro = PostalCode.create(
            {"code": "99901", "name": "Colonia Zzcentro", "state_id": state.id}
        )
        cls.norte = PostalCode.create(
            {"code": "99902", "name": "Colonia Zznorte", "state_id": state.id}
        )

    def test_name_search_matches_the_code(self) -> None:
        found = self.env["l10n_mx.postal_code"].name_search("99901")
        self.assertEqual([record_id for record_id, _name in found], [self.centro.id])

    def test_name_search_matches_the_colony(self) -> None:
        found = self.env["l10n_mx.postal_code"].name_search("Zznorte")
        self.assertEqual([record_id for record_id, _name in found], [self.norte.id])

    def test_negative_name_search_excludes_on_both_fields(self) -> None:
        found = self.env["l10n_mx.postal_code"].search(
            [
                ("display_name", "not ilike", "9990"),
                ("id", "in", (self.centro | self.norte).ids),
            ]
        )
        self.assertFalse(found)


class TestSepomexImport(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        mexico = cls.env.ref("base.mx")
        cls.sinaloa = cls.env["res.country.state"].search(
            [("country_id", "=", mexico.id), ("code", "=", "SIN")]
        )
        cls.municipality = cls.env["l10n_mx.municipality"].create(
            {"name": "Sepomex Test", "code": "951", "state_id": cls.sinaloa.id}
        )
        header = (
            "d_codigo|d_asenta|d_tipo_asenta|D_mnpio|d_estado|d_ciudad|d_CP|c_estado|"
            "c_oficina|c_CP|c_tipo_asenta|c_mnpio|id_asenta_cpcons|d_zona|c_cve_ciudad"
        )
        rows = [
            "99901|Peñasco|Colonia|Sepomex Test|Sinaloa|Culiacán|80001|25|80001||09|951|0001|Urbano|01",
            "99901|El Álamo|Ejido|Sepomex Test|Sinaloa||80001|25|80001||14|951|0002|Rural|",
            "99901|El Álamo |Barrio|Sepomex Test|Sinaloa||80001|25|80001||02|951|0003|Rural|",
            "99902|Nowhere|Colonia|X|X||99999|99|99999||09|001|0001|Urbano|",
        ]
        cls.content = "\r\n".join(
            ["El Catálogo Nacional de Códigos Postales...", header, *rows]
        ).encode("latin-1")

    def test_settlements_get_their_state_and_municipality(self) -> None:
        counts = self.env["l10n_mx.postal_code"]._import_sepomex(self.content)
        self.assertEqual(counts, {"created": 2, "linked": 0, "unknown_state": 1})
        codes = self.env["l10n_mx.postal_code"].search([("code", "=", "99901")])
        self.assertEqual(set(codes.mapped("name")), {"Peñasco", "El Álamo"})
        self.assertEqual(codes.municipality_id, self.municipality)
        self.assertEqual(codes.state_id, self.sinaloa)
        self.assertEqual(set(codes.mapped("zone_type")), {"urban", "rural"})

    def test_importing_again_adds_nothing_and_fills_missing_links(self) -> None:
        postal_code = self.env["l10n_mx.postal_code"]
        postal_code._import_sepomex(self.content)
        postal_code.search([("code", "=", "99901")]).municipality_id = False
        counts = postal_code._import_sepomex(self.content)
        self.assertEqual(counts, {"created": 0, "linked": 2, "unknown_state": 1})
        self.assertEqual(postal_code.search_count([("code", "=", "99901")]), 2)
