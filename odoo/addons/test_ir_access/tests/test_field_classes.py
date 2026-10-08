from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user

MODEL = "test_ir_access.classified"
WHITELISTED = "test_ir_access.whitelisted"


class TestFieldClasses(TransactionCase):
    # a field names the class it belongs to; ir.access rows say who may read
    # or write the fields of a class, and groups= is a class of its own

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pay_group = cls.env["res.groups"].create({"name": "Pay readers"})
        cls.pay_write_group = cls.env["res.groups"].create({"name": "Pay writers"})
        classes = cls.env["ir.access.class"].create(
            [
                {"name": "test_ir_access.pay"},
                {"name": "test_ir_access.pay_write"},
                {"name": "test_ir_access.internal"},
                {"name": "test_ir_access.shared"},
            ]
        )
        cls.pay, cls.pay_write, cls.internal, cls.shared = classes
        everyone = cls.env.ref("base.group_everyone")
        cls.env["ir.access"].create(
            [
                cls._class_row(cls.pay, cls.pay_group, "permission", "ru"),
                cls._class_row(cls.pay_write, cls.pay_write_group, "permission", "u"),
                cls._class_row(cls.internal, everyone, "permission", "ru"),
                cls._class_row(
                    cls.internal,
                    cls.env.ref("base.group_portal"),
                    "guard",
                    "ru",
                    guard_scope="members",
                    reach="none",
                ),
                cls._class_row(cls.shared, everyone, "permission", "ru"),
            ]
        )
        cls.plain = new_test_user(cls.env, login="fc_plain", groups="base.group_user")
        cls.payroll = new_test_user(
            cls.env, login="fc_payroll", groups="base.group_user"
        )
        cls.payroll.group_ids += cls.pay_group
        cls.portal = new_test_user(
            cls.env, login="fc_portal", groups="base.group_portal"
        )
        cls.record = cls.env[MODEL].create({"name": "R", "wage": 10.0, "bonus": 1.0})
        cls.child = cls.env[MODEL].create({"name": "C", "parent_id": cls.record.id})
        cls.listed = cls.env[WHITELISTED].create({"name": "N", "secret": "S"})

    @classmethod
    def _class_row(cls, access_class, group, kind, operation, **values):
        return {
            "name": f"{access_class.name} {kind} {group.name}",
            "class_id": access_class.id,
            "group_id": group.id,
            "kind": kind,
            "operation": operation,
            **values,
        }

    def allowed(self, user, model, fname, operation="read"):
        records = self.env[model].with_user(user)
        return records._has_field_access(records._fields[fname], operation)

    def test_groups_is_a_class_with_the_same_verdict(self):
        for user in (
            self.plain,
            self.payroll,
            self.portal,
            self.env.ref("base.user_admin"),
        ):
            for fname in ("system_note", "internal_note"):
                spec = self.env[MODEL]._fields[fname].groups
                self.assertEqual(
                    self.allowed(user, MODEL, fname),
                    user.has_groups(spec),
                    (user.login, fname),
                )

    def test_a_named_class_is_read_by_the_groups_its_rows_grant(self):
        self.assertTrue(self.allowed(self.payroll, MODEL, "wage"))
        self.assertFalse(self.allowed(self.plain, MODEL, "wage"))
        self.assertEqual(self.record.with_user(self.payroll).wage, 10.0)
        with self.assertRaises(AccessError):
            _ = self.record.with_user(self.plain).wage

    def test_a_field_with_a_class_and_groups_needs_both(self):
        self.assertFalse(self.allowed(self.payroll, MODEL, "wage_note"))
        admin = self.env.ref("base.user_admin")
        self.assertFalse(self.allowed(admin, MODEL, "wage_note"))
        admin.group_ids += self.pay_group
        self.assertTrue(self.allowed(admin, MODEL, "wage_note"))

    def test_a_write_class_adds_to_what_writing_needs(self):
        self.assertTrue(self.allowed(self.plain, MODEL, "bonus", "read"))
        self.assertFalse(self.allowed(self.plain, MODEL, "bonus", "write"))
        with self.assertRaises(AccessError):
            self.record.with_user(self.plain).write({"bonus": 2.0})
        self.plain.group_ids += self.pay_write_group
        self.record.with_user(self.plain).write({"bonus": 2.0})
        self.assertEqual(self.record.bonus, 2.0)

    def test_a_copy_withholds_a_field_of_a_write_class_its_user_lacks(self):
        self.assertEqual(self.record.with_user(self.plain).copy().bonus, 0.0)
        self.plain.group_ids += self.pay_write_group
        self.assertEqual(self.record.with_user(self.plain).copy().bonus, 1.0)

    def test_a_related_field_carries_its_target_class(self):
        field = self.env[MODEL]._fields["parent_wage"]
        self.assertIn("test_ir_access.pay", field.access_classes.read)
        self.assertFalse(self.allowed(self.plain, MODEL, "parent_wage"))
        self.assertEqual(self.child.with_user(self.payroll).parent_wage, 10.0)

    def test_the_residual_class_holds_every_field_but_those_listed(self):
        # secret names no class, so it takes the model's residual class; the
        # automatic columns and the whitelisted name never do
        self.assertFalse(self.allowed(self.portal, WHITELISTED, "secret"))
        self.assertTrue(self.allowed(self.plain, WHITELISTED, "secret"))
        for fname in ("id", "display_name", "name"):
            self.assertTrue(self.allowed(self.portal, WHITELISTED, fname), fname)
        listed = self.listed.with_user(self.portal)
        self.assertEqual(listed.read(["name"])[0]["name"], "N")
        with self.assertRaises(AccessError):
            listed.read(["secret"])

    def test_a_grant_given_in_the_transaction_counts_at_once(self):
        self.assertFalse(self.allowed(self.plain, MODEL, "wage"))
        self.plain.group_ids += self.pay_group
        self.assertTrue(self.allowed(self.plain, MODEL, "wage"))

    def test_a_row_written_in_the_transaction_counts_at_once(self):
        self.assertFalse(self.allowed(self.plain, MODEL, "wage"))
        self.env["ir.access"].create(
            self._class_row(
                self.pay, self.env.ref("base.group_user"), "permission", "r"
            )
        )
        self.assertTrue(self.allowed(self.plain, MODEL, "wage"))

    def test_a_class_without_rows_is_read_by_nobody_but_the_superuser(self):
        self.pay.active = False
        self.assertFalse(self.allowed(self.payroll, MODEL, "wage"))
        self.assertEqual(self.record.sudo().wage, 10.0)

    def test_a_stored_compute_is_not_closed_over_its_sources(self):
        # a derived field states its own class; until it does, it shows what
        # it was computed from (the C2 gate counts such fields)
        self.assertTrue(self.allowed(self.plain, MODEL, "wage_twice"))
        self.assertEqual(self.record.with_user(self.plain).wage_twice, 20.0)

    def test_a_class_row_grants_reading_or_writing_only(self):
        with self.assertRaises(ValidationError):
            self.env["ir.access"].create(
                self._class_row(self.pay, self.pay_group, "permission", "cr")
            )
        with self.assertRaises(ValidationError):
            self.env["ir.access"].create(
                {
                    **self._class_row(self.pay, self.pay_group, "permission", "r"),
                    "domain": "[('id', '=', 1)]",
                }
            )

    def test_a_row_is_for_a_model_or_a_class(self):
        with self.assertRaises(Exception), self.env.cr.savepoint():
            self.env["ir.access"].create(
                {
                    **self._class_row(self.pay, self.pay_group, "permission", "r"),
                    "model_id": self.env["ir.model"]._get_id(MODEL),
                }
            )
        with self.assertRaises(Exception), self.env.cr.savepoint():
            self.env["ir.access"].create(
                {
                    "name": "neither",
                    "group_id": self.pay_group.id,
                    "kind": "permission",
                    "operation": "r",
                }
            )

    def test_the_refusal_names_the_class(self):
        self.env.ref("base.group_no_one").user_ids += self.plain
        records = self.env[MODEL].with_user(self.plain)
        message = records._get_field_access_message(records._fields["wage"], "read")
        self.assertIn("test_ir_access.pay", message)

    def test_groups_verdicts_follow_membership_changes(self):
        self.assertFalse(self.allowed(self.plain, MODEL, "system_note"))
        self.plain.group_ids = [Command.link(self.env.ref("base.group_system").id)]
        self.assertTrue(self.allowed(self.plain, MODEL, "system_note"))


