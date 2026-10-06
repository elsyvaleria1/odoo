/** @odoo-module native */
import { Component, useListener, useProps } from "@odoo/owl";
import { provideDebugContext } from "@web/core/debug/debug_context";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { session } from "@web/session";
import { MainComponentsContainer } from "@web/ui/main_components_container";
import { ActionContainer } from "@web/webclient/actions";

export class SubcontractingPortalWebClient extends Component {
    static components = { ActionContainer, MainComponentsContainer };
    static template = "mrp_subcontracting.SubcontractingPortalWebClient";
    static props = {};
    props = useProps(this.constructor.props);
    setup() {
        window.parent.document.body.style.margin = "0";
        this.actionService = useService("action");
        provideDebugContext({ categories: ["default"] });
        useLayoutEffect(
            () => {
                this._showView();
            },
            () => [],
        );
        useListener(window, "click", this.onGlobalClick.bind(this), { capture: true });
    }

    async _showView() {
        const { action_name, picking_id } = session;
        await this.actionService.doAction(action_name, {
            props: {
                resId: picking_id,
                preventEdit: true,
                preventCreate: true,
            },
            additionalContext: {
                no_breadcrumbs: true,
            },
        });
    }

    /** @param {MouseEvent} ev */
    onGlobalClick(ev) {
        if (
            ev.ctrlKey &&
            ((ev.target instanceof HTMLAnchorElement && ev.target.href) ||
                (ev.target instanceof HTMLElement &&
                    ev.target.closest("a[href]:not([href=''])")))
        ) {
            ev.stopImmediatePropagation();
            return;
        }
    }
}
