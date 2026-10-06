from . import models
from . import reports


def _create_livechat_channel(env) -> None:
    env["team.team"].search(
        [("use_website_helpdesk_livechat", "=", True)]
    )._create_livechat_channel()
