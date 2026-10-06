from collections import defaultdict
from typing import Self

from odoo import api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, Query
from odoo.tools.translate import html_translate

from odoo.addons.resource.fields import ResourceIdentifier
from odoo.addons.resource.models.utils import MANAGER_ROLE, OPERATOR_ROLE

_debug = DebugLog(__name__)

CUSTODY_SILENT = "custody_silent"

SKIP_IDENTITY_CHECK = "skip_asset_identity_check"
# a thing is acquired before it is available, unlike a resource of its own
ASSET_INITIAL_STATE = "draft"
# the kind model already creating these resources as its parents
KIND_MODEL_CREATING = "resource_kind_model_creating"


class ResourceResource(models.Model):
    _name = "resource.resource"
    _inherit = ["resource.resource", "mixin.image"]
    # a thing's vendor is one of its company's
    _check_company_auto = True

    # what a thing is and where it came from, on the resource it is
    kind_id = fields.Many2one(
        comodel_name="resource.kind",
        index="btree_not_null",
        ondelete="restrict",
    )
    kind_code = fields.Char(related="kind_id.code")
    properties = fields.Properties(
        definition="kind_id.properties_definition",
        copy=True,
    )
    description = fields.Html(translate=html_translate)
    model = fields.Char(string="Model Name")
    model_year = fields.Integer(
        help="The commercial model year, which may differ from the year it was built.",
    )
    brand_new = fields.Boolean(default=True)
    vendor_id = fields.Many2one(
        comodel_name="res.partner",
        index="btree_not_null",
        check_company=True,
        tracking=True,
    )
    vendor_ref = fields.Char(string="Vendor Reference")
    warranty_date = fields.Date(string="Warranty Expiration Date")
    address_id = fields.Many2one(
        comodel_name="res.partner",
        string="Location",
        help="Where the resource normally is, when no inventory location tracks it.",
    )
    # a thing's odometer: the newest reading of its odometer meter
    odometer = fields.Float(
        compute="_compute_odometer",
        inverse="_inverse_odometer",
        store=True,
        readonly=False,
    )
    odometer_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        tracking=True,
        help="Unit of measurement for the odometer readings",
    )
    odometer_uom_name = fields.Char(
        related="odometer_uom_id.display_name",
        string="Odometer Unit",
    )
    odometer_meter_id = fields.Many2one(
        comodel_name="resource.meter",
        compute="_compute_odometer_meter_id",
        store=True,
    )

    # read and searched through the identifier rows; a kind model that keeps
    # one as a column of its own declares it again
    license_plate = ResourceIdentifier(
        identifier_code="plate",
        store=False,
        help="License plate number of the asset (eg plate number for a car)",
    )
    vin_sn = ResourceIdentifier(
        identifier_code="vin",
        string="Serial Number / VIN",
        store=False,
        help="Unique number written on an asset's chassis (VIN/SN number).",
    )
    engine_sn = ResourceIdentifier(
        identifier_code="engine",
        string="Engine Serial Number",
        store=False,
        help="Unique number written on the asset's engine.",
    )
    serial_number = ResourceIdentifier(identifier_code="serial", store=False)
    imei = ResourceIdentifier(
        identifier_code="imei",
        string="IMEI",
        store=False,
        help="International Mobile Equipment Identity of a cellular-capable asset.",
    )
    inventory_tag = ResourceIdentifier(identifier_code="inventory", store=False)
    cadastral_id = ResourceIdentifier(
        identifier_code="cadastral",
        string="Cadastral ID",
        store=False,
        help="Government-assigned parcel identifier for real estate assets.",
    )
    missing_identifier_type_ids = fields.Many2many(
        comodel_name="resource.identifier.type",
        compute="_compute_missing_identifier_type_ids",
        search="_search_missing_identifier_type_ids",
    )
    operator_history_count = fields.Integer(compute="_compute_operator_history_count")
    parent_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Part Of",
        compute="_compute_parent_id",
        inverse="_inverse_parent_id",
        search="_search_parent_id",
        compute_sudo=False,
        copy=False,
        readonly=False,
        value_sql="_parent_id_sql",
        help="Current physical parent from the resource membership timeline.",
    )
    child_ids = fields.One2many(
        comodel_name="resource.resource",
        inverse_name="parent_id",
        string="Components",
    )

    def _track_prepare(self, fields_iter):
        # a thing's history is its chatter's; a person's or an intangible's
        # resource keeps none
        return super(ResourceResource, self.filtered("kind_id"))._track_prepare(
            fields_iter
        )

    def get_formview_action(self, access_uid=None):
        if len(self) == 1:
            model_name = self._get_kind_models()[self.id]
            if model_name != self._name:
                return (
                    self.env[model_name]
                    .browse(self.id)
                    .get_formview_action(access_uid=access_uid)
                )
        return super().get_formview_action(access_uid=access_uid)

    def get_formview_id(self, access_uid=None):
        if len(self) == 1 and self.kind_id:
            return self.env.ref("resource_asset.resource_asset_view_form").id
        return super().get_formview_id(access_uid=access_uid)

    @api.depends("image_128")
    def _compute_avatar_128(self) -> None:
        super()._compute_avatar_128()
        for resource in self:
            if not resource.avatar_128:
                resource.avatar_128 = resource.image_128

    @api.constrains("type", "kind_id")
    def _check_a_thing_is_material(self) -> None:
        if self.filtered(
            lambda resource: resource.kind_id and resource.type != "material"
        ):
            raise ValidationError(
                self.env._("A resource of a kind is a thing, not a person.")
            )

    # odometer

    @api.depends("meter_ids.kind")
    def _compute_odometer_meter_id(self) -> None:
        for resource in self:
            resource.odometer_meter_id = resource.meter_ids.filtered(
                lambda m: m.kind == "odometer"
            )[:1]

    @api.depends("odometer_meter_id.last_reading_id.value")
    def _compute_odometer(self) -> None:
        for resource in self:
            resource.odometer = resource.odometer_meter_id.value

    def _inverse_odometer(self) -> None:
        for resource in self:
            meter = resource.odometer_meter_id
            if not resource.odometer and not meter:
                continue
            if not meter:
                meter = resource._create_odometer_meter()
            if meter.value > resource.odometer:
                _debug.logic(
                    "odometer.refused", reason="below_last_reading", resource=resource
                )
                raise ValidationError(
                    self.env._(
                        "%(asset)s: the odometer cannot go below its last reading of %(value)s.",
                        asset=resource.display_name,
                        value=meter.value,
                    )
                )
            if meter.value != resource.odometer:
                meter.record(resource.odometer)

    def _create_odometer_meter(self):
        self.check_singleton()
        meter = self.env["resource.meter"].create(
            {
                "resource_id": self.id,
                "name": self.env._("Odometer"),
                "kind": "odometer",
                "uom_id": self.odometer_uom_id.id,
            }
        )
        self.invalidate_recordset(["odometer_meter_id"])
        return meter

    def _check_odometer_uom_is_not_reinterpreted(self, new_uom_id) -> None:
        """Every reading the meter holds is a number in the asset's unit, and
        nothing stores which unit it was taken in. Changing the unit therefore
        restates the whole history rather than converting it."""
        changing = self.filtered(
            lambda resource: resource.odometer_uom_id.id != new_uom_id
        )
        with_readings = changing.sudo().filtered(
            lambda resource: resource.odometer_meter_id.reading_ids
        )
        if with_readings:
            _debug.logic(
                "odometer_uom.refused", reason="readings_exist", resources=self
            )
            raise ValidationError(
                self.env._(
                    "%(assets)s already carry odometer readings in their current "
                    "unit. Changing it now would restate every one of them; "
                    "convert the readings deliberately instead.",
                    assets=", ".join(with_readings.mapped("display_name")),
                )
            )

    # identifiers

    @api.model
    def _get_identifier_field_names(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, field in self._fields.items()
            if isinstance(field, ResourceIdentifier)
        )

    def _check_required_identifiers(self) -> None:
        if self.env.context.get(SKIP_IDENTITY_CHECK):
            return
        enforced = self.filtered(lambda resource: resource.kind_id.enforce_identifiers)
        if not enforced:
            return
        enforced.invalidate_recordset(
            [
                "identifier_ids",
                "missing_identifier_type_ids",
                *self._get_identifier_field_names(),
            ]
        )
        for resource in enforced:
            missing = resource.missing_identifier_type_ids
            if missing:
                _debug.logic(
                    "asset.refused",
                    reason="missing_required_identifiers",
                    resource=resource,
                )
                raise ValidationError(
                    self.env._(
                        "%(asset)s is a %(kind)s, which requires %(types)s.",
                        asset=resource.name or self.env._("This asset"),
                        kind=resource.kind_id.display_name,
                        types=", ".join(missing.mapped("name")),
                    )
                )

    @api.depends("identifier_ids.type_id", "kind_id.identifier_type_ids")
    def _compute_missing_identifier_type_ids(self) -> None:
        for resource in self:
            resource.missing_identifier_type_ids = (
                resource.kind_id.identifier_type_ids - resource.identifier_ids.type_id
            )

    def _search_missing_identifier_type_ids(self, operator, value):
        if operator in ("any", "not any"):
            type_query = self.env["resource.identifier.type"]._search(value)
            domain = self._get_missing_identifier_domain(
                SQL("rel.type_id IN %s", type_query.subselect())
            )
        elif operator in ("in", "not in"):
            type_ids = [type_id for type_id in value if type_id]
            domain = Domain.FALSE
            if type_ids:
                domain |= self._get_missing_identifier_domain(
                    SQL("rel.type_id = ANY(%s)", type_ids)
                )
            if len(type_ids) < len(value):
                domain |= ~self._get_missing_identifier_domain()
        else:
            return NotImplemented
        return ~domain if operator.startswith("not") else domain

    @api.model
    def _get_missing_identifier_domain(self, type_condition=None):
        def to_sql(model, alias, query):
            return SQL(
                """
                EXISTS (
                    SELECT 1
                      FROM resource_asset_kind_identifier_type_rel rel
                     WHERE rel.kind_id = %(kind)s
                       AND %(types)s
                       AND NOT EXISTS (
                           SELECT 1
                             FROM resource_identifier identifier
                            WHERE identifier.resource_id = %(resource)s
                              AND identifier.type_id = rel.type_id
                       )
                )
                """,
                kind=SQL.identifier(alias, "kind_id"),
                resource=SQL.identifier(alias, "id"),
                types=type_condition or SQL("TRUE"),
            )

        return Domain.custom(to_sql=to_sql)

    # composition

    @api.depends(
        "membership_ids.parent_id",
        "membership_ids.relation_type",
        "membership_ids.active",
        "membership_ids.date_start",
        "membership_ids.date_end",
    )
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_parent_id(self):
        Relation = self.env["resource.relation"]
        relations = Relation.search(
            Relation._get_domain_live_relations() + [("member_id", "in", self.ids)]
        )
        things = (
            self.with_context(active_test=False)
            .search([("id", "in", relations.parent_id.ids), ("kind_id", "!=", False)])
            .ids
        )
        by_member = {
            relation.member_id.id: relation.parent_id.id
            for relation in relations
            if relation.parent_id.id in things
        }
        for resource in self:
            resource.parent_id = by_member.get(resource.id, False)

    def _parent_id_sql(self, field, alias, query=None):
        Relation = self.env["resource.relation"]
        relations = Relation._search(Relation._get_domain_live_relations())
        parents = self.with_context(active_test=False)._search(
            [("kind_id", "!=", False)]
        )
        return SQL(
            """(SELECT relation.parent_id FROM resource_relation relation
                 WHERE relation.member_id = %s AND relation.id IN %s
                   AND relation.parent_id IN %s)""",
            self._field_to_sql(alias, "id", query),
            relations.subselect(),
            parents.subselect(),
        )

    def _search_parent_id(self, operator, value):
        if operator in ("any", "not any"):
            value = self.with_context(active_test=False)._search(value)
            operator = "in" if operator == "any" else "not in"
        if operator not in ("in", "not in"):
            return NotImplemented
        values = list(value) if not isinstance(value, Query) else None
        parent_ids = value if values is None else [v for v in values if v]
        wants_none = values is not None and len(parent_ids) < len(values)

        def to_sql(model, alias, query):
            parent = model._parent_id_sql(model._fields["parent_id"], alias, query)
            if isinstance(parent_ids, Query):
                condition = SQL("%s IN %s", parent, parent_ids.subselect())
            else:
                condition = SQL("%s = ANY(%s)", parent, parent_ids)
            if wants_none:
                condition = SQL("(%s OR %s IS NULL)", condition, parent)
            return SQL("COALESCE(%s, FALSE)", condition)

        domain = Domain.custom(to_sql=to_sql)
        return ~domain if operator == "not in" else domain

    def _inverse_parent_id(self):
        for resource in self:
            resource._set_parent(resource.parent_id)

    def _set_parent(self, parent, operation="write"):
        self.check_singleton()
        self.check_access(operation)
        if parent:
            parent.check_access("write")
        if parent == self:
            raise ValidationError(self.env._("An asset cannot be a part of itself."))
        Relation = self.env["resource.relation"]
        # Only identities leave this integrity lookup. Authorization remains on
        # the resources themselves before the scoped membership mutation.
        old_parents = (
            Relation.sudo()
            .search(
                Relation._get_domain_live_relations() + [("member_id", "=", self.id)]
            )
            .parent_id
        )
        if not parent and old_parents and not old_parents.filtered("kind_id"):
            # Clearing an empty thing parent does not detach a resource that is
            # not a thing. That membership is edited through the relation.
            return
        self.browse(old_parents.ids).check_access("write")
        with self.env.cr.savepoint():
            Relation.sudo()._set_containment_parent(self.sudo(), parent.sudo())
        self.invalidate_recordset(["parent_id"])

    @api.ondelete(at_uninstall=False)
    def _unlink_except_membership_history(self):
        things = self.filtered("kind_id")
        if things and self.env["resource.relation"].sudo().with_context(
            active_test=False
        ).search_count(
            [
                "|",
                ("parent_id", "in", things.ids),
                ("member_id", "in", things.ids),
            ],
            limit=1,
        ):
            raise ValidationError(
                self.env._(
                    "Archive assets with resource membership history instead of deleting them."
                )
            )

    @api.model
    def _asset_projection_sql(self, resource_id):
        """`resource_id` where it names a thing, NULL otherwise."""
        things = self.with_context(active_test=False)._search(
            [("kind_id", "!=", False)]
        )
        return SQL(
            "(SELECT thing.id FROM resource_resource thing WHERE thing.id = %s AND thing.id IN %s)",
            resource_id,
            things.subselect(),
        )

    # kinds

    @api.model
    @tools.ormcache(cache="stable")
    def _get_kind_model_names(self) -> dict[str, str]:
        """The model that extends a resource of each kind, by kind code: a
        model sharing its resource's id that names the kind it extends."""
        return {
            model._resource_kind_code: name
            for name, model in self.env.registry.items()
            if getattr(model, "_resource_kind_code", None)
            and model._inherits_shared_id
            and model._inherits.get("resource.resource")
        }

    @api.model
    def _get_model_for_kind(self, kind) -> str:
        return self._get_kind_model_names().get(kind.code, self._name)

    def _get_kind_models(self) -> dict[int, str]:
        """The model each resource is extended by, by id: its kind's, where a
        row of it exists."""
        found = {}
        for model_name in set(self._get_kind_model_names().values()):
            extended = self.env[model_name].with_context(active_test=False)
            for record_id in extended.search([("id", "in", self.ids)]).ids:  # noqa: E8507  one query per kind model, two of them
                found[record_id] = model_name
        return {record_id: found.get(record_id, self._name) for record_id in self.ids}

    def _around_the_clock(self, vals):
        """The fully flexible schedule: an unscheduled kind is available around
        the clock, and a shared (company-less) thing of a scheduled kind cannot
        take one company's hours -- every reader would then see a company
        crossover."""
        if "calendar_id" in vals:
            return False
        kind = self.env["resource.kind"].browse(vals.get("kind_id"))
        shared = "company_id" in vals and not vals["company_id"]
        return not kind.scheduled or shared

    def _create_in_kind_models(self, vals_list) -> Self | None:
        Kind = self.env["resource.kind"]
        creating = self.env.context.get(KIND_MODEL_CREATING)
        by_model = defaultdict(list)
        for index, vals in enumerate(vals_list):
            model_name = self._get_model_for_kind(Kind.browse(vals.get("kind_id")))
            if model_name == creating:
                model_name = self._name
            by_model[model_name].append((index, vals))
        if set(by_model) <= {self._name}:
            return None
        _debug.pipeline(
            "resource_asset.create_dispatched",
            models={name: len(rows) for name, rows in by_model.items()},
        )
        created = {}
        for model_name, indexed in by_model.items():
            if model_name == self._name:
                records = self.create([vals for __, vals in indexed])
            else:
                records = self.env[model_name].create([vals for __, vals in indexed])
            for (index, __), record in zip(indexed, records, strict=True):
                created[index] = record.id
        return self.browse(created[index] for index in range(len(vals_list)))

    @api.model_create_multi
    def create(self, vals_list):
        dispatched = self._create_in_kind_models(vals_list)
        if dispatched is not None:
            return dispatched
        parent_values = [vals.pop("parent_id", None) for vals in vals_list]
        given = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            if not vals.get("kind_id"):
                continue
            # a kind names what a thing is
            vals["type"] = "material"
            vals.setdefault("state", ASSET_INITIAL_STATE)
            if self._around_the_clock(vals):
                vals["calendar_id"] = (
                    self.env["resource.calendar"]._get_fully_flexible_calendar().id
                )
        resources = super().create(vals_list)
        for resource, vals in zip(resources, given, strict=True):
            if resource.kind_id:
                resource._on_kind_changed(vals)
        for resource, parent_id in zip(resources, parent_values, strict=True):
            if parent_id:
                resource._set_parent(self.browse(parent_id), operation="create")
        return resources

    def write(self, vals):
        if vals.keys() - self._fields.keys():
            return self._write_in_kind_models(vals)
        if "kind_id" in vals:
            self._check_kind_keeps_its_model(vals["kind_id"])
        if "odometer_uom_id" in vals:
            self._check_odometer_uom_is_not_reinterpreted(vals["odometer_uom_id"])
        res = super().write(vals)
        things = self.filtered("kind_id")
        if "kind_id" in vals:
            things._on_kind_changed(vals)
        elif vals.keys() & {"identifier_ids", *self._get_identifier_field_names()}:
            things._check_required_identifiers()
        things._notify_kind_models(vals)
        return res

    def _write_in_kind_models(self, vals) -> bool:
        # what create dispatches to a kind's model, a write of the kind's own
        # fields reaches there too: the kind model delegates the resource's
        # fields back here
        by_model = defaultdict(list)
        for record_id, model_name in self._get_kind_models().items():
            by_model[model_name].append(record_id)
        unknown = sorted(vals.keys() - self._fields.keys())
        if self._name in by_model:
            _debug.logic(
                "write.refused",
                reason="field_of_no_kind",
                resources=self,
                fields=unknown,
            )
            raise ValueError(f"Invalid field {unknown[0]!r} in {self._name!r}")
        _debug.pipeline(
            "resource_asset.write_dispatched",
            models={name: len(ids) for name, ids in by_model.items()},
        )
        for model_name, ids in by_model.items():
            self.env[model_name].browse(ids).write(vals)
        return True

    def _notify_kind_models(self, vals) -> None:
        """What the model extending a thing's kind keeps in step with its
        resource hears every write of the resource."""
        by_model = defaultdict(list)
        for resource in self:
            model_name = self._get_model_for_kind(resource.kind_id)
            if model_name != self._name:
                by_model[model_name].append(resource.id)
        for model_name, ids in by_model.items():
            self.env[model_name].browse(ids)._on_resource_written(vals)

    def _on_kind_changed(self, vals) -> None:
        # the kind model creating these checks them once it holds its identifiers
        if not self.env.context.get(KIND_MODEL_CREATING):
            self._check_required_identifiers()

    def _check_kind_keeps_its_model(self, kind_id) -> None:
        kind = self.env["resource.kind"].browse(kind_id)
        target = self._get_model_for_kind(kind)
        for model_name in set(self._get_kind_models().values()):
            if model_name != target:
                _debug.logic(
                    "write.refused", reason="kind_changes_model", resources=self
                )
                raise ValidationError(
                    self.env._(
                        "An asset of kind %(kind)s is a %(model)s, and this "
                        "one is not. Retype it instead.",
                        kind=kind.display_name,
                        model=target,
                    )
                )

    def _retype(self, kind) -> Self:
        """Deliberately make these resources a kind of another model: the row
        of the model they leave is deleted, and a row of the model their kind
        names is added under the same id. A field only the left model declares
        does not travel."""
        target = self._get_model_for_kind(kind)
        by_source = defaultdict(list)
        for record_id, model_name in self._get_kind_models().items():
            if model_name != target:
                by_source[model_name].append(record_id)
        _debug.lifecycle(
            "retype",
            resources=self,
            target=target,
            moving={source: len(ids) for source, ids in by_source.items()},
        )
        if by_source:
            self.env.flush_all()
            for source, ids in by_source.items():
                if source != self._name:
                    self.env.cr.execute(
                        SQL(
                            "DELETE FROM %s WHERE id = ANY(%s)",
                            SQL.identifier(self.env[source]._table),
                            ids,
                        )
                    )
            self.env.invalidate_all()
            moving = [record_id for ids in by_source.values() for record_id in ids]
            if target != self._name:
                self.env[target].with_context(**{KIND_MODEL_CREATING: target}).create(
                    [{"resource_id": record_id} for record_id in moving]
                )
        self.with_context(active_test=False).write({"kind_id": kind.id})
        return self.browse(self.ids)

    # custody

    def _compute_operator_history_count(self) -> None:
        counts = dict(
            self.env["resource.assignment"]._read_group(
                [
                    ("resource_id", "in", self.ids),
                    ("custody_role", "=", OPERATOR_ROLE),
                ],
                ["resource_id"],
                ["__count"],
            )
        )
        for resource in self:
            resource.operator_history_count = counts.get(resource, 0)

    def _on_custody_changed(self, role, changes, planned=False):
        super()._on_custody_changed(role, changes, planned=planned)
        for resource in self.filtered("kind_id"):
            before, after = changes[resource.id]
            resource._post_custody_message(role, before, after, planned=planned)

    def _get_custody_message(self, role, before, after, planned=False) -> str:
        names = {
            "before": before.sudo().name or "—",
            "after": after.sudo().name or "—",
        }
        if planned:
            return self.env._("Scheduled operator: %(before)s → %(after)s", **names)
        if role == MANAGER_ROLE:
            return self.env._("Manager: %(before)s → %(after)s", **names)
        return self.env._("Operator: %(before)s → %(after)s", **names)

    def _post_custody_message(self, role, before, after, planned=False) -> None:
        self.check_singleton()
        if before == after or self.env.context.get(CUSTODY_SILENT):
            return
        xml_id = (
            "resource_asset.mt_asset_future_operator_scheduled"
            if planned
            else "resource_asset.mt_asset_operator_updated"
        )
        subtype = self.env.ref(xml_id, raise_if_not_found=False)
        self.sudo().message_post(
            body=self._get_custody_message(role, before, after, planned=planned),
            subtype_id=subtype.id if subtype else None,
        )

    def _get_assets_released_by_operator_change(self):
        return self.search(
            [
                ("kind_id", "in", self.kind_id.ids),
                ("operator_id", "in", self.future_operator_id.ids),
                ("id", "not in", self.ids),
            ]
        )

    def action_accept_operator_change(self):
        resources = self.filtered("future_operator_id")
        resources._get_assets_released_by_operator_change().operator_id = False
        now = fields.Datetime.now()
        Assignment = self.env["resource.assignment"]
        for resource in resources:
            planned = Assignment._get_custody_assignments(
                resource, roles=(OPERATOR_ROLE,), when="planned"
            ).sorted("date_start")[:1]
            previous = resource.operator_id
            current = Assignment._get_custody_assignments(
                resource, roles=(OPERATOR_ROLE,)
            )
            current._end(now)
            planned.date_start = now
            resource.invalidate_recordset(
                ["operator_id", "future_operator_id", "date_future_operator"]
            )
            resource._post_custody_message(
                OPERATOR_ROLE, previous, resource.operator_id
            )

    def action_view_operator_history(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Operators"),
            "view_mode": "list,form",
            "res_model": "resource.assignment",
            "domain": [
                ("resource_id", "=", self.id),
                ("custody_role", "=", OPERATOR_ROLE),
            ],
            "context": {
                "default_resource_id": self.id,
                "default_role": OPERATOR_ROLE,
                "active_test": False,
            },
        }

    def _get_holder(self, custody_role=None, at=None):
        self.check_singleton()
        return self.env["resource.assignment"]._get_holder(
            self, custody_role=custody_role, at=at
        )
