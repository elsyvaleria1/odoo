/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

import { basicContainerBuilderComponentProps } from "../utils.js";
import { SelectMany2X } from "./select_many2x.js";

export class BasicMany2Many extends Component {
    static template = "html_builder.BasicMany2Many";
    static props = {
        ...basicContainerBuilderComponentProps,
        model: t.string(),
        fields: t.array(t.string()).optional(),
        domain: t.array().optional(),
        limit: t.number().optional(),
        selection: t.array(t.object()),
        setSelection: t.function(),
        create: t.function().optional(),
    };
    static components = { SelectMany2X };
    props = useProps(this.constructor.props);

    select(entry) {
        this.props.setSelection([...this.props.selection, entry]);
    }
    unselect(id) {
        this.props.setSelection([
            ...this.props.selection.filter((item) => item.id !== id),
        ]);
    }
}
