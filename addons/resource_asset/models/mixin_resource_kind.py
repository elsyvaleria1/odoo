from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .resource_resource import ASSET_INITIAL_STATE, KIND_MODEL_CREATING

# what a thing decides at its creation, which a person's defaults must not
THING_DECIDES = ("type", "state", "calendar_id")
THING_STARTS = {"type": "material", "state": ASSET_INITIAL_STATE}


def without_resource_defaults(model, fields, defaults):
    """The resource's defaults for what a thing decides itself are not values a
    model delegating to it hands down: a thing starts in its own state, as the
    thing it is. A required one is given the thing's own value, so a form can
    be saved; the calendar is left to create, which reads the kind."""
    for name in THING_DECIDES:
        if name in fields and f"default_{name}" not in model.env.context:
            if name in THING_STARTS:
                defaults[name] = THING_STARTS[name]
            else:
                defaults.pop(name, None)
    return defaults


def _resource_action(name):
    def action(self):
        return getattr(self.resource_id, name)()

    action.__name__ = name
    return action


class MixinResourceKind(models.AbstractModel):
    """What a resource of one kind adds, in a table of its own, under its
    resource's id. The resource keeps everything every thing has; this model
    keeps what only its kind has, and its form extends the asset form."""

    _name = "mixin.resource.kind"
    _description = "Resource Kind Extension"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _inherits = {"resource.resource": "resource_id"}
    _inherits_shared_id = "resource_id"
    _order = "name, id"
    _resource_kind_code = ""

    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        required=True,
        ondelete="cascade",
    )

    # the asset form's buttons call the resource; a form of this model shows
    # them, and an object button must name a method of the record it is on
    action_accept_operator_change = _resource_action("action_accept_operator_change")
    action_dispose = _resource_action("action_dispose")
    action_end_maintenance = _resource_action("action_end_maintenance")
    action_open_depreciation = _resource_action("action_open_depreciation")
    action_set_available = _resource_action("action_set_available")
    action_set_in_service = _resource_action("action_set_in_service")
    action_set_maintenance = _resource_action("action_set_maintenance")
    action_set_out_of_service = _resource_action("action_set_out_of_service")
    action_view_bills = _resource_action("action_view_bills")
    action_view_device_devices = _resource_action("action_view_device_devices")
    action_view_documents = _resource_action("action_view_documents")
    action_view_flagged_parts = _resource_action("action_view_flagged_parts")
    action_view_logs = _resource_action("action_view_logs")
    action_view_logs_all = _resource_action("action_view_logs_all")
    action_view_logs_fuel = _resource_action("action_view_logs_fuel")
    action_view_logs_service = _resource_action("action_view_logs_service")
    action_view_maintenance = _resource_action("action_view_maintenance")
    action_view_maintenance_plans = _resource_action("action_view_maintenance_plans")
    action_view_operator_history = _resource_action("action_view_operator_history")
    action_view_parts = _resource_action("action_view_parts")

    @api.depends("resource_id.display_name")
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.resource_id.display_name

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        calendar_id = defaults.get("calendar_id")
        defaults = without_resource_defaults(self, fields, defaults)
        if "calendar_id" in fields and "default_calendar_id" not in self.env.context:
            # what create decides for this kind, so a form of it can be saved
            defaults["calendar_id"] = (
                calendar_id
                if self._get_kind().scheduled
                else self.env["resource.calendar"]._get_fully_flexible_calendar().id
            )
        return defaults

    @api.model
    def _get_kind(self):
        return self.env["resource.kind"].search(
            [("code", "=", self._resource_kind_code)], limit=1
        )

    @api.model_create_multi
    def create(self, vals_list):
        kind = self._get_kind()
        for vals in vals_list:
            if not vals.get("resource_id"):
                vals.setdefault("kind_id", kind.id)
            if vals.get("kind_id") and vals["kind_id"] != kind.id:
                raise ValidationError(
                    self.env._(
                        "A %(model)s extends a resource of kind %(kind)s only.",
                        model=self._description,
                        kind=kind.display_name,
                    )
                )
        records = super(
            MixinResourceKind, self.with_context(**{KIND_MODEL_CREATING: self._name})
        ).create(vals_list)
        # the identifiers this model holds are written only now
        records.resource_id.with_context(
            **{KIND_MODEL_CREATING: False}
        )._check_required_identifiers()
        return records

    def write(self, vals):
        res = super().write(vals)
        # what is written on the resource is heard through it
        own = {
            name: value
            for name, value in vals.items()
            if name in self._fields and not self._fields[name].inherited
        }
        if own:
            self._on_resource_written(own)
        return res

    def _on_resource_written(self, vals) -> None:
        """Hook: these records, or the resources they extend, were written
        `vals`."""
