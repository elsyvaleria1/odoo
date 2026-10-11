import pathlib
from configparser import ConfigParser
from os import pardir
from urllib.parse import quote_plus

import odoo
from odoo import models, tools


class TransifexTranslation(models.AbstractModel):
    _name = "transifex.translation"
    _description = "Transifex Translation"

    @tools.ormcache()
    def _get_transifex_projects(self):
        tx_config_file = ConfigParser()
        projects = {}
        for addon_path in odoo.addons.__path__:
            for tx_path in (
                pathlib.Path(addon_path, ".tx", "config"),
                pathlib.Path(addon_path, pardir, ".tx", "config"),
            ):
                if tx_path.is_file():
                    tx_config_file.read(tx_path)
                    for sec in tx_config_file.sections()[1:]:
                        if len(sec.split(":")) != 6:
                            tx_project, tx_mod = sec.split(".")
                        else:
                            _, _, _, tx_project, _, tx_mod = sec.split(":")
                        projects[tx_mod] = tx_project
        return projects

    def _update_transifex_url(self, translations) -> None:

        base_url = self.env.registry.settings.get(
            self.env, "transifex.project_url", False
        )
        if not base_url:
            return
        base_url = base_url.rstrip("/")

        res_langs = self.env["res.lang"].search([])
        lang_to_iso = {l.code: l.iso_code for l in res_langs}
        if not lang_to_iso:
            return

        projects = self._get_transifex_projects()
        if not projects:
            return

        for translation in translations:
            if not translation["source"] or translation["lang"] == "en_US":
                continue

            lang_iso = lang_to_iso.get(translation["lang"])
            if not lang_iso:
                continue

            project = projects.get(translation["module"])
            if not project:
                continue

            source = quote_plus(
                translation["source"][:50].replace("\n", "").replace("'", "\\'")
            )
            source = f"'{source}'" if "+" in source else source
            translation["transifex_url"] = (
                f"{base_url}/{project}/translate/#{lang_iso}/{translation['module']}/42?q=text%3A{source}"
            )
