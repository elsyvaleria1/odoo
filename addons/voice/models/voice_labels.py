import re

from lxml import etree

from odoo import api, models

MAX_OTHER_LANGS = 2
_GROUP_BY = re.compile(r"""['"]group_by['"]\s*:\s*\[?\s*['"]([\w.]+)""")
_SPOKEN_SEPARATOR = re.compile(r"\s*;\s*")


class VoiceLabels(models.AbstractModel):
    _name = "voice.labels"
    _description = "Voice: labels in the user's other languages"

    @api.model
    def _other_langs(self) -> list[str]:
        mine = self.env.lang or "en_US"
        installed = [code for code, _name in self.env["res.lang"].get_installed()]
        return [code for code in installed if code != mine][:MAX_OTHER_LANGS]

    @api.model
    def menu_labels(self, menu_ids: list[int]) -> dict[str, dict[int, str]]:
        menus = self.env["ir.ui.menu"].browse(menu_ids).exists()
        return {
            lang: {menu.id: menu.name for menu in menus.with_context(lang=lang)}
            for lang in self._other_langs()
        }

    @api.model
    def view_labels(self, res_model: str, views: list[list]) -> dict[str, dict]:
        requested = [(view_id or False, view_type) for view_id, view_type in views]
        labels = {}
        for lang in self._other_langs():
            result = self.env[res_model].with_context(lang=lang).get_views(requested)
            fields = result["models"].get(res_model, {}).get("fields", {})
            found: dict[str, dict] = {
                "filters": {},
                "date_filters": {},
                "group_bys": {},
                "search_fields": {},
                "form_fields": {},
                "buttons": {},
                "fields": {
                    name: field["string"]
                    for name, field in fields.items()
                    if field.get("string")
                },
            }
            for view_type, view in result["views"].items():
                arch = etree.fromstring(view["arch"])
                if view_type == "search":
                    self._read_search(arch, fields, found)
                elif view_type == "form":
                    self._read_form(arch, fields, found)
            labels[lang] = found
        return labels

    @api.model
    def _field_label(self, node, fields) -> str:
        name = node.get("name")
        return node.get("string") or fields.get(name, {}).get("string") or ""

    @api.model
    def _read_search(self, arch, fields, found) -> None:
        for node in arch.iter("filter"):
            label = node.get("string")
            if not label:
                continue
            grouped = _GROUP_BY.search(node.get("context") or "")
            if grouped:
                found["group_bys"][grouped.group(1).split(":")[0]] = label
            elif node.get("date"):
                found["date_filters"][node.get("name")] = label
            elif node.get("name"):
                found["filters"][node.get("name")] = label
        for node in arch.iter("field"):
            label = self._field_label(node, fields)
            if label:
                found["search_fields"][node.get("name")] = label

    @api.model
    def _read_form(self, arch, fields, found) -> None:
        for node in arch.iter("field"):
            label = self._field_label(node, fields)
            if label and node.get("name") not in found["form_fields"]:
                found["form_fields"][node.get("name")] = label
        for node in arch.iter("button"):
            if node.get("type") not in ("object", "action") or not node.get("name"):
                continue
            phrases = [node.get("string") or ""]
            phrases += _SPOKEN_SEPARATOR.split(node.get("spoken") or "")
            phrases = [phrase for phrase in phrases if phrase]
            if phrases:
                found["buttons"][node.get("name")] = phrases
