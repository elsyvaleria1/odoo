import secrets

from . import controllers
from . import models


def _update_webhook_user_password(env) -> None:
    user = env.ref(
        "device_access_control.user_access_device_webhook",
        raise_if_not_found=False,
    )
    if user:
        user.write({"password": secrets.token_urlsafe(32)})
