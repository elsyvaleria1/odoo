from collections import defaultdict

from odoo.fields import Field
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEmployeeFieldOwnership(TransactionCase):
    def test_no_field_is_delegated_by_both_parents(self):
        employee = self.env["hr.employee"]
        declared = {
            name
            for cls in type(employee).mro()[1:]
            for name, value in vars(cls).items()
            if isinstance(value, Field)
        }
        parents = [self.env[model]._fields for model in employee._inherits]
        ambiguous = sorted(
            name
            for name in employee._fields
            if name not in declared and all(name in fields for fields in parents)
        )
        self.assertEqual(ambiguous, [])

    def test_the_photo_is_the_work_contacts(self):
        image = self.env["hr.employee"]._fields["image_1920"]
        self.assertEqual(image.related, "partner_id.image_1920")
        self.assertEqual(image.inherited_field.model_name, "res.partner")

    def test_every_label_names_one_field(self):
        for model in ("hr.employee", "res.users"):
            by_label = defaultdict(list)
            for name, field in self.env[model]._fields.items():
                by_label[field.string].append(name)
            shared = {
                label: names for label, names in by_label.items() if len(names) > 1
            }
            with self.subTest(model=model):
                self.assertEqual(shared, {})
