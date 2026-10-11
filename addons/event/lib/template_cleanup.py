from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo.models import BaseModel


def unlink_template_schedules(templates: BaseModel) -> None:
    domain = (
        "template_ref",
        "in",
        [f"{template._name},{template.id}" for template in templates],
    )
    templates.env["event.mail"].sudo().search([domain]).unlink()
    templates.env["event.type.mail"].sudo().search([domain]).unlink()
