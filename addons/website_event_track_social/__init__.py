from . import models


def post_init(env) -> None:
    env["event.track"].search([]).write(
        {
            "push_reminder": False,
            "push_reminder_delay": 0,
        }
    )
