from lxml import etree

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase
from odoo.tests.form import Form
from odoo.tools import is_html_empty
from odoo.tools.safe_eval import safe_eval


class TestDescriptionTemplate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Template = cls.env["project.task.description.template"]
        cls.Task = cls.env["project.task"]
        cls.company = cls.env.company
        cls.other_company = cls.env["res.company"].create({"name": "Tpl Other Co"})
        cls.project = cls.env["project.project"].create(
            {"name": "Tpl Project", "company_id": cls.company.id}
        )
        cls.other_project = cls.env["project.project"].create(
            {"name": "Tpl Other Project", "company_id": cls.company.id}
        )
        cls.template = cls.Template.create(
            {"name": "Tpl Shared", "description": "<p>BODY</p>"}
        )
        cls.restricted = cls.Template.create(
            {
                "name": "Tpl Restricted",
                "description": "<p>ONLY HERE</p>",
                "project_ids": [(6, 0, [cls.project.id])],
            }
        )

    def _onchange_project(self, task_form_values, changed_field):
        spec = dict.fromkeys(task_form_values, "1")
        return self.Task.onchange(task_form_values, [changed_field], spec)


    def test_onchange_fills_an_empty_description(self):
        form = Form(self.Task)
        form.name = "Task A"
        form.project_id = self.project
        form.description_template_id = self.template
        self.assertEqual(str(form.description), str(self.template.description))

    def test_onchange_keeps_a_description_the_user_already_wrote(self):
        form = Form(self.Task)
        form.name = "Task B"
        form.project_id = self.project
        form.description = "<p>MINE</p>"
        form.description_template_id = self.template
        self.assertIn("MINE", str(form.description))

    def test_action_apply_template_overwrites_the_description(self):
        task = self.Task.create(
            {
                "name": "Task C",
                "project_id": self.project.id,
                "description": "<p>MINE</p>",
                "description_template_id": self.template.id,
            }
        )
        task.action_apply_template()
        self.assertEqual(str(task.description), str(self.template.description))

    def test_switching_template_replaces_the_previous_template_body(self):
        other = self.Template.create(
            {"name": "Tpl Second", "description": "<p>SECOND BODY</p>"}
        )
        form = Form(self.Task)
        form.name = "Task B2"
        form.project_id = self.project
        form.description_template_id = self.template
        task = form.save()

        form = Form(task)
        form.description_template_id = other
        self.assertEqual(str(form.description), str(other.description))
        task = form.save()
        self.assertEqual(str(task.description), str(other.description))

    def test_switching_template_keeps_a_description_the_user_edited(self):
        other = self.Template.create(
            {"name": "Tpl Third", "description": "<p>THIRD BODY</p>"}
        )
        task = self.Task.create(
            {
                "name": "Task B3",
                "project_id": self.project.id,
                "description": "<p>MINE</p>",
                "description_template_id": self.template.id,
            }
        )
        form = Form(task)
        form.description_template_id = other
        self.assertIn("MINE", str(form.description))


    def test_button_hidden_while_the_description_matches_the_template(self):
        form = Form(self.Task)
        form.name = "Task D"
        form.project_id = self.project
        form.description_template_id = self.template
        self.assertFalse(
            form.show_apply_template,
            "the button must not offer to replace the text with itself",
        )
        task = form.save()
        self.assertFalse(task.show_apply_template)

    def test_button_shown_once_the_description_differs(self):
        task = self.Task.create(
            {
                "name": "Task E",
                "project_id": self.project.id,
                "description": "<p>EDITED</p>",
                "description_template_id": self.template.id,
            }
        )
        self.assertTrue(task.show_apply_template)
        task.action_apply_template()
        self.assertFalse(task.show_apply_template)

    def test_button_shown_when_the_description_is_still_empty(self):
        task = self.Task.create(
            {
                "name": "Task E2",
                "project_id": self.project.id,
                "description_template_id": self.template.id,
            }
        )
        self.assertTrue(is_html_empty(task.description))
        self.assertTrue(task.show_apply_template)
        task.action_apply_template()
        self.assertEqual(str(task.description), str(self.template.description))
        self.assertFalse(task.show_apply_template)

    def test_button_hidden_when_the_template_body_is_empty_too(self):
        blank = self.Template.create(
            {"name": "Tpl Blank", "description": "<p><br></p>"}
        )
        task = self.Task.create(
            {
                "name": "Task E3",
                "project_id": self.project.id,
                "description_template_id": blank.id,
            }
        )
        self.assertFalse(
            task.show_apply_template,
            "applying an empty body over an empty description changes nothing",
        )

    def test_button_hidden_without_a_template(self):
        task = self.Task.create(
            {
                "name": "Task F",
                "project_id": self.project.id,
                "description": "<p>OWN TEXT</p>",
            }
        )
        self.assertFalse(task.show_apply_template)


    def test_switching_project_warns_and_keeps_the_description(self):
        values = {
            "name": "Task G",
            "project_id": self.other_project.id,
            "description_template_id": self.restricted.id,
            "description": "<p>ONLY HERE</p>",
        }
        result = self._onchange_project(values, "project_id")
        self.assertTrue(
            result.get("warning"), "dropping the template must not be silent"
        )
        self.assertIn(self.restricted.name, result["warning"]["message"])
        self.assertFalse(result["value"].get("description_template_id"))
        self.assertNotIn(
            "description",
            result["value"],
            "the description is the user's, it must be left alone",
        )

    def test_switching_to_a_covered_project_keeps_the_template(self):
        values = {
            "name": "Task H",
            "project_id": self.project.id,
            "description_template_id": self.restricted.id,
            "description": "<p>ONLY HERE</p>",
        }
        result = self._onchange_project(values, "project_id")
        self.assertFalse(result.get("warning"))

    def test_the_core_project_onchange_is_not_shadowed(self):
        parent = self.Task.create({"name": "Task G0", "project_id": self.project.id})
        values = {
            "name": "Task G1",
            "parent_id": parent.id,
            "project_id": False,
        }
        result = self._onchange_project(values, "project_id")
        self.assertEqual(
            result["value"].get("project_id"),
            self.project.id,
            "core's _onchange_project_id no longer runs",
        )


    def test_template_restricted_to_another_project_is_refused(self):
        with self.assertRaises(ValidationError):
            self.Task.create(
                {
                    "name": "Task I",
                    "project_id": self.other_project.id,
                    "description_template_id": self.restricted.id,
                }
            )

    def test_moving_a_task_out_of_the_template_projects_is_refused(self):
        task = self.Task.create(
            {
                "name": "Task J",
                "project_id": self.project.id,
                "description_template_id": self.restricted.id,
            }
        )
        with self.assertRaises(ValidationError):
            task.write({"project_id": self.other_project.id})

    def test_restricted_template_is_allowed_without_a_project(self):
        task = self.Task.create(
            {"name": "Task K", "description_template_id": self.restricted.id}
        )
        self.assertEqual(task.description_template_id, self.restricted)

    def test_template_of_another_company_is_refused(self):
        foreign = self.Template.create(
            {
                "name": "Tpl Foreign",
                "description": "<p>x</p>",
                "company_id": self.other_company.id,
            }
        )
        with self.assertRaises(ValidationError):
            self.Task.create(
                {
                    "name": "Task L",
                    "project_id": self.project.id,
                    "description_template_id": foreign.id,
                }
            )

    def test_company_less_template_is_allowed_on_any_task(self):
        globl = self.Template.create(
            {"name": "Tpl Global", "description": "<p>x</p>", "company_id": False}
        )
        task = self.Task.create(
            {
                "name": "Task M",
                "project_id": self.project.id,
                "description_template_id": globl.id,
            }
        )
        self.assertEqual(task.description_template_id, globl)

    def test_any_template_is_allowed_on_a_company_less_task(self):
        shared_project = self.env["project.project"].create(
            {"name": "Tpl Shared Project", "company_id": False}
        )
        foreign = self.Template.create(
            {
                "name": "Tpl Foreign Two",
                "description": "<p>x</p>",
                "company_id": self.other_company.id,
            }
        )
        task = self.Task.create(
            {
                "name": "Task N",
                "project_id": shared_project.id,
                "description_template_id": foreign.id,
            }
        )
        self.assertFalse(task.company_id)
        self.assertEqual(task.description_template_id, foreign)


    def test_narrowing_the_template_projects_under_a_task_is_refused(self):
        task = self.Task.create(
            {
                "name": "Task O",
                "project_id": self.project.id,
                "description_template_id": self.restricted.id,
            }
        )
        with self.assertRaises(ValidationError) as caught:
            self.restricted.write({"project_ids": [(6, 0, [self.other_project.id])]})
        self.assertIn(task.display_name, str(caught.exception))

    def test_switching_the_template_company_under_a_task_is_refused(self):
        template = self.Template.create(
            {
                "name": "Tpl Movable",
                "description": "<p>x</p>",
                "company_id": self.company.id,
            }
        )
        task = self.Task.create(
            {
                "name": "Task P",
                "project_id": self.project.id,
                "description_template_id": template.id,
            }
        )
        self.assertEqual(task.company_id, self.company)
        with self.assertRaises(ValidationError):
            template.write({"company_id": self.other_company.id})

    def test_narrowing_a_template_no_task_uses_is_allowed(self):
        self.restricted.write({"project_ids": [(6, 0, [self.other_project.id])]})
        self.assertEqual(self.restricted.project_ids, self.other_project)

    def test_widening_the_template_projects_is_always_allowed(self):
        self.Task.create(
            {
                "name": "Task Q",
                "project_id": self.project.id,
                "description_template_id": self.restricted.id,
            }
        )
        self.restricted.write(
            {"project_ids": [(6, 0, [self.project.id, self.other_project.id])]}
        )
        self.assertIn(self.project, self.restricted.project_ids)


    def test_the_field_lands_in_the_header_group_not_in_a_subtask_list(self):
        arch = etree.fromstring(
            self.Task.get_view(self.env.ref("project.view_task_form2").id, "form")[
                "arch"
            ]
        )
        nodes = arch.xpath("//field[@name='description_template_id']")
        self.assertEqual(len(nodes), 1)
        ancestors = [parent.tag for parent in nodes[0].iterancestors()]
        self.assertNotIn(
            "list", ancestors, "a label, a div and a button are invalid there"
        )
        self.assertIn("group", ancestors)


    def _template_domain_for(self, task):
        source = self.Task._fields["description_template_id"]._description_domain(
            self.env
        )
        return safe_eval(
            source,
            {"company_id": task.company_id.id, "project_id": task.project_id.id},
        )

    def test_the_domain_carries_a_company_predicate(self):
        source = self.Task._fields["description_template_id"]._description_domain(
            self.env
        )
        self.assertIn("company_id", source)

    def test_the_domain_hides_a_template_of_another_company(self):
        foreign = self.Template.create(
            {
                "name": "Tpl Domain Foreign",
                "description": "<p>x</p>",
                "company_id": self.other_company.id,
            }
        )
        mine = self.Template.create(
            {
                "name": "Tpl Domain Mine",
                "description": "<p>x</p>",
                "company_id": self.company.id,
            }
        )
        shared = self.Template.create(
            {
                "name": "Tpl Domain Shared",
                "description": "<p>x</p>",
                "company_id": False,
            }
        )
        task = self.Task.create({"name": "Task R", "project_id": self.project.id})
        self.assertEqual(task.company_id, self.company)
        offered = self.Template.search(
            self._template_domain_for(task)
            + [("id", "in", (foreign | mine | shared).ids)]
        )
        self.assertEqual(offered, mine | shared)

    def test_the_domain_offers_only_shared_templates_to_a_company_less_task(self):
        shared_project = self.env["project.project"].create(
            {"name": "Tpl Domain Shared Project", "company_id": False}
        )
        mine = self.Template.create(
            {
                "name": "Tpl Domain Mine Two",
                "description": "<p>x</p>",
                "company_id": self.company.id,
            }
        )
        shared = self.Template.create(
            {
                "name": "Tpl Domain Shared Two",
                "description": "<p>x</p>",
                "company_id": False,
            }
        )
        task = self.Task.create({"name": "Task S", "project_id": shared_project.id})
        self.assertFalse(task.company_id)
        offered = self.Template.search(
            self._template_domain_for(task) + [("id", "in", (mine | shared).ids)]
        )
        self.assertEqual(offered, shared)

    def test_the_company_less_asymmetry_is_documented_on_the_field(self):
        field = self.Task._fields["description_template_id"]
        self.assertTrue(field.help, "the asymmetry has to be written down")
        self.assertIn("company", field.help)


    def test_archived_template_is_hidden_from_a_plain_search(self):
        self.template.active = False
        self.assertFalse(self.Template.search([("name", "=", self.template.name)]))

    def test_archived_template_is_reachable_through_the_archived_filter(self):
        self.template.active = False
        found = self.Template.with_context(active_test=False).search(
            [("active", "=", False), ("name", "=", self.template.name)]
        )
        self.assertEqual(found, self.template)

    def test_the_action_points_at_a_search_view_offering_that_filter(self):
        action = self.env.ref(
            "project_task_description_template.project_task_description_template_action"
        )
        self.assertTrue(
            action.search_view_id,
            "without a search view the Archived filter is unreachable",
        )
        arch = self.Template.get_view(
            view_id=action.search_view_id.id, view_type="search"
        )["arch"]
        self.assertIn('name="inactive"', arch)
