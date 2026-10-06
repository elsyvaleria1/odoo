// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { router } from "@web/core/browser/router";
import { useService } from "@web/core/utils/hooks";

export class HomeTileRecordLink extends Component {
    static template = "web.HomeTileRecordLink";
    static props = {
        resModel: t.string(),
        resId: t.number(),
        className: t.string().optional(),
        slots: t.object().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    get href() {
        return router.stateToUrl({
            model: this.props.resModel,
            resId: this.props.resId,
        });
    }

    /** @param {MouseEvent} ev */
    onClick(ev) {
        // a modified or secondary click is the browser's: a new tab, a window
        if (ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) {
            return;
        }
        ev.preventDefault();
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: this.props.resModel,
            res_id: this.props.resId,
            views: [[false, "form"]],
        });
    }
}
