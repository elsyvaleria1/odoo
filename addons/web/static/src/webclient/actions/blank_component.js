// @ts-check
/** @odoo-module native */

import { Component, onMounted, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { provideChildViewConfig } from "@web/core/view_config_hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";

export class BlankComponent extends Component {
    static props = null;
    static template = "web.BlankComponent";
    static components = { ControlPanel };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        provideChildViewConfig({ breadcrumbs: [], noBreadcrumbs: true });
        onMounted(() => this.props.onMounted());
    }
}
