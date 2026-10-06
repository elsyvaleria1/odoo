/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useBus, useService } from "@web/core/utils/hooks";

export class ProjectRightSidePanelSection extends Component {
    static props = {
        name: t.string().optional(),
        header: t.boolean().optional(true),
        show: t.boolean(),
        showData: t.boolean().optional(true),
        slots: t.object({
            default: t.object(),
            header: t.object().optional(),
            title: t.object().optional(),
        }),
        dataClassName: t.object().optional(),
        headerClassName: t.string().optional(),
        canBeClosed: t.boolean().optional(true),
    };

    static template = "project.ProjectRightSidePanelSection";
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.state = proxy({
            isClosed: !!this.ui.isSmall && this.props.canBeClosed,
        });

        useBus(this.ui.bus, "resize", this.setDefaultIsClosed.bind(this));
    }

    setDefaultIsClosed() {
        this.state.isClosed = this.ui.isSmall && this.props.canBeClosed;
    }

    toggleSection() {
        if (!this.ui.isSmall || !this.props.canBeClosed) {
            this.state.isClosed = false;
        } else {
            this.state.isClosed = !this.state.isClosed;
        }
    }
}
