/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registerField } from "@web/fields/_registry";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class GeoFormField extends Component {
    static template = "geoengine.GeoFormField";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    get displayValue() {
        const value = this.props.record.data[this.props.name];
        if (!value) {
            return "";
        }
        try {
            const geom = typeof value === "string" ? JSON.parse(value) : value;
            if (geom && geom.type) {
                return geom.coordinates !== undefined
                    ? `${geom.type} ${JSON.stringify(geom.coordinates)}`
                    : geom.type;
            }
        } catch {}
        return String(value);
    }
}

const GEO_TYPES = [
    "geo_point",
    "geo_line",
    "geo_polygon",
    "geo_multi_point",
    "geo_multi_line",
    "geo_multi_polygon",
];

export const geoFormField = {
    component: GeoFormField,
    displayName: "Geometry",
};

for (const geoType of GEO_TYPES) {
    registerField(geoType, geoFormField);
}
