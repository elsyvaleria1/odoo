from odoo import fields, models

from odoo.addons.resource.models.utils import CUSTODY_SILENT, MANAGER_ROLE


class ResourceResource(models.Model):
    _name = "resource.resource"
    _inherit = ["resource.resource", "mixin.mail.thread", "mixin.mail.activity"]

    im_status = fields.Char(related="user_id.im_status")
    state = fields.Selection(tracking=True)
    date_acquisition = fields.Date(tracking=True)
    date_disposal = fields.Date(tracking=True)
    value_original = fields.Monetary(tracking=True)
    vendor_id = fields.Many2one(tracking=True)
    odometer_uom_id = fields.Many2one(tracking=True)

    def get_avatar_card_data(self, field_names):
        stored = [fname for fname in field_names if fname != "phone"]
        data = self.read(stored) if stored else [{"id": r.id} for r in self]
        if "phone" in field_names:
            for resource, values in zip(self, data, strict=True):
                values["phone"] = resource.partner_id.phone_ids._primary().number
        return data

    def _track_prepare(self, fields_iter):
        # a thing's history is its chatter's; a person's or an intangible's
        # resource keeps none
        return super(ResourceResource, self.filtered("kind_id"))._track_prepare(
            fields_iter
        )

    def _on_custody_changed(self, role, changes, planned=False):
        super()._on_custody_changed(role, changes, planned=planned)
        for resource in self.filtered("kind_id"):
            before, after = changes[resource.id]
            resource._announce_custody_change(role, before, after, planned=planned)

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

    def _announce_custody_change(self, role, before, after, planned=False) -> None:
        self.check_singleton()
        super()._announce_custody_change(role, before, after, planned=planned)
        if before == after or self.env.context.get(CUSTODY_SILENT):
            return
        xml_id = (
            "resource_mail.mt_asset_future_operator_scheduled"
            if planned
            else "resource_mail.mt_asset_operator_updated"
        )
        subtype = self.env.ref(xml_id, raise_if_not_found=False)
        self.sudo().message_post(
            body=self._get_custody_message(role, before, after, planned=planned),
            subtype_id=subtype.id if subtype else None,
        )
