/** @odoo-module native */
import { Component, proxy, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { registry } from "@web/core/registry";

export class StarshipitServiceSelectionWidget extends Component {
    static template = "delivery_starshipit.StarshipitServiceWidget";
    static components = {
        Dropdown,
        DropdownItem,
    };
    static props = null;
    props = useProps(this.constructor.props);

    setup() {
        this.available_services = this.props.record.data.available_services;
        this.code = this.props.record.data.selected_service_code;
        if (this.code === "") {
            this.code = this.available_services[0].service_code;
            this.props.record.update({ [this.props.name]: this.code });
        }
        this.state = proxy({
            code: this.code,
        });
    }

    get activeService() {
        let service = this.available_services.find(
            (service) => service.service_code === this.state.code,
        );
        if (service === undefined) {
            service = this.available_services[0];
        }
        return service;
    }

    _onSelected(code) {
        this.state.code = code;
        this.props.record.update({ [this.props.name]: code });
    }
}

export const starshipitServiceSelectionWidget = {
    component: StarshipitServiceSelectionWidget,
};

registry
    .category("fields")
    .add("starshipit_service_selection", starshipitServiceSelectionWidget);
