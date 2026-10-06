// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export class RibbonWidget extends Component {
    static template = "web.Ribbon";
    static props = {
        ...standardWidgetProps,
        record: t.object().optional(),
        text: t.string(),
        title: t.string().optional(""),
        bgClass: t.string().optional("text-bg-success"),
    };
    props = useProps(this.constructor.props);

    /** @returns {string} */
    get classes() {
        let classes = this.props.bgClass;
        if (this.props.text.length > 15) {
            classes += " o_small";
        } else if (this.props.text.length > 10) {
            classes += " o_medium";
        }
        return classes;
    }
}

/** @type {import("registries").ViewWidgetsRegistryItemShape} */
const ribbonWidget = {
    component: RibbonWidget,
    extractProps: ({ attrs }) => ({
        text: attrs.title || attrs.text || "",
        title: attrs.tooltip,
        bgClass: attrs.bg_color,
    }),
    supportedAttributes: [
        {
            label: _t("Title"),
            name: "title",
            type: "string",
        },
        {
            label: _t("Background color"),
            name: "bg_color",
            type: "string",
        },
        {
            label: _t("Tooltip"),
            name: "tooltip",
            type: "string",
        },
    ],
};

registry.category("view_widgets").add("web_ribbon", ribbonWidget);
