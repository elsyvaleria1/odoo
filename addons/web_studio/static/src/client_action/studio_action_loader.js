/** @odoo-module native */
import { Component, t, useProps, xml } from "@odoo/owl";
import { LazyComponent } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions";

class StudioActionLoader extends Component {
    static components = { LazyComponent };
    static template = xml`
        <LazyComponent bundle="'web_studio.studio_assets'" Component="'StudioClientAction'" props="this.props"/>
    `;
    static props = {
        ...standardActionServiceProps,
        props: t.object().optional(),
        Component: t.function().optional(),
    };
    props = useProps(this.constructor.props);
}
registry.category("actions").add("studio", StudioActionLoader);
