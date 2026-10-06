from . import models
from . import wizards


def _uninstall_hook(env) -> None:
    act_window = env.ref(
        "mass_mailing_sms.mailing_mailing_action_sms", raise_if_not_found=False
    )
    if (
        act_window
        and act_window.domain
        and "use_in_marketing_automation" in act_window.domain
    ):
        act_window.domain = [("mailing_type", "=", "sms")]
