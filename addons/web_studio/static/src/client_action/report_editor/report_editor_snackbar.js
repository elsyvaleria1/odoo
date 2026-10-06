/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class ReportEditorSnackbar extends Component {
    static template = "web_studio.ReportEditor.SnackBar";
    static props = {
        onSave: t.function(),
        state: t.object(),
        onDiscard: t.function().optional(),
    };
    props = useProps(this.constructor.props);
}
