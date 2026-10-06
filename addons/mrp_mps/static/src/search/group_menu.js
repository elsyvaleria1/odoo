/** @odoo-module native */
import { useMrpMpsContext } from "@mrp_mps/mrp_mps_context";
import { Component, t, useProps } from "@odoo/owl";
import { CheckboxItem } from "@web/components/dropdown";

export class GroupMenu extends Component {
    static template = "mrp_mps.GroupMenu";
    static components = { CheckboxItem };
    static props = { items: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.mpsContext = useMrpMpsContext();
    }

    get items() {
        return this.props.items;
    }

    _toggle_group(group) {
        const value = {};
        value[group] = !this.props.items[group];
        this.mpsContext.model._saveCompanySettings(value);
    }
}
