import binascii
import functools
import pprint
import textwrap
from base64 import b64decode
from collections import Counter, OrderedDict

from lxml import etree
from lxml.builder import E

from odoo import models
from odoo.fields import Domain
from odoo.tools import topological_sort

XML_FIELDS = [("ir.ui.view", "arch")]


class ModelDataGetter:
    def __init__(self, data=None):
        self.reset_cache(data)

    def reset_cache(self, data=None):
        self._cache = data.grouped(lambda d: (d.model, d.res_id)) if data else {}

    def __call__(self, record):
        key = (record._name, record.id)
        if key not in self._cache or not self._cache[key]:
            for data in (
                record.env["ir.model.data"]
                .sudo()
                .search(
                    [
                        ("model", "=", record._name),
                        ("res_id", "in", list(record._prefetch_ids)),
                    ],
                    order="id",
                )
            ):
                key_data = (data.model, data.res_id)
                if key_data not in self._cache:
                    self._cache[key_data] = data

        if key not in self._cache:
            raise MissingXMLID(record)
        return self._cache[key]


class MissingXMLID(Exception):
    def __init__(self, record):
        super().__init__("Missing XMLID: %s (%s)" % (record, record.display_name))


class StudioExportSerializer:
    def __init__(self, env, module, export_info):
        self.env = env
        self.module = module
        data, to_export, circular_dependencies = export_info
        self.data = data
        self.to_export = to_export
        self.circular_dependencies = circular_dependencies
        self.has_website = (
            env["ir.module.module"].search_count(
                [("state", "=", "installed"), ("name", "=", "website")]
            )
            == 1
        )
        self.utils = StudioExportUtils(env, module, data)
        self.filepaths = []
        self.demo_sale_orders = None
        self.website_themes = []

    def serialize(self):
        depends = set(self.module.mapped("dependencies_id.name"))
        self.utils.path_counter.clear()
        self.warnings = []

        if self.circular_dependencies:
            circ_lines = "\n".join(
                [
                    f"({'demo' if is_demo else 'data'}) {' -> '.join(dep)}"
                    for (is_demo, dep) in self.circular_dependencies
                ]
            )
            self.warnings.append(
                f"Found {len(self.circular_dependencies)} circular dependencies (you may have to change data loading order to avoid issues when importing):\n"
                f"{circ_lines}\n"
            )

        has_skipped_fields_warnings = False
        for model, records, fields, no_update, path_info in self.to_export:
            (files, new_deps, skipped_relations) = self._serialize_model(
                model=model,
                records=records,
                fields=fields,
                no_update=no_update,
                path_info=path_info,
            )
            if files is not None:
                depends.update(new_deps)
                yield from files

            if skipped_relations:
                if not has_skipped_fields_warnings:
                    has_skipped_fields_warnings = True
                    self.warnings.append(
                        "The following relational data haven't been exported because they either refer\n"
                        "to a model that Studio doesn't export, or have no XML id:\n"
                    )
                for xmlid, field, value in skipped_relations:
                    self.warnings.append(
                        textwrap.dedent(f"""
                        Record: {xmlid},
                        Model: {field.model_name},
                        Field: {field.name},
                        Type: {field.type},
                        Value: {value} ({
                            ", ".join(repr(v.display_name) for v in value)
                            if isinstance(value, models.BaseModel)
                            else f"DB id: {value}"
                        })
                    """)
                    )

        yield from self._get_last_files(depends)

    def _serialize_model(self, model, records, fields, no_update, path_info):
        records_to_export, binary_files, new_deps = (
            self.utils.prepare_records_to_export(model, records, fields)
        )
        default_get_data = records_to_export[0].browse().default_get(fields)

        nodes = self._get_pre_nodes(model, records_to_export)
        skipped_fields = []
        for record in records_to_export:
            record_node, skipped_relations = self._serialize_record(
                record, fields, default_get_data
            )
            if record_node is not None:
                nodes.append(record_node)
            skipped_fields.extend(skipped_relations)
        nodes.extend(self._get_post_nodes(model, records))

        if not nodes:
            return None, {}, skipped_fields

        root = E.odoo(*nodes, noupdate="1") if no_update else E.odoo(*nodes)
        content = etree.tostring(
            root, pretty_print=True, encoding="UTF-8", xml_declaration=True
        )
        (group, suffix) = path_info
        filepath = self.utils.get_next_file_path(group, model, suffix)
        self.filepaths.append(filepath)
        self._update_pending_files(group, model, new_deps)
        return [(filepath, content)] + binary_files, new_deps, skipped_fields

    def _serialize_record(self, record, fields, default_get_data):
        record_data = self.utils.get_model_data(record)
        exportid = self.utils.get_xmlid(record)
        skipped_relations = []

        context = {}
        if record_data.studio:
            context.update({"studio": True})
        if record._name in ("product.template", "product.template.attribute.line"):
            context.update({"create_product_product": False})
        if record._name == "worksheet.template":
            context.update({"worksheet_no_generation": True})
        if exportid.startswith("website.configurator_"):
            exportid = exportid.replace("website.configurator_", "configurator_")

        node_attrs = {"id": exportid, "model": record._name}
        if context:
            node_attrs["context"] = str(context)
        if self.module.name != self.utils.get_module_name(record):
            node_attrs["forcecreate"] = "1"

        fields_nodes = []
        for name in fields:
            field = record._fields[name]
            field_element = None
            try:
                field_element = self._serialize_field(record, field, default_get_data)
            except MissingXMLID:
                skipped_relations.append((exportid, field, record[name]))

            if field_element is not None:
                fields_nodes.append(field_element)

        return E.record(
            *fields_nodes, **node_attrs
        ) if fields_nodes else None, skipped_relations

    def _serialize_field(self, record, field, default_get_data):
        default_value = default_get_data.get(field.name)
        value = record[field.name]
        if (not value and not default_value) or field.convert_to_cache(
            value, record
        ) == field.convert_to_cache(default_value, record):
            return None

        if (
            self.has_website
            and field.name == "key"
            and record._name == "ir.ui.view"
            and record.website_id
        ):
            value = f"studio_customization.{value}"

        if field.type in ("boolean", "properties_definition", "properties"):
            return E.field(name=field.name, eval=str(value))
        elif field.type == "many2one_reference":
            reference_model = record[field.model_field]
            reference_value = (
                reference_model and record.env[reference_model].browse(value)
            ) or False
            xmlid = self.utils.get_xmlid(reference_value)
            if reference_value:
                return E.field(name=field.name, ref=xmlid)
            else:
                return E.field(name=field.name, eval="False")
        elif field.type in ("many2many", "one2many"):
            xmlids = [self.utils.get_xmlid(v) for v in value]
            return E.field(
                name=field.name,
                eval="[(6, 0, [%s])]"
                % ", ".join("ref('%s')" % xmlid for xmlid in xmlids),
            )

        if not value:
            return E.field(name=field.name, eval="False")
        elif (field.model_name, field.name) in XML_FIELDS:
            parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False)
            return E.field(etree.XML(value, parser), name=field.name, type="xml")
        elif field.type == "binary":
            return E.field(
                name=field.name,
                type="base64",
                file="studio_customization/"
                + self.utils.get_binary_field_file_name(field, record),
            )
        elif field.type == "datetime":
            return E.field(field.to_string(value), name=field.name)
        elif field.type in ("many2one", "reference"):
            xmlid = self.utils.get_xmlid(value)
            return E.field(name=field.name, ref=xmlid)
        elif field.type in ("html", "text"):
            node = E.field(name=field.name)
            node.text = etree.CDATA(str(value))
            return node
        else:
            return E.field(str(value), name=field.name)

    def _update_pending_files(self, group, model, depends):
        if model == "sale.order" and group == "demo":
            demo_so = self.data.filtered_domain(
                [("model", "=", model), ("is_demo_data", "=", True)]
            )
            demo_so = self.env["sale.order"].browse(demo_so.mapped("res_id"))
            self.demo_sale_orders = demo_so.filtered_domain(
                [("state", "not in", ("cancel", "draft"))]
            )

        themes = [d for d in depends if d and d.startswith("theme_")]
        self.website_themes.extend(themes)

    def _get_last_files(self, depends):
        if self.demo_sale_orders:
            filepath = self.utils.get_next_file_path("demo", "sale.order", "_confirm")
            self.filepaths.append(filepath)
            refs = ",".join(
                "ref('%s')" % self.utils.get_xmlid(so) for so in self.demo_sale_orders
            )
            nodes = [
                etree.Comment("Update sale order stages"),
                E.function(
                    model="sale.order",
                    name="action_confirm",
                    eval="[[%s]]" % refs,
                ),
            ]
            root = E.odoo(*nodes)
            content = etree.tostring(
                root, pretty_print=True, encoding="UTF-8", xml_declaration=True
            )
            yield (filepath, content)

        if self.website_themes:
            filepath = self.utils.get_next_file_path("demo", "website_theme", "_apply")
            fns = [
                E.function(
                    E.value(
                        model="ir.module.module",
                        eval=f"obj().env['ir.module.module'].search([('name', '=', '{theme}')]).ids",
                    ),
                    E.value(
                        model="ir.module.module",
                        eval="obj().env.ref('website.default_website')",
                    ),
                    model="ir.module.module",
                    name="_theme_load",
                    context="{'apply_new_theme': True}",
                )
                for theme in self.website_themes
            ]
            comments = [
                etree.Comment(etree.tostring(fn, pretty_print=True, encoding="UTF-8"))
                for fn in fns[1:]
            ]
            nodes = [fns[0], *comments]
            root = E.odoo(*nodes)
            content = etree.tostring(
                root, pretty_print=True, encoding="UTF-8", xml_declaration=True
            )
            try:
                index = self.filepaths.index("demo/ir_ui_view.xml")
                self.filepaths.insert(index, filepath)
            except ValueError:
                self.filepaths.append(filepath)
            yield (filepath, content)

        if self.warnings:
            yield ("warnings.txt", "".join(self.warnings))

        manifest = self.utils.create_manifest(depends, self.filepaths)
        yield ("__manifest__.py", manifest)
        yield ("__init__.py", b"")

    def _get_pre_nodes(self, model, records):
        nodes = []
        if model == "website.menu" and any(
            r["url"] == "/default-main-menu" for r in records
        ):
            nodes.append(
                E.function(
                    E.value(
                        model="website.menu",
                        eval="obj().search([('website_id', '=', ref('website.default_website')), ('url', '=', '/default-main-menu')]).id",
                    ),
                    model="website.menu",
                    name="unlink",
                )
            )
        return nodes

    def _get_post_nodes(self, model, records):
        nodes = []
        if model == "ir.ui.view" and self.has_website:
            website_views = filter(
                lambda r: (
                    r["website_id"]
                    and r["key"].startswith("website.")
                    and r["create_uid"].id == 1
                ),
                records,
            )
            for view in website_views:
                exportid = self.utils.get_xmlid(view)
                nodes.append(
                    E.function(
                        E.value(
                            model="ir.ui.view",
                            eval="obj().env['website'].with_context(website_id=obj().env.ref('website.default_website').id).viewref('%s').id"
                            % view["key"],
                        ),
                        E.value(
                            model="ir.ui.view",
                            eval="{'arch': obj().env.ref('%s').arch}" % exportid,
                        ),
                        model="ir.ui.view",
                        name="write",
                    )
                )
        return nodes


