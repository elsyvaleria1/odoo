from . import models
from . import reports
from . import wizards


def uninstall_hook(env):
    act_window = env.ref("mass_mailing.mailing_mailing_action_mail", False)
    if (
        act_window
        and act_window.domain
        and "use_in_marketing_automation" in act_window.domain
    ):
        act_window.domain = [("mailing_type", "=", "mail")]
