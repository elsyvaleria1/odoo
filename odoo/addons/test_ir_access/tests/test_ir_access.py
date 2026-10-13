import re
from contextlib import contextmanager

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


class TestIrAccessCase(TransactionCase):
    MODEL = "test_ir_access.item"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group1 = cls.env["res.groups"].create({"name": "Group 1"})
        cls.group2 = cls.env["res.groups"].create({"name": "Group 2"})
        cls.group3 = cls.env["res.groups"].create({"name": "Group 3"})
        groups = cls.env.ref("base.group_user") + cls.group1 + cls.group2
        cls.user = cls.env["res.users"].create(
            {
                "login": "bob",
                "name": "Bob Bobman",
                "group_ids": [Command.set(groups.ids)],
            }
        )
        cls.env["ir.access"].search(
            [
                ("model_id.model", "like", "test_ir_access.%"),
                ("model_id.model", "!=", "test_ir_access.node"),
            ]
        ).unlink()
        cls.records = (
            cls.env[cls.MODEL]
            .create(
                [
                    {"name": name}
                    for name in ("Mario", "Luigi", "Peach", "Toad", "Yoshi", "Bowser")
                ]
            )
            .with_user(cls.user)
        )
        cls.mario, cls.luigi, cls.peach, cls.toad, cls.yoshi, cls.bowser = cls.records
        cls.model = cls.records.browse()

    def create_access(
        self,
        name="",
        records=None,
        group=None,
        operation="r",
        kind="permission",
        model=None,
        **kwargs,
    ):
        return self.env["ir.access"].create(
            {
                "name": name or "access",
                "model_id": self.env["ir.model"]._get_id(model or self.MODEL),
                "group_id": (group or self.env.ref("base.group_everyone")).id,
                "kind": kind,
                "operation": operation,
                "domain": str([("id", "in", records.ids)]) if records else False,
                **kwargs,
            }
        )

    def create_guard(self, name="", records=None, group=None, operation="r", **kwargs):
        return self.create_access(
            name, records, group, operation, kind="guard", **kwargs
        )

    def assertAccess(self, allowed, operation="read"):
        self.assertTrue(self.model.has_access(operation))
        self.model.check_access(operation)
        for record in self.records:
            if record in allowed:
                self.assertTrue(record.has_access(operation))
                record.check_access(operation)
            else:
                self.assertFalse(record.has_access(operation))
                with self.assertAccessError():
                    record.check_access(operation)
        allowed.check_access(operation)
        if self.records - allowed:
            with self.assertAccessError():
                self.records.check_access(operation)
        self.assertEqual(self.records._filtered_access(operation), allowed)
        if operation == "read":
            self.assertEqual(
                self.model.search([("id", "in", self.records.ids)], order="id"),
                allowed.sorted("id"),
            )

    @contextmanager
    def assertAccessError(self, message=None):
        with mute_logger("odoo.addons.base.models.ir_access"):
            if message:
                with self.assertRaisesRegex(
                    AccessError, re.compile(message, re.DOTALL)
                ):
                    yield
            else:
                with self.assertRaises(AccessError):
                    yield


