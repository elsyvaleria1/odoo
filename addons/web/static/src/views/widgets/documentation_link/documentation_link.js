// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

const LINK_REGEX = /^https?:\/\//;

export class DocumentationLink extends Component {
    static template = "web.DocumentationLink";
    static props = {
        ...standardWidgetProps,
        record: t.object().optional(),
        path: t.string(),
        label: t.string().optional(),
        icon: t.string().optional(),
        alertLink: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    /** @returns {string} */
    get url() {
        if (LINK_REGEX.test(this.props.path)) {
            return this.props.path;
        } else {
            const serverVersion = session.server_version_info.includes("final")
                ? `${session.server_version_info[0]}.${session.server_version_info[1]}`.replace(
                      "~",
                      "-",
                  )
                : "master";
            return (
                "https://www.odoo.com/documentation/" + serverVersion + this.props.path
            );
        }
    }

    get classes() {
        let classes = "o_doc_link me-2";
        if (this.props.alertLink) {
            classes += " alert-link";
        }
        return classes;
    }
}

/** @type {import("registries").ViewWidgetsRegistryItemShape} */
export const documentationLink = {
    component: DocumentationLink,
    extractProps: ({ attrs }) => {
        const { path, label, icon, alert_link } = attrs;
        return {
            path,
            label,
            icon,
            alertLink: Boolean(alert_link),
        };
    },
    additionalClasses: ["d-inline"],
};

registry.category("view_widgets").add("documentation_link", documentationLink);
