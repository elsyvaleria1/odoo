from odoo.tests import TransactionCase, tagged

RESTATABLE = frozenset({"related", "inherited", "readonly", "groups", "string", "help"})


@tagged("post_install", "-at_install")
class TestVersionDelegationGate(TransactionCase):
    def _restatements(self):
        Employee = self.env["hr.employee"]
        Version = self.env["hr.version"]
        Partner = self.env["res.partner"]
        found = []
        for name, field in Employee._fields.items():
            related = field.related or ""
            if not related.startswith("version_id.") or related.count(".") != 1:
                continue
            if name in Partner._fields:
                continue
            parent = Version._fields.get(related.split(".")[1])
            if parent is None or parent.name != name:
                continue
            declared = [
                base
                for base in getattr(field, "_base_fields__", ())
                if "inherited_field" not in base._args__
            ]
            if not declared:
                continue
            if any(set(base._args__) - RESTATABLE for base in declared):
                continue
            same = (
                field.type == parent.type
                and field.readonly == parent.readonly
                and (field.groups or None) == (parent.groups or None)
                and field.string == parent.string
                and (field.help or None) == (parent.help or None)
            )
            if same:
                found.extend((name, base._module) for base in declared)
        return sorted(found)

    def test_no_employee_field_merely_restates_its_version_field(self):
        self.assertFalse(
            self._restatements(),
            "these hr.employee declarations repeat what _inherits hr.version "
            "already provides; delete them, or give them the attribute that "
            "justifies them",
        )

    def test_a_name_on_both_employee_and_version_is_stored_once(self):
        Employee = self.env["hr.employee"]._fields
        Version = self.env["hr.version"]._fields
        magic = {
            "id",
            "display_name",
            "create_uid",
            "create_date",
            "write_uid",
            "write_date",
        }
        twice = []
        for name in set(Employee) & set(Version):
            if name in magic or Employee[name].inherited:
                continue
            if set(Employee[name]._modules or ()) & set(Version[name]._modules or ()):
                continue
            if Employee[name].store and Version[name].store:
                twice.append(name)
        self.assertFalse(
            sorted(twice),
            "hr.employee and hr.version both store these; one side must be a "
            "related to the other",
        )
