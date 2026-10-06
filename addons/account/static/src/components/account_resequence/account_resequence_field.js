/** @odoo-module native */
import { JsonBlobField } from "@account/components/json_blob_field/json_blob_field";
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";

class ChangeLine extends Component {
    static template = "account.ResequenceChangeLine";
    static props = { changeLine: t.any(), ordering: t.any() };
    props = useProps(this.constructor.props);
}

class ShowResequenceRenderer extends JsonBlobField {
    static template = "account.ResequenceRenderer";
    static components = { ChangeLine };
    get defaultValue() {
        return { changeLines: [], ordering: "date" };
    }
}

registry.category("fields").add("account_resequence_widget", {
    component: ShowResequenceRenderer,
});
