from . import models
from . import reports


def _update_skills_for_confirmed(env) -> None:
    confirmed_appraisals = env["hr.appraisal"].search(
        [("state", "=", "2_pending"), ("appraisal_skill_ids", "=", False)]
    )
    confirmed_appraisals._copy_skills_when_confirmed()
