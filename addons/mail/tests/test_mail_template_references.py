import re

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

EXPRESSION_FIELDS = (
    "body_html",
    "subject",
    "email_from",
    "email_to",
    "email_cc",
    "partner_to",
    "reply_to",
    "scheduled_date",
)

MODEL_LITERAL = re.compile(r"""env\[['"]([a-z_][a-z0-9_.]*)['"]\]""")


@tagged("mail_tools", "-at_install", "post_install")
class TestMailTemplateReferences(TransactionCase):
    def _shipped_templates(self):
        data = self.env["ir.model.data"].search([("model", "=", "mail.template")])
        return (
            self.env["mail.template"]
            .with_context(active_test=False)
            .browse(data.mapped("res_id"))
            .exists()
        )

    def _expressions(self, template):
        return [str(template[name] or "") for name in EXPRESSION_FIELDS]

    def test_every_shipped_template_names_a_live_model(self):
        broken = []
        for template in self._shipped_templates():
            for body in self._expressions(template):
                broken.extend(
                    f"{template.name} (id {template.id}): env[{name!r}]"
                    for name in sorted(set(MODEL_LITERAL.findall(body)))
                    if name not in self.env
                )
        self.assertFalse(
            broken,
            "mail templates naming a model the registry does not have:\n  "
            + "\n  ".join(broken),
        )

    def test_every_shipped_template_names_a_live_field(self):
        # the analysis a save runs, guards and guard variables included, so a
        # shipped template reads here exactly as it would be judged when edited
        broken = []
        for template in self._shipped_templates():
            if not template.model or template.model not in self.env:
                continue
            fnames = template._get_dynamic_field_names()
            if failure := template._compile_dynamic_fields(fnames):
                fname, error = failure
                broken.append(f"{template.name} (id {template.id}) {fname}: {error}")
        self.assertFalse(
            broken,
            "mail templates reading a field that does not exist:\n  "
            + "\n  ".join(sorted(broken)),
        )

    def test_every_template_model_column_agrees_with_its_model_id(self):
        drifted = [
            f"{template.name} (id {template.id}): "
            f"model={template.model!r} but model_id names "
            f"{template.model_id.model!r}"
            for template in self.env["mail.template"]
            .with_context(active_test=False)
            .search([])
            if template.model != template.model_id.model
        ]
        self.assertFalse(
            drifted,
            "mail templates whose model column never caught up:\n  "
            + "\n  ".join(drifted),
        )
