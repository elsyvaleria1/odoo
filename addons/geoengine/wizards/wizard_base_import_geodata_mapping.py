import logging

from odoo import fields, models

from ..models.geo_types import GEO_FIELD_TTYPES

logger = logging.getLogger(__name__)


class WizardBaseImportGeodataMapping(models.TransientModel):
    _name = "wizard.base.import.geodata.mapping"
    _description = "GeoJSON Import Field Mapping"

    wizard_id = fields.Many2one(
        comodel_name="wizard.base.import.geodata",
        required=True,
        ondelete="cascade",
    )
    property_name = fields.Char(
        required=True,
        help="Property name from GeoJSON features",
    )
    field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        required=True,
        domain="[('model_id', '=', parent.model_id), "
        f"('ttype', 'not in', {[*GEO_FIELD_TTYPES, 'one2many', 'many2many']}), "
        "('readonly', '=', False)]",
        help="Odoo field to map this property to",
    )
