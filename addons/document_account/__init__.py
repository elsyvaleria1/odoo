from . import models
from . import controllers
from . import wizards


def _documents_account_post_init(env) -> None:
    env["account.journal"].search(
        [
            (
                "id",
                "not in",
                env["document.account.folder.setting"]._search([]).select("journal_id"),
            )
        ]
    )._documents_configure_sync()