class TestIrAccess(TestIrAccessCase):
    def test_a_context_without_companies_is_a_cache_key(self):
        self.create_access(records=self.mario + self.luigi)
        model = self.model.with_context(allowed_company_ids=[])
        self.assertEqual(tuple(model.env["ir.access"]._get_access_context())[0], ())
        self.model = model
        self.assertAccess(self.mario + self.luigi)

    def test_for_fields(self):
        access = self.create_access(records=self.records, operation="ru")
        self.assertTrue(access.for_read)
        self.assertTrue(access.for_write)
        self.assertFalse(access.for_create)
        self.assertFalse(access.for_unlink)

        access.operation = "cr"
        self.assertTrue(access.for_read)
        self.assertFalse(access.for_write)
        self.assertTrue(access.for_create)
        self.assertFalse(access.for_unlink)

        access.write({"for_write": True, "for_create": False})
        self.assertEqual(access.operation, "ru")

        access = self.env["ir.access"].create(
            {
                "name": "no operation",
                "model_id": self.env["ir.model"]._get_id(self.MODEL),
                "group_id": self.group1.id,
                "kind": "permission",
                "for_create": True,
            }
        )
        self.assertEqual(access.operation, "c")

    def test_a_guard_without_group_binds_everyone(self):
        self.create_access(group=self.group1)
        guard = self.env["ir.access"].create(
            {
                "name": "no group",
                "model_id": self.env["ir.model"]._get_id(self.MODEL),
                "kind": "guard",
                "operation": "r",
                "domain": str([("id", "in", self.mario.ids)]),
            }
        )

        self.assertEqual(guard.group_id, self.env.ref("base.group_everyone"))
        self.assertAccess(self.mario)

    def test_a_permission_without_group_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env["ir.access"].create(
                {
                    "name": "no group",
                    "model_id": self.env["ir.model"]._get_id(self.MODEL),
                    "kind": "permission",
                    "operation": "r",
                }
            )

    def test_a_row_naming_neither_kind_nor_group_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "names no group"):
            self.env["ir.access"].create(
                {
                    "name": "neither kind nor group",
                    "model_id": self.env["ir.model"]._get_id(self.MODEL),
                    "operation": "r",
                    "domain": str([("id", "in", self.mario.ids)]),
                }
            )

    def test_everyone_is_implied_by_every_user_type(self):
        everyone = self.env.ref("base.group_everyone")
        for xmlid in ("base.group_user", "base.group_portal", "base.group_public"):
            self.assertIn(everyone, self.env.ref(xmlid).all_implied_ids)
        self.assertIn(everyone, self.user.all_group_ids)
        self.assertIn(everyone, self.env.ref("base.public_user").all_group_ids)

    def test_sudo(self):
        records = self.records.sudo()
        for operation in ("read", "write", "create", "unlink"):
            self.assertTrue(records.has_access(operation))
            self.assertEqual(records._filtered_access(operation), records)
            records.check_access(operation)

    def test_no_access(self):
        for operation in ("read", "write", "create", "unlink"):
            self.assertFalse(self.records.has_access(operation))
            self.assertFalse(self.records._filtered_access(operation))
            with self.assertAccessError():
                self.records.check_access(operation)

    def test_a_guard_alone_grants_nothing(self):
        self.create_guard(records=self.records)

        self.assertFalse(self.model.has_access("read"))
        self.assertFalse(self.model.has_access("write"))
        self.assertFalse(self.records._filtered_access("read"))
        with self.assertAccessError():
            self.model.check_access("read")
        with self.assertAccessError():
            self.records.check_access("read")

    def test_one_permission(self):
        humans = self.mario + self.luigi + self.peach
        self.create_access(group=self.group1, operation="r")
        self.create_access(records=humans, group=self.group1, operation="u")

        self.assertAccess(self.records, "read")
        self.assertAccess(humans, "write")

    def test_two_permissions_in_group(self):
        self.create_access(records=self.mario + self.luigi, group=self.group1)
        self.create_access(records=self.mario + self.peach, group=self.group1)

        self.assertAccess(self.mario + self.luigi + self.peach)

    def test_two_permissions_in_distinct_groups(self):
        self.create_access(records=self.mario + self.luigi, group=self.group1)
        self.create_access(records=self.mario + self.peach, group=self.group2)
        self.create_access(records=self.mario + self.yoshi, group=self.group3)

        self.assertAccess(self.mario + self.luigi + self.peach)

    def test_one_permission_one_guard(self):
        self.create_access(
            records=self.mario + self.peach + self.bowser, group=self.group1
        )
        self.create_guard(records=self.records - self.bowser)

        self.assertAccess(self.mario + self.peach)

    def test_two_permissions_one_guard(self):
        self.create_access(
            records=self.mario + self.luigi + self.bowser, group=self.group1
        )
        self.create_access(
            records=self.mario + self.peach + self.bowser, group=self.group2
        )
        self.create_guard(records=self.records - self.bowser)

        self.assertAccess(self.mario + self.luigi + self.peach)

    def test_two_permissions_two_guards(self):
        self.create_access(
            records=self.mario + self.luigi + self.bowser, group=self.group1
        )
        self.create_access(
            records=self.mario + self.peach + self.bowser, group=self.group2
        )
        self.create_guard(records=self.records - self.bowser)
        self.create_guard(records=self.records - self.peach)

        self.assertAccess(self.mario + self.luigi)

    def test_special_user_manager(self):
        self.create_access(
            records=self.mario + self.luigi + self.bowser, group=self.group1
        )
        self.create_access(group=self.group2)
        self.create_guard(records=self.records - self.bowser)

        self.assertAccess(self.records - self.bowser)

    def test_guards_bind_their_operations_only(self):
        self.create_access(group=self.group1, operation="r")
        self.create_access(group=self.group2, operation="crud")
        self.create_guard(records=self.records - self.bowser, operation="cud")

        self.assertAccess(self.records, operation="read")
        self.assertAccess(self.records - self.bowser, operation="write")
        self.assertAccess(self.records - self.bowser, operation="create")
        self.assertAccess(self.records - self.bowser, operation="unlink")

    def test_a_member_guard_binds_only_the_members_of_its_group(self):
        self.create_access(group=self.group1)
        self.create_guard(
            records=self.mario + self.luigi, group=self.group3, guard_scope="members"
        )

        self.assertAccess(self.records)

        self.user.group_ids = [Command.link(self.group3.id)]
        self.assertAccess(self.mario + self.luigi)

    def test_adding_a_group_never_takes_records_away(self):
        self.create_access(records=self.mario + self.luigi, group=self.group1)
        self.create_access(records=self.peach, group=self.group3)
        self.create_guard(records=self.records - self.bowser)
        before = self.records._filtered_access("read")
        self.assertEqual(before, self.mario + self.luigi)

        self.user.group_ids = [Command.link(self.group3.id)]
        after = self.records._filtered_access("read")
        self.assertLessEqual(before, after)
        self.assertEqual(after, self.mario + self.luigi + self.peach)

    def test_a_domain_that_tests_the_user_s_groups_is_refused(self):
        for domain in (
            "[('id', '!=', user.has_group('base.group_system') and 0 or 1)]",
            "[('val', 'not in', user.group_ids.ids)]",
            "['!', ('id', 'in', user.all_group_ids.ids)]",
            "[('id', '=', 0)] if user.has_group('base.group_system') else []",
            "[('val', 'not in', user._get_effective_group_ids())]",
            "[('id', '!=', user.has_any_group_id([1]) and 0 or 1)]",
        ):
            with (
                self.subTest(domain=domain),
                self.assertRaisesRegex(ValidationError, "tests the user's groups"),
            ):
                self.create_access(group=self.group1, domain=domain)

    def test_a_domain_that_only_widens_with_the_user_s_groups_is_accepted(self):
        for domain in (
            "[('id', 'in', user.all_group_ids.ids)]",
            "[('val', 'in', user.group_ids.ids)]",
            "[] if user.has_group('base.group_system') else [('id', '=', 0)]",
            "['|', ('val', '=', False), ('val', 'in', group_ids)]",
            (
                "(['|', ('id', '=', 1)] if user.has_group('base.group_system') else [])"
                " + [('id', '=', 2)]"
            ),
        ):
            with self.subTest(domain=domain):
                self.create_access(group=self.group1, domain=domain)

    def test_an_invalid_domain_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "Invalid domain"):
            self.create_access(group=self.group1, domain="[('no_such_field', '=', 1)]")
        with self.assertRaisesRegex(ValidationError, "Invalid domain"):
            self.create_access(group=self.group1, domain="[('val', 'access', 'read')]")
        with self.assertRaisesRegex(ValidationError, "Invalid domain"):
            self.create_access(
                group=self.group1, domain="[('category_id', 'access', 'fly')]"
            )

    def test_a_row_that_does_not_evaluate_admits_nothing(self):
        self.create_access(records=self.mario, group=self.group1)
        broken = self.create_access(group=self.group2)
        self.env.cr.execute(
            "UPDATE ir_access SET domain = %s WHERE id = %s",
            [f"[('id', '=', 1 // (user.id - {self.user.id}))]", broken.id],
        )
        self.env.registry.clear_cache("stable")
        self.env.invalidate_all()

        with mute_logger("odoo.addons.base.models.ir_access"):
            self.assertAccess(self.mario)

    def test_a_guard_that_does_not_evaluate_lets_nothing_through(self):
        self.create_access(group=self.group1)
        broken = self.create_guard()
        self.env.cr.execute(
            "UPDATE ir_access SET domain = %s WHERE id = %s",
            [f"[('id', '=', 1 // (user.id - {self.user.id}))]", broken.id],
        )
        self.env.registry.clear_cache("stable")
        self.env.invalidate_all()

        with mute_logger("odoo.addons.base.models.ir_access"):
            self.assertFalse(self.model.has_access("read"))
            with self.assertAccessError():
                self.mario.check_access("read")

    def test_error_message_no_access(self):
        self.create_access(group=self.group3, operation="cd")

        with self.assertAccessError(
            r"You are not allowed to access.*No group currently allows this operation"
        ):
            self.records.check_access("read")
        with self.assertAccessError(
            r"You are not allowed to create.*"
            r"This operation is allowed for the following groups:\s*- Group 3"
        ):
            self.records.check_access("create")

    def test_error_message_names_the_failing_rows(self):
        humans = self.records[:3]
        self.create_access("See good guys", records=self.records[:5], group=self.group1)
        self.create_guard("Restrict to humans", records=humans)

        self.assertEqual(self.records._filtered_access("read"), humans)
        with self.assertAccessError(
            rf"Sorry, Bob Bobman \(id={self.user.id}\) doesn't have 'read' access to:\s*"
            r"- Item read through ir.access \(test_ir_access\.item\)\s*"
            r"Refused by: Restrict to humans\s*Ask: [^\n]+\s*"
            r"If you really"
        ):
            self.records.check_access("read")

        with (
            self.debug_mode(),
            self.assertAccessError(
                r"Blame the following accesses:\s*- See good guys\s*- Restrict to humans"
            ),
        ):
            self.records.check_access("read")

    def test_customize_edits_a_copy_of_a_module_row(self):
        standard = self.env.ref("test_ir_access.access_node_system")
        self.assertTrue(standard.is_standard)
        self.assertIn(
            standard, self.env["ir.access"].search([("is_standard", "=", True)])
        )
        action = standard.customize()
        copy = self.env["ir.access"].browse(action["res_id"])
        self.assertNotEqual(copy, standard)
        self.assertFalse(standard.active)
        self.assertFalse(copy.is_standard)
        self.assertEqual(copy.customize()["res_id"], copy.id)

    def test_every_model_reads_its_access_from_ir_access(self):
        partner = self.env["res.partner"].create({"name": "Somebody"})
        self.assertTrue(partner.with_user(self.user).has_access("read"))
        self.create_guard(model="res.partner", domain="[(0, '=', 1)]")
        self.assertFalse(partner.with_user(self.user).has_access("read"))