class StudioExportUtils:
    def __init__(self, env, module, data):
        self.env = env
        self.module = module
        self.get_model_data = ModelDataGetter(data)
        self.path_counter = Counter()

    def clean_dependencies(self, input_deps):
        input_deps -= {False, self.module.name, "__export__"}
        all_deps = self.env["ir.module.module.dependency"].all_dependencies(input_deps)
        deep_deps = {}

        @functools.cache
        def get_deep_depends(module_name):
            deep_deps[module_name] = set()

            for dep in all_deps.get(module_name, []):
                deep_deps[module_name] |= {dep, *get_deep_depends(dep)}

            return deep_deps[module_name]

        for name in all_deps:
            get_deep_depends(name)

        output_deps = set(input_deps)
        for mod, deps in deep_deps.items():
            if mod in input_deps:
                to_remove = deps - {mod}
                output_deps -= to_remove

        return sorted(output_deps)

    def create_manifest(self, depends, filepaths):
        depends = self.clean_dependencies(depends)
        return pprint.pformat(
            {
                "name": self.module.display_name,
                "version": self.module.manifest_version,
                "category": "Studio",
                "description": self.module.description,
                "author": self.module.author,
                "depends": depends,
                "data": [f for f in filepaths if f.startswith("data/")],
                "demo": [f for f in filepaths if f.startswith("demo/")],
                "license": self.module.license,
            },
            sort_dicts=False,
        ).encode()

    def get_binary_field_file_name(self, field, record):
        binary_filename = "%s-%s" % (record.id, field.name)
        if field.model_name == "ir.attachment":
            binary_filename = "%s-%s" % (
                record.id,
                record.name.replace("/", "_").replace(" ", ""),
            )
        return (
            f"static/src/binary/{field.model_name.replace('.', '_')}/{binary_filename}"
        )

    def get_module_name(self, record):
        xmlid = self.get_xmlid(record)
        if xmlid.startswith("base.module_"):
            return xmlid[12:]
        if "." not in xmlid:
            return "studio_customization"
        return xmlid.split(".", 1)[0]

    def get_next_file_path(self, group, model, suffix):
        key = (group, model, suffix)
        path_count = self.path_counter[key]
        self.path_counter[key] += 1
        return "%s/%s%s%s.xml" % (
            group,
            model.replace(".", "_"),
            "" if not path_count else f"_{path_count}",
            suffix,
        )

    def get_relations(self, record, field):
        if not record[field.name]:
            return None

        if field.type in ("many2one", "one2many", "many2many", "reference"):
            return record[field.name]

        if field.type == "many2one_reference":
            related_model = record[field.model_field]
            if not related_model:
                return None
            return record.env[related_model].browse(record[field.name])

        if field.model_name == "ir.model.fields":
            if field.name in ("depends", "related"):
                dep_fields = set()
                for dep_names in record[field.name].split(","):
                    dep_model = record.env[record.model]
                    for dep_name in dep_names.strip().split("."):
                        dep_field = dep_model._fields[dep_name]
                        if dep_name not in models.MAGIC_COLUMNS:
                            dep_fields.add(dep_field)
                        if dep_field.relational:
                            dep_model = record.env[dep_field.comodel_name]
                if dep_fields:
                    return record.search(
                        Domain.OR(
                            [
                                "&",
                                ("model", "=", dep_field.model_name),
                                ("name", "=", dep_field.name),
                            ]
                            for dep_field in dep_fields
                        )
                    )
            elif field.name == "relation_field":
                return record.search(
                    [
                        ("model", "=", record.relation),
                        ("name", "=", record.relation_field),
                    ]
                )

        if field.model_name == "ir.actions.act_window" and field.name in (
            "res_model",
            "binding_model",
        ):
            return record.env["ir.model"]._get(record[field.name])
        if field.model_name == "ir.actions.report" and field.name == "model":
            return record.env["ir.model"]._get(record.model)
        return None

    def get_xmlid(self, record):
        return self.get_model_data(record)._xmlid_for_export()

    def prepare_records_to_export(self, model, records, fields_to_export):
        binary_files = []
        fields = [records._fields[name] for name in fields_to_export]
        record_deps = OrderedDict.fromkeys(records, records.browse())
        module_deps = set()
        for record in records:
            module_name = self.get_module_name(record)

            module_deps.add(record._original_module)
            module_deps.add(record._module)
            module_deps.add(module_name)

            for field in fields:
                module_deps.update(field._modules)
                if field.type == "binary" and record[field.name]:
                    value = record[field.name]
                    try:
                        binary_data = b64decode(value)
                    except binascii.Error, TypeError:
                        binary_data = (
                            value.decode("utf-8")
                            if isinstance(value, bytes)
                            else str(value)
                        )
                    binary_files.append(
                        (self.get_binary_field_file_name(field, record), binary_data)
                    )

                rel_records = self.get_relations(record, field)
                if not rel_records:
                    continue

                for rel_record in rel_records:
                    try:
                        module_deps.add(self.get_module_name(rel_record))
                    except MissingXMLID:
                        continue

                if rel_records._name == model:
                    record_deps[record] |= rel_records

            if record._name == "ir.model.fields" and record.ttype == "monetary":
                rel_record = record._get(record.model, "currency_id") or record._get(
                    record.model, "x_currency_id"
                )
                if rel_record:
                    module_deps.add(self.get_module_name(rel_record))
                    record_deps[record] |= rel_record

        records = topological_sort(record_deps)

        return records, binary_files, module_deps
