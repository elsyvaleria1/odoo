import logging
import time
from typing import Any, override

from odoo.libs.debug_log import DebugLog

from . import DatabaseCommand, open_environment

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class WarmAssets(DatabaseCommand):
    name = "warm_assets"
    description = "Build the asset bundles of a database before it takes traffic"

    def __init__(self) -> None:
        super().__init__()
        self.add_config_arguments(self.parser)

    @override
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
    qweb = env["ir.qweb"]
    links = list(qweb._pregenerate_assets_bundles())
    websites = env["website"].search([]) if "website" in env else ()
    for website in websites:
        links.extend(
            qweb.with_context(website_id=website.id)._pregenerate_assets_bundles()
        )
        _debug.pipeline("warm_assets.website", website=website.id, links=len(links))
    return links
