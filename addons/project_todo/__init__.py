from . import models
from . import wizards


def _todo_post_init(env) -> None:
    env["res.users"].search([("share", "=", False)])._create_onboarding_todo()