class TestCompanySelectionKey(TestIrAccessCase):
    def test_the_selection_keys_the_cache_whatever_its_order(self):
        Access = self.env["ir.access"]

        def key(companies):
            return Access.with_context(
                allowed_company_ids=companies
            )._policy_signature()

        self.assertEqual(key([4, 2, 3]), key([4, 3, 2]))
        self.assertNotEqual(key([4, 2, 3]), key([2, 4, 3]))
        self.assertEqual(hash(key([])), hash(key([])))

    def test_a_search_asking_no_company_is_answered(self):
        partners = (
            self.env["res.partner"]
            .with_user(self.user)
            .with_context(allowed_company_ids=[])
            .search([], limit=1)
        )
        self.assertTrue(partners)


@tagged("post_install", "-at_install")
class TestStaleRows(TestIrAccessCase):
    def test_a_row_naming_a_field_its_model_lost_admits_nothing(self):
        self.create_access(records=self.luigi, group=self.group1)
        stale = self.create_access(group=self.group2)
        self.env.cr.execute(
            "UPDATE ir_access SET domain = %s WHERE id = %s",
            ["[('no_such_field', '=', 1)]", stale.id],
        )
        self.env.registry.clear_cache("stable")
        self.env.invalidate_all()

        with mute_logger("odoo.addons.base.models.ir_access"):
            self.assertAccess(self.luigi)


