from . import lib
from . import tools
from . import models
from . import wizards


def post_init_hook(env) -> None:
    env["phone.number"]._rekey_sanitized()


def uninstall_hook(env) -> None:
    Phone = env["phone.number"]
    Phone._rekey_sanitized(rekey=Phone._get_rekeyed_sanitized_without_validation)
