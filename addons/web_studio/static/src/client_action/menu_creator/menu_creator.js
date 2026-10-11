/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { RecordSelector } from "@web/components/record_selectors";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus, useOwnedDialogs } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";
import { useDialogConfirmation } from "@web_studio/client_action/utils";

import { ModelConfiguratorDialog } from "../model_configurator/model_configurator.js";

export class MenuCreatorModel {
    constructor({ allowNoModel } = {}) {
        this.data = {
            modelId: false,
            menuName: "",
            modelChoice: "new",
        };

        this.modelChoiceSelection = {
            new: _t("New Model"),
            existing: _t("Existing Model"),
        };

        if (allowNoModel) {
            this.modelChoiceSelection.parent = _t("Parent Menu");
        }
    }

    isGroupableField(fieldName) {
        if (fieldName === "menuName") {
            return !!this.data.menuName;
        } else if (fieldName === "modelId") {
            return this.data.modelChoice === "existing" ? !!this.data.modelId : true;
        }
    }

    get isValid() {
        return ["menuName", "modelId"].every((fName) => this.isGroupableField(fName));
    }
}

export class MenuCreator extends Component {
    static template = "web_studio.MenuCreator";
    static components = { RecordSelector };
    static props = {
        menuCreatorModel: t.object(),
        showValidation: t.boolean().optional(false),
    };
    props = useProps(this.constructor.props);

    get multiRecordSelectorProps() {
        return {
            resModel: "ir.model",
            resId: this.state.data.modelId && this.state.data.modelId[0],
            update: (resId) => (this.state.data.modelId = [resId]),
            domain: [
                ["transient", "=", false],
                ["abstract", "=", false],
            ],
        };
    }

    setup() {
        this.autofocusRef = elementRef();
        useAutofocus({ ref: this.autofocusRef });
        this.state = proxy(this.props.menuCreatorModel);
    }

    isValid(fieldName) {
        return this.props.showValidation
            ? this.state.isGroupableField(fieldName)
            : true;
    }
}

export class MenuCreatorDialog extends Component {
    static template = "web_studio.MenuCreatorDialog";
    static components = { Dialog, MenuCreator };
    static props = { confirm: t.function(), close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.addDialog = useOwnedDialogs();
        this.menuCreatorModel = proxy(new MenuCreatorModel({ allowNoModel: true }));
        this.state = proxy({ showValidation: false });
        const { confirm, cancel } = useDialogConfirmation({
            confirm: async (data = {}) => {
                if (!this.menuCreatorModel.isValid) {
                    this.state.showValidation = true;
                    return false;
                }
                await this.props.confirm(data);
            },
        });
        this._confirm = confirm;
        this._cancel = cancel;
    }

    confirm(data = {}) {
        this._confirm({ ...this.menuCreatorModel.data, ...data });
    }

    onCreateNewModel() {
        if (!this.menuCreatorModel.isValid) {
            this.state.showValidation = true;
            return;
        }
        this.addDialog(ModelConfiguratorDialog, {
            confirmLabel: _t("Create Menu"),
            confirm: (data) => {
                this.confirm({ modelOptions: data });
            },
        });
    }
}