class TestGroupLabels(TestIrAccessCase):
    def test_a_group_does_not_name_a_record_its_reader_cannot_read(self):
        Category = self.env["test_ir_access.category"]
        hidden, shown = Category.create([{"name": "Secret"}, {"name": "Public"}])
        self.mario.sudo().category_id = hidden
        self.luigi.sudo().category_id = shown
        self.create_access(group=self.group1)
        self.create_access(
            records=shown, group=self.group1, model="test_ir_access.category"
        )

        groups = self.model.read_group(
            [("id", "in", (self.mario + self.luigi).ids)],
            ["category_id"],
            ["category_id"],
        )

        labels = {group["category_id"][0]: group["category_id"][1] for group in groups}
        self.assertEqual(labels, {hidden.id: "", shown.id: "Public"})


class TestConditionalReach(TestIrAccessCase):
    def ceiling(self, **args):
        role = self.group1._add_missing_xml_ids()[self.group1.id]
        return self.create_guard(
            group=self.group1,
            guard_scope="members",
            reach="predicate",
            predicate_id=self.env.ref("base.access_predicate_conditional_reach").id,
            predicate_args={"operation": "read", "role": role, **args},
        )

    def test_a_restricted_role_is_bounded_by_its_conditional_accesses(self):
        self.create_access(records=self.mario + self.luigi, group=self.group1)
        self.create_access(group=self.group2)
        self.assertAccess(self.records)

        self.ceiling()

        self.assertAccess(self.mario + self.luigi)

    def test_a_wider_variant_of_the_role_lifts_the_ceiling(self):
        wider = self.env["res.groups"].create(
            {
                "name": "Group 1, every record",
                "implied_ids": [Command.link(self.group1.id)],
            }
        )
        self.create_access(records=self.mario, group=self.group1)
        self.create_access(group=wider)
        self.user.group_ids = [Command.link(wider.id)]

        self.ceiling()

        self.assertAccess(self.records)

    def test_a_group_the_role_names_counts_as_its_own(self):
        self.create_access(records=self.mario, group=self.group1)
        self.create_access(group=self.group2)

        self.ceiling(**{"with": [self.group2._add_missing_xml_ids()[self.group2.id]]})

        self.assertAccess(self.records)


