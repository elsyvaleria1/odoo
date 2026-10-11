from odoo.tests import TransactionCase, tagged

MAGIC = frozenset(
    {"id", "create_date", "create_uid", "write_date", "write_uid", "display_name"}
)

KEEP_SHADOWED = frozenset(
    {
        "parent_id",
        "child_ids",
        "user_id",
        "company_id",
        "active",
        "tag_ids",
        "tz",
        "color",
    }
)
SEPARATE_DESTINATION = frozenset(
    {
        "barcode",
    }
)
DELEGATION_PROVIDES = frozenset({"name", "lang", "phone_ids", "email", "im_status"})
FACET_PROVIDES = frozenset(
    {
        "sex",
        "birthday",
        "nationality_country_id",
        "nationality_country_ids",
        "private_email",
        "private_phone_ids",
        "private_street",
        "private_street2",
        "private_city",
        "private_state_id",
        "private_zip",
        "private_country_id",
        "place_of_birth",
        "country_of_birth",
        "nationality_ids",
        "marital",
        "spouse_complete_name",
        "spouse_birthdate",
        "children",
        "certificate",
        "study_field",
        "study_school",
    }
)
WRONG_PARENT = frozenset({"country_code"})

CONDITIONAL = {
    "currency_id": "account",
    "document_count": "document_hr",
}

EXPECTED = (KEEP_SHADOWED | SEPARATE_DESTINATION | WRONG_PARENT) | set(CONDITIONAL)


@tagged("post_install", "-at_install")
class TestPartnerShadowGate(TransactionCase):

    @classmethod
    def _shadowed(cls):
        employee = cls.env["hr.employee"]._fields
        partner = cls.env["res.partner"]._fields
        found = set()
        for name in set(employee) & set(partner):
            if name in MAGIC:
                continue
            shared = (
                set(employee[name]._modules or ()) & set(partner[name]._modules or ())
            ) - {"base"}
            if shared:
                continue
            if name in FACET_PROVIDES and name not in EXPECTED:
                continue
            field = employee[name]
            if field.inherited and field.inherited_field.model_name == "res.partner":
                continue
            found.add(name)
        return found

    def test_no_field_shadows_the_partner_beyond_the_recorded_set(self):
        unexpected = self._shadowed() - EXPECTED
        self.assertFalse(
            unexpected,
            "hr.employee gained %s, which res.partner also declares. Delegation "
            "will not move it and no error will say so -- either delete it, or "
            "add it to this test with the reason it must stay shadowed."
            % sorted(unexpected),
        )

    @classmethod
    def _expected_here(cls):
        installed = set(
            cls.env["ir.module.module"]
            .search([("state", "=", "installed")])
            .mapped("name")
        )
        return EXPECTED - {
            name for name, module in CONDITIONAL.items() if module not in installed
        }

    def test_the_recorded_set_has_not_silently_shrunk(self):
        gone = self._expected_here() - self._shadowed()
        self.assertFalse(
            gone,
            "%s no longer shadows res.partner. If step 7 resolved it, remove it "
            "from this test in the same commit." % sorted(gone),
        )

    def test_the_recorded_set_is_complete_only_for_the_installed_modules(self):
        installed = set(
            self.env["ir.module.module"]
            .search([("state", "=", "installed")])
            .mapped("name")
        )
        if "account" not in installed:
            self.skipTest("account is not installed; currency_id cannot collide here")
        self.assertIn("currency_id", self._shadowed())

    def test_inherited_alone_does_not_satisfy_the_gate(self):
        field = self.env["hr.employee"]._fields["country_code"]
        self.assertTrue(field.inherited)
        self.assertEqual(field.inherited_field.model_name, "hr.version")
        self.assertIn("country_code", self._shadowed())

    def test_the_facet_fields_are_read_from_the_facet(self):
        Employee = self.env["hr.employee"]
        for name in FACET_PROVIDES:
            field = Employee._fields[name]
            depends = field.get_depends(Employee)[0]
            self.assertTrue(
                (field.related and field.related.startswith("private_address_id."))
                or (
                    field.compute
                    and depends
                    and all(path.startswith("private_address_id.") for path in depends)
                ),
                "%s must read the private facet, but related=%r, depends=%r"
                % (name, field.related, depends),
            )

    def test_delegation_provides_what_it_promised(self):
        employee = self.env["hr.employee"]._fields
        for name in DELEGATION_PROVIDES:
            field = employee[name]
            self.assertTrue(field.inherited, name)
            self.assertEqual(field.inherited_field.model_name, "res.partner", name)
