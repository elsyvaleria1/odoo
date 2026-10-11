from . import controllers
from . import models


def _create_social_accounts(env) -> None:
    env["website"].search([])._create_push_accounts()
