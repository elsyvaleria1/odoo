/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useOwnedDialogs, useService, useServices } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

import { ModelConfiguratorDialog } from "../../model_configurator/model_configurator.js";
import { useDialogConfirmation } from "../../utils.js";

class SimpleNewModelDialog extends Component {
    static template = "web_studio.SimpleNewModelDialog";
    static components = { Dialog };
    static props = { close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.appServices = useServices();
        this.addDialog = useOwnedDialogs();
        this.menus = useService("menu");
        this.action = useService("action");
        this.studio = useService("studio");
        this.state = proxy({ modelName: "", showValidation: false });
        const { confirm, cancel } = useDialogConfirmation({
            confirm: async (data) => {
                const { menu_id, action_id } = await rpc(
                    "/web_studio/create_new_menu",
                    {
                        menu_name: this.state.modelName,
                        model_id: false,
                        model_choice: "new",
                        model_options: data.modelOptions,
                        parent_menu_id: this.menus.getCurrentApp().id,
                        context: user.context,
                    },
                );
                await this.appServices.menu.reload();
                const action = await this.action.loadAction(action_id);
                this.menus.setCurrentMenu(menu_id);
                this.studio.setParams({ action, viewType: "form" });
            },
        });

        this._confirm = confirm;
        this._cancel = cancel;
    }

    confirm(data = {}) {
        this.props.close();
        return this._confirm(data);
    }

    onConfigureModel() {
        if (!this.state.modelName) {
            this.state.showValidation = true;
            return;
        }

        this.addDialog(ModelConfiguratorDialog, {
            confirmLabel: _t("Create Model"),
            confirm: (data) => {
                this.confirm({ modelOptions: data });
            },
        });
    }
}

export class NewModelItem extends Component {
    static props = {};
    static template = "web_studio.NewModelItem";
    props = useProps(this.constructor.props);

    setup() {
        this.addDialog = useOwnedDialogs();
        this.menus = useService("menu");
        this.studio = useService("studio");
        this.action = useService("action");
    }

    onClick(ev) {
        ev.preventDefault();
        this.addDialog(SimpleNewModelDialog);
    }
}