class TestAccessOperator(TestIrAccessCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Category = cls.env["test_ir_access.category"]
        cls.heroes, cls.villains = Category.create(
            [{"name": "Heroes"}, {"name": "Villains"}]
        )
        (cls.records - cls.bowser).sudo().category_id = cls.heroes
        cls.bowser.sudo().category_id = cls.villains

    def delegate_to_category(self, operation="read"):
        return self.create_access(
            "through the category",
            group=self.group1,
            domain=str([("category_id", "access", operation)]),
        )

    def test_a_record_is_reachable_when_its_category_is(self):
        self.delegate_to_category()
        self.create_access(
            records=self.heroes, group=self.group1, model="test_ir_access.category"
        )
        self.assertAccess(self.records - self.bowser)

    def test_no_access_to_the_category_is_no_access_to_the_model(self):
        self.delegate_to_category()
        self.assertFalse(self.model.has_access("read"))
        self.assertFalse(self.records._filtered_access("read"))

    def test_the_operator_reads_the_category_s_own_operation(self):
        self.delegate_to_category("write")
        self.create_access(group=self.group1, model="test_ir_access.category")
        self.create_access(
            records=self.villains,
            group=self.group1,
            operation="u",
            model="test_ir_access.category",
        )
        self.assertAccess(self.bowser)

    def test_a_read_verdict_follows_a_write_the_category_rule_reads(self):
        self.delegate_to_category()
        self.create_access(
            group=self.group1,
            model="test_ir_access.category",
            domain="[('name', '!=', 'Hidden')]",
        )
        self.assertTrue(self.mario.has_access("read"))
        self.heroes.sudo().name = "Hidden"
        self.assertFalse(self.mario.has_access("read"))
        self.assertTrue(self.bowser.has_access("read"))

    def test_a_cycle_through_the_operator_is_refused(self):
        self.delegate_to_category()
        with self.assertRaisesRegex(
            ValidationError,
            r"form a cycle: .*test_ir_access\.category\.read.*test_ir_access\.item\.read",
        ):
            self.create_access(
                group=self.group2,
                model="test_ir_access.category",
                domain=str([("featured_item_id", "access", "read")]),
            )

    def test_a_self_referencing_row_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "form a cycle"):
            self.create_access(
                group=self.group1,
                model="test_ir_access.node",
                domain=str(
                    ["|", ("parent_id", "=", False), ("parent_id", "access", "read")]
                ),
            )

    def test_a_cycle_written_behind_the_constraint_fails_clearly(self):
        self.delegate_to_category()
        back = self.create_access(group=self.group2, model="test_ir_access.category")
        self.env.cr.execute(
            "UPDATE ir_access SET domain = %s WHERE id = %s",
            [str([("featured_item_id", "access", "read")]), back.id],
        )
        self.env.registry.clear_cache("stable")
        self.env.invalidate_all()
        with self.assertRaisesRegex(ValueError, "form a cycle"):
            self.model.search([])


