/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class ViewEditorSnackbar extends Component {
    static template = "web_studio.ViewEditor.Snackbar";
    static props = { operations: t.object(), saveIndicator: t.object() };
    props = useProps(this.constructor.props);
}
