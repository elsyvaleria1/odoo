/** @odoo-module native */
import { Component, onMounted, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";

export class DragAndDropMoveHandle extends Component {
    static template = "html_builder.DragAndDropMoveHandle";
    static props = { onRenderedCallback: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.title = _t("Drag and move");

        onMounted(() => {
            this.props.onRenderedCallback();
        });
    }
}