class TestDelegatedAccess(TestIrAccessCase):
    def test_a_stored_delegate_binds_its_parent_s_access(self):
        self._check_delegation("test_ir_access.delegated", "item_id")

    def test_a_computed_delegate_binds_its_parent_s_access(self):
        self._check_delegation("test_ir_access.delegated_computed", "held_id")

    def test_a_domain_computed_under_sudo_keeps_the_parent_s_access(self):
        children = self.env["test_ir_access.delegated"].create(
            [{"item_id": record.id} for record in self.mario + self.bowser]
        )
        allowed = children[0]
        self.create_access(group=self.group1, model="test_ir_access.delegated")
        self.create_access(records=self.mario, group=self.group1)
        user_children = children.with_user(self.user)

        user_children.sudo()._access_domain("read")

        self.assertEqual(
            user_children.search([("id", "in", children.ids)]),
            allowed.with_user(self.user),
        )
        with self.assertAccessError():
            children[1].with_user(self.user).check_access("read")

    def _check_delegation(self, model_name, link):
        children = self.env[model_name].create(
            [{link: record.id} for record in self.mario + self.bowser]
        )
        allowed, forbidden = children
        self.create_access(group=self.group1, model=model_name)
        user_children = children.with_user(self.user)
        self.assertFalse(user_children.browse().has_access("read"))

        self.create_access(records=self.mario, group=self.group1)
        self.assertEqual(
            user_children.search([("id", "in", children.ids)]),
            allowed.with_user(self.user),
        )
        self.assertEqual(user_children._filtered_access("read"), allowed)
        with self.assertAccessError():
            forbidden.with_user(self.user).check_access("read")


