from . import models
from . import wizards


def _create_assessment_notes(env) -> None:
    default_notes = env["res.company"]._prepare_default_assessment_note_commands()
    default_confirmation_mail_template = env[
        "res.company"
    ]._get_default_appraisal_confirm_mail_template()

    env["res.company"].search([]).write(
        {
            "assessment_note_ids": default_notes,
            "appraisal_confirm_mail_template": default_confirmation_mail_template.id,
        }
    )
