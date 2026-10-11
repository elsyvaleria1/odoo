import re
from copy import deepcopy
from typing import TYPE_CHECKING

from lxml import etree

from odoo.libs.debug_log import DebugLog
from odoo.libs.hashing import cache_hash
from odoo.libs.lru import LRU
from odoo.tools import OrderedSet, config
from odoo.tools.assets.esm_graph import reachable_module_sources
from odoo.tools.assets.owl_precompile import (
    InlineSource,
    compiler_fingerprint,
    web_static_path,
)
from odoo.tools.json import scriptsafe as json

if TYPE_CHECKING:
    from .bundle import AssetsBundle
    from .common import XMLBlock
from .common import XMLAssetError

_debug = DebugLog(__name__)

_INLINE_TEMPLATE_RE = re.compile(r"\bxml\s*`")

_RENDERED_XML_CACHE: LRU[tuple[str, ...], str] = LRU(64)


class XmlTemplatePipeline:
    _TEMPLATE_MODULE = "@web/core/templates"
    _TEMPLATE_REGISTRARS = (
        "checkPrimaryTemplateParents, registerTemplate, registerTemplateBundle, "
        "registerTemplateExtension"
    )

    def __init__(self, bundle: AssetsBundle) -> None:
        self._bundle = bundle
        self._rendered_bundle: str | None = None
        self._inline_sources: list[InlineSource] | None = None
        self._page_registrations: list[str] | None = None

    def xml(self) -> list[XMLBlock]:
        bundle = self._bundle
        blocks = []
        block = None
        for asset in bundle.templates:
            for template_tree in asset.template_elements:
                template_name = template_tree.get("t-name")
                inherit_from = template_tree.get("t-inherit")
                inherit_mode = None
                if inherit_from:
                    inherit_mode = template_tree.get("t-inherit-mode", "primary")
                    if inherit_mode not in {"primary", "extension"}:
                        addon = asset.url.split("/")[1] if asset.url else asset.name
                        _debug.logic(
                            "xml_inherit_mode_invalid",
                            bundle=bundle.name,
                            template=template_name,
                            mode=inherit_mode,
                        )
                        raise asset._prepare_asset_error(
                            bundle.env._(
                                'Invalid inherit mode. Module "%(module)s" and template name "%(template_name)s"',
                                module=addon,
                                template_name=template_name,
                            )
                        )
                if inherit_mode == "extension":
                    if block is None or block["type"] != "extensions":
                        block = {
                            "type": "extensions",
                            "extensions": {},
                        }
                        blocks.append(block)
                    block["extensions"].setdefault(inherit_from, []).append(
                        (template_tree, asset.url)
                    )
                elif template_name:
                    if block is None or block["type"] != "templates":
                        block = {"type": "templates", "templates": []}
                        blocks.append(block)
                    block["templates"].append((template_tree, asset.url, inherit_from))
                else:
                    _debug.logic(
                        "xml_template_name_missing", bundle=bundle.name, url=asset.url
                    )
                    raise asset._prepare_asset_error(
                        bundle.env._("Template name is missing.")
                    )
        _debug.pipeline(
            "xml_blocks",
            bundle=bundle.name,
            assets=len(bundle.templates),
            blocks=len(blocks),
            extension_blocks=sum(1 for b in blocks if b["type"] == "extensions"),
        )
        return blocks

    def generate_xml_bundle(self) -> str:
        if self._rendered_bundle is None:
            key = tuple(asset.unique_descriptor for asset in self._bundle.templates)
            rendered = _RENDERED_XML_CACHE.get(key)
            if rendered is None:
                with _debug.perf("xml_render", bundle=self._bundle.name) as span:
                    rendered, failed = self._render_xml_bundle()
                    span.set(bytes=len(rendered))
                if not failed:
                    _RENDERED_XML_CACHE[key] = rendered
            self._rendered_bundle = rendered
        return self._rendered_bundle

    def _render_xml_bundle(self) -> tuple[str, bool]:
        content = []
        blocks = []
        failed = False
        try:
            blocks = self.xml()
        except XMLAssetError as e:
            content.append(f"throw new Error({json.dumps(str(e))});")
            failed = True
            _debug.logic("xml_bundle_error_inlined", bundle=self._bundle.name)

        def get_template(element: etree._Element) -> str:
            element = deepcopy(element)
            element.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            string = etree.tostring(element, encoding="unicode")
            string = (
                string.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
            )
            return re.sub(r"(?i)</script", r"<\\/script", string)

        names = OrderedSet()
        primary_parents = OrderedSet()
        extension_parents = OrderedSet()
        for block in blocks:
            if block["type"] == "templates":
                for element, url, inherit_from in block["templates"]:
                    if inherit_from:
                        primary_parents.add(inherit_from)
                    name = element.get("t-name")
                    names.add(name)
                    template = get_template(element)
                    content.append(
                        f"registerTemplate({json.dumps(name)}, {json.dumps(url)}, `{template}`);"
                    )
            else:
                for inherit_from, elements in block["extensions"].items():
                    extension_parents.add(inherit_from)
                    for element, url in elements:
                        template = get_template(element)
                        content.append(
                            f"registerTemplateExtension({json.dumps(inherit_from)}, {json.dumps(url)}, `{template}`);"
                        )

        missing_names_for_primary = primary_parents - names
        _debug.pipeline(
            "xml_bundle",
            bundle=self._bundle.name,
            blocks=len(blocks),
            templates=len(names),
            primary_parents=len(primary_parents),
            extension_parents=len(extension_parents),
            missing_primary=len(missing_names_for_primary),
            missing_extension=len(extension_parents - names),
        )
        if missing_names_for_primary:
            content.append(
                f"checkPrimaryTemplateParents({json.dumps(list(missing_names_for_primary))});"
            )
        missing_names_for_extension = extension_parents - names
        if missing_names_for_extension:
            missing_msg = "Missing (extension) parent templates: " + ", ".join(
                missing_names_for_extension
            )
            content.append(f"console.error({json.dumps(missing_msg)});")

        return "\n".join(content), failed

    def precompile_checksum(self) -> str | None:
        bundle = self._bundle
        if bundle.is_debug_assets or "xml" in config["dev_mode"]:
            return None
        templates = self.generate_xml_bundle()
        sources = self.inline_template_sources()
        if not templates and not sources:
            return None
        web_static = web_static_path()
        if web_static is None:
            return None
        fingerprint = compiler_fingerprint(web_static)
        inline = "".join(f"\n{source.url}\n{source.content}" for source in sources)
        pages = "".join(f"{page}\n" for page in self.page_registrations())
        return cache_hash(f"{fingerprint}\n{pages}{templates}{inline}".encode())[:16]

    def page_registrations(self) -> list[str]:
        if self._page_registrations is None:
            bundle = self._bundle
            IrQweb = bundle.env["ir.qweb"]
            params = bundle.assets_params or None
            self._page_registrations = [
                IrQweb._get_asset_bundle(
                    parent, css=False, js=True, assets_params=params
                )._xml.generate_xml_bundle()
                for parent in IrQweb._get_runtime_group_parents(
                    bundle.name, assets_params=params
                )
            ]
        return self._page_registrations

    def inline_template_sources(self) -> list[InlineSource]:
        if self._inline_sources is None:
            bundle = self._bundle
            sources = [
                InlineSource(asset.url or asset.name, asset.content)
                for asset in (*bundle.javascripts, *bundle.native_modules)
            ]
            members = [module.module_path for module in bundle.native_modules]
            if members:
                reachable = reachable_module_sources(
                    members,
                    members,
                    bundle.env["ir.qweb"]._external_libs(),
                    bundle.name,
                    dynamic=True,
                    modules=bundle.native_modules,
                )
                sources += (
                    InlineSource(url, content)
                    for spec, (url, content) in reachable.items()
                    if spec not in members
                )
            self._inline_sources = [
                source
                for source in sources
                if _INLINE_TEMPLATE_RE.search(source.content)
            ]
            _debug.logic(
                "inline_template_sources",
                bundle=bundle.name,
                sources=len(self._inline_sources),
            )
        return self._inline_sources

    def _announced(self, templates: str) -> str:
        checksum = self.precompile_checksum()
        if checksum is None:
            return templates
        args = [json.dumps(self._bundle.name), json.dumps(checksum)]
        params = self._bundle.js_rebuild_params
        if params or templates:
            args.append(json.dumps(params or {}))
        if templates:
            args.append(f"() => {{\n{templates}\n}}")
        return f"registerTemplateBundle({', '.join(args)});\n"

    def _registrar_binding(self, indent: str = "") -> str:
        return (
            f"{indent}const {{ {self._TEMPLATE_REGISTRARS} }} = "
            f'odoo.loader.modules.get("{self._TEMPLATE_MODULE}");\n'
        )

    def generate_esm_template_bundle(self, use_import=True) -> str:
        bundle = self._bundle
        templates = self.generate_xml_bundle() if bundle.templates else ""
        announced = self._announced(templates)
        if not announced:
            _debug.logic("esm_template_bundle_skipped", bundle=bundle.name)
            return ""
        _debug.logic(
            "esm_template_bundle",
            bundle=bundle.name,
            use_import=use_import,
            bytes=len(templates),
        )
        if use_import:
            header = (
                f"import {{ {self._TEMPLATE_REGISTRARS} }} "
                f'from "{self._TEMPLATE_MODULE}";\n'
            )
        else:
            header = self._registrar_binding()
        return f"{header}/* {bundle.name} */\n{announced}"

    def legacy_template_iife(self) -> str:
        templates = self.generate_xml_bundle()
        _debug.pipeline(
            "legacy_template_iife", bundle=self._bundle.name, bytes=len(templates)
        )
        return (
            "\n\n"
            "/*******************************************\n"
            "*  Templates                               *\n"
            "*******************************************/\n\n"
            "(function() {\n"
            '    "use strict";\n'
            f"{self._registrar_binding(indent='    ')}"
            f"    /* {self._bundle.name} */\n"
            f"{self._announced(templates)}\n"
            "})();\n"
        )