class TestRetiredAccessTables(TestIrAccessCase):
    def test_rows_do_not_load_while_an_id_still_names_an_old_record(self):
        self.env["ir.model.data"].create(
            {
                "module": "test_ir_access",
                "name": "an_unconverted_rule",
                "model": "ir.rule",
                "res_id": 1,
            }
        )
        data = {
            "xml_id": "test_ir_access.a_row_of_a_module_file",
            "values": {
                "name": "row",
                "model_id": self.env["ir.model"]._get_id(self.MODEL),
                "group_id": self.group1.id,
                "kind": "permission",
                "operation": "r",
            },
        }
        with self.assertRaisesRegex(UserError, r"-u base"):
            self.env["ir.access"]._load_records([data])

    def test_a_group_guard_loaded_without_its_scope_is_refused(self):
        def load(name, **values):
            return self.env["ir.access"]._load_records(
                [
                    {
                        "xml_id": f"test_ir_access.{name}",
                        "values": {
                            "name": "guard",
                            "model_id": self.env["ir.model"]._get_id(self.MODEL),
                            "kind": "guard",
                            "operation": "u",
                            "domain": "[('id', '=', 0)]",
                            **values,
                        },
                    }
                ]
            )

        with self.assertRaisesRegex(ValidationError, "does not say whom it binds"):
            load("unscoped_guard", group_id=self.group1.id)
        members = load("member_guard", group_id=self.group1.id, guard_scope="members")
        self.assertEqual(members.guard_scope, "members")
        everyone = load(
            "everyone_guard", group_id=self.env.ref("base.group_everyone").id
        )
        self.assertEqual(everyone.guard_scope, "everyone")

    def test_the_failing_guard_is_blamed_by_name(self):
        self.create_access(group=self.group1, operation="ru")
        self.create_guard("only mario", records=self.mario, operation="u")
        with (
            self.debug_mode(),
            self.assertAccessError(r"Blame the following accesses:\s*- only mario"),
        ):
            self.luigi.check_access("write")


