from collections import defaultdict
from typing import Self

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, Query
from odoo.tools.translate import html_translate

from odoo.addons.resource.fields import ResourceIdentifier
from odoo.addons.resource.models.utils import (
    MANAGER_ROLE,
    OPERATOR_ROLE,
)

_debug = DebugLog(__name__)

CUSTODY_SILENT = "custody_silent"

SKIP_IDENTITY_CHECK = "skip_asset_identity_check"


class ResourceAsset(models.Model):
    _name = "resource.asset"
    _description = "Asset"
    _inherit = [
        "mixin.table.inheritance.root",
        "mixin.mail.thread",
        "mixin.mail.activity",
        "mixin.avatar",
        "mixin.resource",
    ]
    _inherits = {"resource.resource": "resource_id"}
    _inherits_shared_id = "resource_id"
    # an asset's row is governed by the asset's rules: it writes its resource
    # as the system (`_write_through_resource`), and its other resource fields
    # are read under the resource's rules
    _inherits_rules = False
    _table_inheritance_root = "resource_asset"
    _resource_type = "material"
    # A write through the root reaches each row's concrete model, so a kind's
    # hooks run whichever model the caller holds; every polymorphic reference
    # those hooks record names the root (`_get_reference_model_name`).
    _dispatch_write_to_concrete = True
    _order = "name, id"
    _check_company_auto = True

    resource_id = fields.Many2one(
        delegate=True,
        ondelete="cascade",
    )
    name = fields.Char(  # noqa: E8529  identity column of a delegated record: the asset, SAF-T and compliance reports read it in raw SQL across three repos
        related="resource_id.name",
        store=True,
        readonly=False,
    )
    active = fields.Boolean(  # noqa: E8529  identity column of a delegated record: every search filters on it, and the asset reports test it in raw SQL
        related="resource_id.active",
        default=True,
        store=True,
        readonly=False,
    )
    color = fields.Integer(
        related="resource_id.color",
        readonly=False,
    )
    kind_id = fields.Many2one(
        comodel_name="resource.asset.kind",
        index=True,
        required=True,
        ondelete="restrict",
    )
    kind_code = fields.Char(related="kind_id.code")
    state = fields.Selection(
        related="resource_id.state",
        default="draft",
        readonly=False,
        tracking=True,
    )
    state_before_maintenance = fields.Selection(
        related="resource_id.state_before_maintenance",
    )
    date_acquisition = fields.Date(
        related="resource_id.date_acquisition",
        readonly=False,
        tracking=True,
    )
    date_disposal = fields.Date(
        related="resource_id.date_disposal",
        readonly=False,
        tracking=True,
    )
    brand_new = fields.Boolean(default=True)
    model = fields.Char(string="Model Name")
    model_year = fields.Integer(
        help="The commercial model year, which may differ from the year it was built.",
    )
    date_origin = fields.Date(
        related="resource_id.date_origin",
        string="Date Built",
        readonly=False,
    )
    year_origin = fields.Integer(
        related="resource_id.year_origin",
        string="Year Built",
    )
    origin_country_id = fields.Many2one(
        related="resource_id.origin_country_id",
        string="Country of Production",
        readonly=False,
    )
    place_origin = fields.Char(
        related="resource_id.place_origin",
        string="Place of Production",
        readonly=False,
    )
    nationality_ids = fields.One2many(
        related="resource_id.nationality_ids",
        readonly=False,
    )
    description = fields.Html(translate=html_translate)
    vendor_id = fields.Many2one(
        comodel_name="res.partner",
        index="btree_not_null",
        check_company=True,
        tracking=True,
    )
    vendor_ref = fields.Char(string="Vendor Reference")
    warranty_date = fields.Date(string="Warranty Expiration Date")
    # a new asset has no resource yet to read it from
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_currency_id",
        value_sql="_value_sql_currency_id",
    )
    value_original = fields.Monetary(
        related="resource_id.value_original",
        readonly=False,
        tracking=True,
    )
    asset_properties = fields.Properties(
        definition="kind_id.asset_properties_definition",
        copy=True,
    )

    identifier_ids = fields.One2many(
        related="resource_id.identifier_ids",
        readonly=False,
    )
    # Accessors on the root: read and searched through the identifier rows,
    # stored as columns only by the kinds that carry them.
    license_plate = ResourceIdentifier(
        identifier_code="plate",
        through="resource_id",
        store=False,
        help="License plate number of the asset (eg plate number for a car)",
    )
    vin_sn = ResourceIdentifier(
        identifier_code="vin",
        through="resource_id",
        string="Serial Number / VIN",
        store=False,
        help="Unique number written on an asset's chassis (VIN/SN number).",
    )
    engine_sn = ResourceIdentifier(
        identifier_code="engine",
        through="resource_id",
        string="Engine Serial Number",
        store=False,
        help="Unique number written on the asset's engine.",
    )
    missing_identifier_type_ids = fields.Many2many(
        comodel_name="resource.identifier.type",
        compute="_compute_missing_identifier_type_ids",
        search="_search_missing_identifier_type_ids",
    )
    meter_ids = fields.One2many(
        related="resource_id.meter_ids",
        readonly=False,
    )
    odometer_meter_id = fields.Many2one(
        comodel_name="resource.meter",
        compute="_compute_odometer_meter_id",
        store=True,
    )
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
    address_id = fields.Many2one(
        comodel_name="res.partner",
        string="Location",
        help="Where the asset normally is, when no inventory location tracks it.",
    )
    assignment_ids = fields.One2many(related="resource_id.assignment_ids")
    holder_id = fields.Many2one(related="resource_id.holder_id")
    operator_id = fields.Many2one(
        related="resource_id.operator_id",
        readonly=False,
        check_company=True,
    )
    manager_id = fields.Many2one(
        related="resource_id.manager_id",
        readonly=False,
        check_company=True,
    )
    future_operator_id = fields.Many2one(
        related="resource_id.future_operator_id",
        readonly=False,
        check_company=True,
    )
    date_future_operator = fields.Datetime(
        related="resource_id.date_future_operator",
        readonly=False,
    )
    operator_history_count = fields.Integer(compute="_compute_operator_history_count")
    parent_id = fields.Many2one(
        comodel_name="resource.asset",
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
        comodel_name="resource.asset",
        inverse_name="parent_id",
        string="Components",
    )

    _resource_uniq = models.Constraint(
        "UNIQUE(resource_id)", "A resource is one asset at most."
    )

    @api.depends("company_id")
    def _compute_currency_id(self) -> None:
        fallback = self.env.company.currency_id
        for asset in self:
            asset.currency_id = asset.company_id.currency_id or fallback

    def _value_sql_currency_id(self, field, alias, query=None):
        return SQL(
            "COALESCE((SELECT currency_id FROM res_company WHERE id = %s), %s)",
            self._field_to_sql(alias, "company_id", query),
            self.env.company.currency_id.id,
        )

    @api.depends("meter_ids.kind")
    def _compute_odometer_meter_id(self) -> None:
        for asset in self:
            asset.odometer_meter_id = asset.meter_ids.filtered(
                lambda m: m.kind == "odometer"
            )[:1]

    @api.depends("odometer_meter_id.last_reading_id.value")
    def _compute_odometer(self) -> None:
        for asset in self:
            asset.odometer = asset.odometer_meter_id.value

    def _inverse_odometer(self) -> None:
        for asset in self:
            meter = asset.odometer_meter_id
            if not asset.odometer and not meter:
                continue
            if not meter:
                meter = asset._create_odometer_meter()
            if meter.value > asset.odometer:
                _debug.logic(
                    "odometer.refused", reason="below_last_reading", asset=asset
                )
                raise ValidationError(
                    self.env._(
                        "%(asset)s: the odometer cannot go below its last reading of %(value)s.",
                        asset=asset.display_name,
                        value=meter.value,
                    )
                )
            if meter.value != asset.odometer:
                meter.record(asset.odometer)

    def _create_odometer_meter(self):
        self.check_singleton()
        meter = self.env["resource.meter"].create(
            {
                "resource_id": self.resource_id.id,
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
        changing = self.filtered(lambda asset: asset.odometer_uom_id.id != new_uom_id)
        with_readings = changing.sudo().filtered(
            lambda asset: asset.odometer_meter_id.reading_ids
        )
        if with_readings:
            _debug.logic("odometer_uom.refused", reason="readings_exist", assets=self)
            raise ValidationError(
                self.env._(
                    "%(assets)s already carry odometer readings in their current "
                    "unit. Changing it now would restate every one of them; "
                    "convert the readings deliberately instead.",
                    assets=", ".join(with_readings.mapped("display_name")),
                )
            )

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
        enforced = self.filtered(lambda asset: asset.kind_id.enforce_identifiers)
        if not enforced:
            return
        enforced.invalidate_recordset(
            [
                "identifier_ids",
                "missing_identifier_type_ids",
                *self._get_identifier_field_names(),
            ]
        )
        for asset in enforced:
            missing = asset.missing_identifier_type_ids
            if missing:
                _debug.logic(
                    "asset.refused", reason="missing_required_identifiers", asset=asset
                )
                raise ValidationError(
                    self.env._(
                        "%(asset)s is a %(kind)s, which requires %(types)s.",
                        asset=asset.name or self.env._("This asset"),
                        kind=asset.kind_id.display_name,
                        types=", ".join(missing.mapped("name")),
                    )
                )

    @api.depends("identifier_ids.type_id", "kind_id.identifier_type_ids")
    def _compute_missing_identifier_type_ids(self) -> None:
        for asset in self:
            asset.missing_identifier_type_ids = (
                asset.kind_id.identifier_type_ids - asset.identifier_ids.type_id
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
                resource=SQL.identifier(alias, "resource_id"),
                types=type_condition or SQL("TRUE"),
            )

        return Domain.custom(to_sql=to_sql)

    @api.depends(
        "resource_id",
        "resource_id.membership_ids.parent_id",
        "resource_id.membership_ids.relation_type",
        "resource_id.membership_ids.active",
        "resource_id.membership_ids.date_start",
        "resource_id.membership_ids.date_end",
    )
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_parent_id(self):
        Relation = self.env["resource.relation"]
        relations = Relation.search(
            Relation._get_domain_live_relations()
            + [
                ("member_id", "in", self.resource_id.ids),
            ]
        )
        assets = (
            self.env["resource.asset"]
            .with_context(active_test=False)
            .search(
                [
                    ("resource_id", "in", relations.parent_id.ids),
                ]
            )
        )
        by_resource = {asset.resource_id.id: asset for asset in assets}
        by_member = {
            relation.member_id.id: by_resource.get(relation.parent_id.id, False)
            for relation in relations
        }
        for asset in self:
            asset.parent_id = by_member.get(asset.resource_id.id, False)

    def _parent_id_sql(self, field, alias, query=None):
        Relation = self.env["resource.relation"]
        relations = Relation._search(Relation._get_domain_live_relations())
        parents = self.env["resource.asset"].with_context(active_test=False)._search([])
        return SQL(
            """(SELECT parent.id FROM resource_relation relation
                  JOIN resource_asset parent ON parent.resource_id = relation.parent_id
                 WHERE relation.member_id = %s AND relation.id IN %s
                   AND parent.id IN %s)""",
            self._field_to_sql(alias, "resource_id", query),
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
        for asset in self:
            asset._set_parent_asset(asset.parent_id)

    def _set_parent_asset(self, parent, operation="write"):
        self.check_singleton()
        self.check_access(operation)
        parent = self.env["resource.asset"].browse(parent.ids)
        if parent:
            parent._get_concrete().check_access("write")
        if parent == self:
            raise ValidationError(self.env._("An asset cannot be a part of itself."))
        Relation = self.env["resource.relation"]
        # Only identities leave this integrity lookup. Authorization remains on
        # normal asset/resource records before the scoped membership mutation.
        old_ids = (
            Relation.sudo()
            .search(
                Relation._get_domain_live_relations()
                + [
                    ("member_id", "=", self.resource_id.id),
                ]
            )
            .parent_id.ids
        )
        old_resources = self.env["resource.resource"].browse(old_ids)
        old_assets = (
            self.env["resource.asset"]
            .with_context(active_test=False)
            .search(
                [
                    ("resource_id", "in", old_ids),
                ]
            )
        )
        if not parent and old_ids and not old_assets:
            # Clearing an empty asset projection does not detach a non-asset
            # resource parent. That membership is edited through resource.
            return
        for old_asset in old_assets:
            old_asset._get_concrete().check_access("write")
        non_asset_parents = old_resources - old_assets.resource_id
        if non_asset_parents:
            non_asset_parents.check_access("write")
        with self.env.cr.savepoint():
            Relation.sudo()._set_containment_parent(
                self.resource_id.sudo(),
                (
                    parent.resource_id if parent else self.env["resource.resource"]
                ).sudo(),
            )
        self.invalidate_recordset(["parent_id"])

    @api.ondelete(at_uninstall=False)
    def _unlink_except_membership_history(self):
        if (
            self.env["resource.relation"]
            .sudo()
            .with_context(active_test=False)
            .search_count(
                [
                    "|",
                    ("parent_id", "in", self.resource_id.ids),
                    ("member_id", "in", self.resource_id.ids),
                ],
                limit=1,
            )
        ):
            raise ValidationError(
                self.env._(
                    "Archive assets with resource membership history instead of deleting them."
                )
            )

    def _around_the_clock(self, vals):
        """The fully flexible schedule: an unscheduled kind is available around
        the clock, and a shared (company-less) asset of a scheduled kind cannot
        take one company's hours -- every reader would then see a company
        crossover."""
        if "resource_calendar_id" in vals:
            return False
        kind = self.env["resource.asset.kind"].browse(vals.get("kind_id"))
        shared = "company_id" in vals and not vals["company_id"]
        return not kind.scheduled or shared

    def _prepare_resource_values(self, vals, tz):
        resource_vals = super()._prepare_resource_values(vals, tz)
        if self._around_the_clock(vals):
            resource_vals["calendar_id"] = (
                self.env["resource.calendar"]._get_fully_flexible_calendar().id
            )
        # What the asset relays to its resource is born with the resource:
        # popped here, it never reaches a related inverse run as the user.
        resource_vals.update(self._pop_resource_vals(vals))
        resource_vals.setdefault("state", self._fields["state"].default(self))
        return resource_vals

    @api.model_create_multi
    def create(self, vals_list):
        if self._name == self._get_root_model_name():
            dispatched = self._create_in_kind_models(vals_list)
            if dispatched is not None:
                return dispatched
        self._check_kind_belongs_to_this_model(vals_list)
        parent_values = [
            vals.pop("parent_id", self.env.context.get("default_parent_id"))
            for vals in vals_list
        ]
        given = [dict(vals) for vals in vals_list]
        resource_vals_list = []
        for vals in vals_list:
            if vals.get("kind_id") and self._around_the_clock(vals):
                vals["resource_calendar_id"] = (
                    self.env["resource.calendar"]._get_fully_flexible_calendar().id
                )
            # A new resource takes these at birth (_prepare_resource_values);
            # one given ready-made is written as the system after the create.
            resource_vals_list.append(
                self._pop_resource_vals(vals) if vals.get("resource_id") else {}
            )
        context = dict(self.env.context)
        context.pop("default_parent_id", None)
        assets = super(ResourceAsset, self.with_context(context)).create(vals_list)
        for asset, resource_vals, vals in zip(
            assets, resource_vals_list, given, strict=True
        ):
            if resource_vals:
                asset.resource_id.sudo().write(resource_vals)
            asset._on_kind_changed(vals)
        for asset, parent_id in zip(assets, parent_values, strict=True):
            if parent_id:
                asset._set_parent_asset(
                    self.env["resource.asset"].browse(parent_id), operation="create"
                )
        return assets

    def _write_concrete(self, vals):
        if "kind_id" in vals:
            self._check_kind_stays_in_this_table(vals["kind_id"])
        if "odometer_uom_id" in vals:
            self._check_odometer_uom_is_not_reinterpreted(vals["odometer_uom_id"])
        res = self._write_through_resource(vals)
        self._check_identity_after(vals)
        return res

    def _check_identity_after(self, vals) -> None:
        if "kind_id" in vals:
            self._on_kind_changed(vals)
        elif vals.keys() & {"identifier_ids", *self._get_identifier_field_names()}:
            self._check_required_identifiers()

    def _write_through_resource(self, vals):
        vals = dict(vals)
        resource_vals = self._pop_resource_vals(vals)
        if resource_vals and self:
            self.check_access("write")
            if not (
                self.env.context.get("tracking_disable")
                or self.env.context.get("mail_notrack")
            ):
                # mail's write runs below this one: the tracked values it reads
                # first would already be the resource's new ones
                self._track_prepare(resource_vals)
            self.resource_id.sudo().write(resource_vals)
        if not vals:
            return True
        return super()._write_concrete(vals)

    def _compute_operator_history_count(self) -> None:
        counts = dict(
            self.env["resource.assignment"]._read_group(
                [
                    ("resource_id", "in", self.resource_id.ids),
                    ("custody_role", "=", OPERATOR_ROLE),
                ],
                ["resource_id"],
                ["__count"],
            )
        )
        for asset in self:
            asset.operator_history_count = counts.get(asset.resource_id, 0)

    def _on_custody_changed(self, role, changes, planned=False):
        for asset in self:
            before, after = changes[asset.resource_id.id]
            asset._post_custody_message(role, before, after, planned=planned)

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
        assets = self.filtered("future_operator_id")
        assets._get_assets_released_by_operator_change().operator_id = False
        now = fields.Datetime.now()
        Assignment = self.env["resource.assignment"]
        for asset in assets:
            resource = asset.resource_id
            planned = Assignment._get_custody_assignments(
                resource, roles=(OPERATOR_ROLE,), when="planned"
            ).sorted("date_start")[:1]
            previous = asset.operator_id
            current = Assignment._get_custody_assignments(
                resource, roles=(OPERATOR_ROLE,)
            )
            current._end(now)
            planned.date_start = now
            resource.invalidate_recordset(
                ["operator_id", "future_operator_id", "date_future_operator"]
            )
            asset._post_custody_message(OPERATOR_ROLE, previous, asset.operator_id)

    def action_view_operator_history(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Operators"),
            "view_mode": "list,form",
            "res_model": "resource.assignment",
            "domain": [
                ("resource_id", "=", self.resource_id.id),
                ("custody_role", "=", OPERATOR_ROLE),
            ],
            "context": {
                "default_resource_id": self.resource_id.id,
                "default_role": OPERATOR_ROLE,
                "active_test": False,
            },
        }

    def action_set_available(self) -> None:
        self._transition("available")

    def action_set_in_service(self) -> None:
        self._transition("in_service")

    def action_set_maintenance(self) -> None:
        self._transition("maintenance")

    def action_end_maintenance(self) -> None:
        self._end_maintenance()

    def _end_maintenance(self) -> None:
        under_maintenance = self.filtered(lambda asset: asset.state == "maintenance")
        for state, assets in under_maintenance.grouped(
            lambda asset: asset.resource_id._get_state_after_maintenance()
        ).items():
            assets._transition(state)

    def action_set_out_of_service(self) -> None:
        self._transition("out_of_service")

    def action_dispose(self):
        return self._dispose()

    def _dispose(self, date=None):
        self._transition("disposed", date=date)

    def _transition(self, state, date=None) -> None:
        _debug.lifecycle("transition", assets=self, state=state, date=date)
        self.write(self.env["resource.resource"]._get_transition_vals(state, date))

    def _check_transition(self, state):
        pass

    def _check_reactivation(self):
        pass

    def _on_kind_changed(self, vals) -> None:
        self._check_required_identifiers()

    @api.model
    def _get_model_for_kind(self, kind) -> str:
        root = self._get_root_model_name()
        if not kind.code:
            return root
        model_name = f"{root}.{kind.code}"
        if model_name in self._get_model_names_in_tree():
            return model_name
        return root

    def _create_in_kind_models(self, vals_list) -> Self | None:
        Kind = self.env["resource.asset.kind"]
        by_model = defaultdict(list)
        for index, vals in enumerate(vals_list):
            kind = Kind.browse(vals.get("kind_id"))
            by_model[self._get_model_for_kind(kind)].append((index, vals))
        if set(by_model) <= {self._name}:
            return None
        _debug.pipeline(
            "resource_asset.create_dispatched",
            models={name: len(rows) for name, rows in by_model.items()},
        )
        created = {}
        for model_name, indexed in by_model.items():
            records = self.env[model_name].create([vals for __, vals in indexed])
            for (index, __), record in zip(indexed, records, strict=True):
                created[index] = record.id
        return self.browse(created[index] for index in range(len(vals_list)))

    def _check_kind_stays_in_this_table(self, kind_id) -> None:
        kind = self.env["resource.asset.kind"].browse(kind_id)
        target = self._get_model_for_kind(kind)
        for model_name in self._get_model_names_concrete().values():
            if model_name != target:
                _debug.logic("write.refused", reason="kind_changes_table", assets=self)
                raise ValidationError(
                    self.env._(
                        "An asset of kind %(kind)s is a %(model)s, and no row moves "
                        "between the two tables. Create it there instead.",
                        kind=kind.display_name,
                        model=target,
                    )
                )

    def _retype(self, kind) -> Self:
        """Deliberately make these assets a kind of another model. A kind
        names a table, and this is the one door through which a row changes
        table: parent to child is a DELETE and an INSERT, which the shared
        sequence and the absence of foreign keys into the root allow. A column
        only the source model declares does not travel; a stored compute only
        the target declares is computed afresh."""
        target = self._get_model_for_kind(kind)
        by_source = defaultdict(list)
        for record_id, model_name in self._get_model_names_concrete().items():
            if model_name != target:
                by_source[model_name].append(record_id)
        _debug.lifecycle(
            "retype",
            assets=self,
            target=target,
            moving={source: len(ids) for source, ids in by_source.items()},
        )
        if by_source:
            self.env.flush_all()
            Target = self.env[target]
            for source, ids in by_source.items():
                source_table = self.env[source]._table
                columns = self._get_columns_shared(source_table, Target._table)
                self.env.cr.execute(
                    SQL(
                        """
                        WITH moved AS (
                            DELETE FROM ONLY %(source)s WHERE id = ANY(%(ids)s) RETURNING *
                        )
                        INSERT INTO %(target)s (%(columns)s) SELECT %(columns)s FROM moved
                        """,
                        source=SQL.identifier(source_table),
                        target=SQL.identifier(Target._table),
                        ids=ids,
                        columns=SQL(", ").join(SQL.identifier(c) for c in columns),
                    )
                )
                _debug.lifecycle(
                    "resource_asset.rows_retyped",
                    source=source,
                    target=target,
                    rows=len(ids),
                )
            self.env.registry.clear_cache("default")
            self.env.invalidate_all()
            moved = Target.browse(
                [record_id for ids in by_source.values() for record_id in ids]
            )
            root_fields = self.env[self._get_root_model_name()]._fields
            for name, field in Target._fields.items():
                root_field = root_fields.get(name)
                stored_by_root = root_field is not None and root_field.store
                if field.store and field.compute and not stored_by_root:
                    field.compute_value(moved)
            self.env.flush_all()
        self.with_context(active_test=False).write({"kind_id": kind.id})
        return self.browse(self.ids)

    @api.model
    def _get_columns_shared(self, source_table, target_table) -> list[str]:
        self.env.cr.execute(
            """
            SELECT a.column_name
              FROM information_schema.columns a
              JOIN information_schema.columns b
                ON b.column_name = a.column_name AND b.table_name = %s
             WHERE a.table_name = %s
             ORDER BY a.ordinal_position
            """,
            [target_table, source_table],
        )
        return [row[0] for row in self.env.cr.fetchall()]

    def _check_kind_belongs_to_this_model(self, vals_list) -> None:
        Kind = self.env["resource.asset.kind"]
        for vals in vals_list:
            kind = Kind.browse(vals.get("kind_id"))
            if not kind:
                continue
            model_name = self._get_model_for_kind(kind)
            if model_name != self._name:
                _debug.logic(
                    "create.refused", reason="kind_of_another_model", model=self._name
                )
                raise ValidationError(
                    self.env._(
                        "An asset of kind %(kind)s is a %(model)s, and no row "
                        "moves between the two tables. Create it there instead.",
                        kind=kind.display_name,
                        model=model_name,
                    )
                )

    def _get_type_field_name(self) -> str:
        return ""

    def _get_holder(self, custody_role=None, at=None):
        self.check_singleton()
        return self.env["resource.assignment"]._get_holder(
            self.resource_id, custody_role=custody_role, at=at
        )
