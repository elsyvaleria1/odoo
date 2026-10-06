// @ts-check
/** @odoo-module native */

import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { Setting } from "@web/views/form/setting/setting";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

class ResConfigEdition extends Component {
    static template = "res_config_edition";
    static components = { Setting };
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        /** @type {string} */
        this.serverVersion = session.server_version;
    }
}

/** @type {import("registries").ViewWidgetsRegistryItemShape} */
const resConfigEdition = {
    component: ResConfigEdition,
};

registry.category("view_widgets").add("res_config_edition", resConfigEdition);