class TestGroupsWithAccess(TestIrAccessCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.carol = cls.env["res.users"].create(
            {
                "login": "carol",
                "name": "Carol",
                "group_ids": [
                    Command.set((cls.env.ref("base.group_user") + cls.group3).ids)
                ],
            }
        )

    def groups(self, model, operation="read"):
        groups = self.env["ir.access"]._get_groups_with_access(model, operation)
        return groups & (self.group1 + self.group2 + self.group3)

    def test_a_row_through_the_access_operator_needs_the_pointed_access(self):
        self.create_access(
            group=self.group1, domain=str([("category_id", "access", "read")])
        )
        self.create_access(group=self.group2, model="test_ir_access.category")
        self.assertFalse(self.groups(self.MODEL))
        with self.assertAccessError("No group currently allows this operation"):
            self.env[self.MODEL].with_user(self.carol).check_access("read")

        self.create_access(group=self.group1, model="test_ir_access.category")
        self.assertEqual(self.groups(self.MODEL), self.group1)
        with self.assertAccessError(
            r"allowed for the following groups:\s*- Group 1\s*Ask: [^\n]+\s*Contact"
        ):
            self.env[self.MODEL].with_user(self.carol).check_access("read")

    def test_the_model_s_own_guard_needs_its_access_too(self):
        self.create_access(group=self.group1, model="test_ir_access.guarded")
        self.create_access(group=self.group2, model="test_ir_access.category")
        self.assertFalse(self.groups("test_ir_access.guarded"))
        self.create_access(group=self.group1, model="test_ir_access.category")
        self.assertEqual(self.groups("test_ir_access.guarded"), self.group1)

    def test_a_path_through_the_access_operator_needs_the_pointed_access(self):
        self.create_access(
            group=self.group1,
            model="test_ir_access.guarded",
            domain=str([("category_id.featured_item_id", "access", "read")]),
        )
        self.create_access(group=self.group1, model="test_ir_access.category")
        self.create_access(group=self.group2)
        self.assertFalse(self.groups("test_ir_access.guarded"))
        self.create_access(group=self.group1)
        self.assertEqual(self.groups("test_ir_access.guarded"), self.group1)

    def test_a_nested_access_condition_needs_the_pointed_access(self):
        self.create_access(
            group=self.group1,
            model="test_ir_access.guarded",
            domain=str(
                [("category_id", "any", [("featured_item_id", "access", "read")])]
            ),
        )
        self.create_access(group=self.group1, model="test_ir_access.category")
        self.create_access(group=self.group2)
        self.assertFalse(self.groups("test_ir_access.guarded"))
        self.create_access(group=self.group1)
        self.assertEqual(self.groups("test_ir_access.guarded"), self.group1)

    def test_a_delegated_parent_needs_its_access_too(self):
        self.create_access(group=self.group1, model="test_ir_access.delegated")
        self.create_access(group=self.group2)
        self.assertFalse(self.groups("test_ir_access.delegated"))
        self.create_access(group=self.group1)
        self.assertEqual(self.groups("test_ir_access.delegated"), self.group1)


class TestFailedAccesses(TestIrAccessCase):
    def test_the_delegated_parent_s_rows_are_blamed(self):
        children = self.env["test_ir_access.delegated"].create(
            [{"item_id": record.id} for record in self.mario + self.bowser]
        )
        self.create_access(group=self.group1, model="test_ir_access.delegated")
        self.create_access("only mario items", records=self.mario, group=self.group1)
        forbidden = children[1].with_user(self.user)
        with (
            self.debug_mode(),
            self.assertAccessError(
                r"Blame the following accesses:\s*"
                r"- only mario items \(through item_id, test_ir_access\.item\)"
            ),
        ):
            forbidden.check_access("read")

    def test_the_model_s_own_guard_is_blamed(self):
        hidden = self.env["test_ir_access.category"].create({"name": "Hidden"})
        record = self.env["test_ir_access.guarded"].create(
            {"name": "g", "category_id": hidden.id}
        )
        self.create_access(group=self.group1, model="test_ir_access.guarded")
        self.create_access(
            group=self.group1,
            model="test_ir_access.category",
            domain="[('name', '!=', 'Hidden')]",
        )
        with (
            self.debug_mode(),
            self.assertAccessError(
                r"Blame the following accesses:\s*"
                r"- the condition of test_ir_access\.guarded itself"
            ),
        ):
            record.with_user(self.user).check_access("read")


class TestOwnerThroughTheAccessOperator(TestIrAccessCase):
    def test_an_owned_record_follows_its_many2one_owner(self):
        owned = self.env["test_ir_access.owned"].create(
            [
                {"name": "of mario", "item_id": self.mario.id},
                {"name": "of bowser", "item_id": self.bowser.id},
                {"name": "of nobody"},
            ]
        )
        of_mario, of_bowser, of_nobody = owned
        self.create_access(group=self.group1, model="test_ir_access.owned")
        self.create_access(records=self.mario, group=self.group1)
        as_user = self.env["test_ir_access.owned"].with_user(self.user)
        self.assertTrue(as_user._access_owner_delegates())
        self.assertEqual(
            as_user.search([("id", "in", owned.ids)]),
            (of_mario + of_nobody).with_user(self.user),
        )
        of_mario.with_user(self.user).check_access("read")
        with self.assertAccessError():
            of_bowser.with_user(self.user).check_access("read")

    def test_owned_records_check_their_owners_in_one_query_per_model(self):
        Owned = self.env["test_ir_access.owned"]
        Owned.create({"name": "warm", "item_id": self.mario.id})
        self.env.flush_all()
        with self.assertQueryCount(2):
            Owned.create(
                [{"name": "owned", "item_id": item_id} for item_id in self.records.ids]
            )
