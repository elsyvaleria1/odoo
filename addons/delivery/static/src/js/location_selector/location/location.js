/** @odoo-module native */
import { LocationSchedule } from "@delivery/js/location_selector/location_schedule/location_schedule";
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";

export class Location extends Component {
    static components = { LocationSchedule };
    static template = "delivery.locationSelector.location";
    static props = {
        id: t.string(),
        number: t.number(),
        name: t.string(),
        street: t.string(),
        city: t.string(),
        zipCode: t.string(),
        openingHours: t.record(t.array(t.string()).optional()),
        additionalData: t.object().optional(),
        isSelected: t.boolean(),
        setSelectedLocation: t.function(),
    };
    props = useProps(this.constructor.props);

    /** @return {Object} */
    getCityAndZipCode() {
        return `${this.props.zipCode} ${this.props.city}`;
    }

    get openingHoursLabel() {
        return _t("Opening hours");
    }
}