class TestFieldClassViews(TransactionCase):
    # a class-gated field is dropped from the arch a non-holder is served,
    # like a groups= field, because the view compiler reads the class's rows

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pay_group = cls.env["res.groups"].create({"name": "Pay view readers"})
        cls.pay = cls.env["ir.access.class"].create({"name": "test_ir_access.pay"})
        cls.env["ir.access"].create(
            {
                "name": "pay read",
                "class_id": cls.pay.id,
                "group_id": cls.pay_group.id,
                "kind": "permission",
                "operation": "r",
            }
        )
        cls.view = cls.env["ir.ui.view"].create(
            {
                "name": "classified form",
                "model": "test_ir_access.classified",
                "arch": """
                    <form>
                        <field name="name"/>
                        <field name="wage"/>
                    </form>
                """,
            }
        )
        cls.reader = new_test_user(
            cls.env, login="fcv_reader", groups="base.group_user"
        )
        cls.reader.group_ids += cls.pay_group
        cls.plain = new_test_user(cls.env, login="fcv_plain", groups="base.group_user")

    def _arch_fields(self, user):
        from lxml import etree

        views = (
            self.env["test_ir_access.classified"]
            .with_user(user)
            .get_views([(self.view.id, "form")])
        )
        arch = etree.fromstring(views["views"]["form"]["arch"])
        return {node.get("name") for node in arch.iter("field")}

    def test_a_class_gated_field_is_dropped_for_a_non_holder(self):
        self.assertNotIn("wage", self._arch_fields(self.plain))
        self.assertIn("name", self._arch_fields(self.plain))

    def test_a_class_gated_field_is_kept_for_a_holder(self):
        self.assertIn("wage", self._arch_fields(self.reader))
