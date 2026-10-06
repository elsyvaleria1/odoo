// @ts-check
/** @odoo-module native */

import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { viewModelOf } from "@web/model/model";
import { COG_GROUP, isActWindowView } from "@web/search/cog_menu/cog_menu_group";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";

export class ExplainAccessCogMenu extends Component {
    static template = "web.ExplainAccessCogMenu";
    static components = { CogMenuItem };
    static props = {};
    props = useProps(this.constructor.props);

    /** @type {import("services").ServiceFactories["action"]} */
    action;

    setup() {
        this.action = useService("action");
    }

    async explain() {
        const { resModel, resId } = viewModelOf(this).root;
        await this.action.doAction("base.action_ir_access_explain", {
            additionalContext: { explain_model: resModel, explain_id: resId },
        });
    }
}

registry.category("cogMenu").add(
    "explain-access",
    /** @type {any} */ ({
        Component: ExplainAccessCogMenu,
        groupNumber: COG_GROUP.INTEGRATE,
        /** @param {any} scope */
        isDisplayed: (scope) =>
            isActWindowView(scope, ["form"]) &&
            user.isInternalUser &&
            Boolean(scope.model?.root?.resId),
    }),
    { sequence: 90 },
);
