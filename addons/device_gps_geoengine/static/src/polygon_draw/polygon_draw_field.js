/** @odoo-module **/

import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";

import { PolygonDrawDialog } from "./polygon_draw_dialog.js";

export class PolygonDrawField extends Component {
    static template = "device_gps_geoengine.PolygonDrawField";
    static props = standardFieldProps;
    props = useProps(this.constructor.props);

    setup() {
        this.dialogService = useService("dialog");
    }

    /**
     * @returns {Array<[number, number]>}
     */
    get points() {
        const raw = this.props.record.data[this.props.name];
        if (!raw) {
            return [];
        }
        try {
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    }

    /** @returns {number} */
    get pointCount() {
        return this.points.length;
    }

    /** @returns {string} */
    get buttonLabel() {
        const count = this.pointCount;
        if (count === 0) {
            return _t("Draw polygon on map");
        }
        return _t("Edit polygon on map (%s points)", count);
    }

    openDialog() {
        this.dialogService.add(PolygonDrawDialog, {
            initialPoints: this.points,
            currentRecordId: this.props.record.resId || false,
            readonly: this.props.readonly,
            onConfirm: (points) => {
                this.props.record.update({
                    [this.props.name]: JSON.stringify(points),
                });
            },
            onClear: () => {
                this.props.record.update({ [this.props.name]: false });
            },
        });
    }
}

registry.category("fields").add("polygon_draw", {
    component: PolygonDrawField,
    supportedTypes: ["text"],
});
