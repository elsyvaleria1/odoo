/** @odoo-module native */
import { Component, useProps, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";

class DefaultField extends Component {
    static template = xml``;
    static props = null;
    props = useProps(this.constructor.props);
}
registry
    .category("fields")
    .add("list.many2one_avatar_user", { component: DefaultField });
registry.category("fields").add("list.list_activity", { component: DefaultField });
