import logging
import time
from typing import Any

from odoo.libs.debug_log import DebugLog

from . import DatabaseCommand, open_environment

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class WarmAssets(DatabaseCommand):
    """Build a database's asset bundles before it takes traffic."""

    # run after a deploy, before the workers receive requests: every bundle and
    # lazy group, per website, compiles once here instead of in each cold
    # worker of each instance, and the classic bundles' SCSS with them
    name = "warm_assets"
    description = "Build the asset bundles of a database before it takes traffic"

    def __init__(self) -> None:
        super().__init__()
        self.add_config_arguments(self.parser)

    def run(self, args: list[str]) -> None:
        parsed_args, unknown = self.parse_args(args)
        dbname = self.bootstrap_config(parsed_args, extra_args=unknown)
        started = time.monotonic()
        with open_environment(dbname) as env:
            links = warm_asset_bundles(env)
        _logger.info(
            "Warmed %d asset urls of %s in %.1f s",
            len(links),
            dbname,
            time.monotonic() - started,
        )


def warm_asset_bundles(env: Any) -> list[str]:
    """Pregenerate every bundle once without a website, then once per website.

    :return: the asset urls built
    """
    qweb = env["ir.qweb"]
    links = list(qweb._pregenerate_assets_bundles())
    websites = env["website"].search([]) if "website" in env else ()
    for website in websites:
        # the frontend variants are keyed by website_id, which website's
        # _prepare_assets_params reads from the context outside a request
        links.extend(
            qweb.with_context(website_id=website.id)._pregenerate_assets_bundles()
        )
        _debug.pipeline("warm_assets.website", website=website.id, links=len(links))
    return links
