/** @odoo-module native */
import { Component, proxy, t, useListener, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { user } from "@web/core/user";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import {
    MenuCreator,
    MenuCreatorModel,
} from "@web_studio/client_action/menu_creator/menu_creator";
import { ModelConfigurator } from "@web_studio/client_action/model_configurator/model_configurator";

import { DEFAULT_ICON, IconCreator } from "../icon_creator/icon_creator.js";

class AppCreatorState {
    /**
     * @param {Function} onFinished
     */
    constructor({ onFinished }) {
        this._onFinished = onFinished;
        this.step = "welcome";

        this.fieldsValidators = {
            appName: () => !!this.data.appName,
            menu: (_this) => _this.menuCreatorModel.isValid,
        };
        this.menuCreatorModel = proxy(new MenuCreatorModel());

        this.data = {
            appName: "",
            iconData: DEFAULT_ICON,
            menu: this.menuCreatorModel.data,
            modelOptions: [],
        };

        this._steps = {
            welcome: {
                next: () => "app",
            },
            app: {
                previous: "welcome",
                next: () => "model",
                fields: ["appName"],
            },
            model: {
                previous: "app",
                next: (data) =>
                    data.menu.modelChoice === "new" ? "model_configuration" : "",
                fields: ["menu"],
            },
            model_configuration: {
                previous: "model",
            },
        };
    }

    get step() {
        return this._step;
    }

    set step(step) {
        this._step = step;
        this.showValidation = false;
    }

    get nextStep() {
        return this._stepInvalidFields.length ? false : this._next;
    }

    get hasPrevious() {
        return "previous" in this._currentStep;
    }

    isFieldValid(fieldName) {
        return this.showValidation ? this.fieldsValidators[fieldName](this) : true;
    }

    next() {
        this.showValidation = true;
        const invalidFields = this._stepInvalidFields;
        if (invalidFields.length) {
            return;
        }
        const next = this._next;
        if (next) {
            this.step = next;
        } else {
            return this._onFinished();
        }
    }

    previous() {
        if (this._currentStep.previous) {
            this.step = this._currentStep.previous;
        }
    }

    get _currentStep() {
        return this._steps[this._step];
    }

    get _next() {
        return this._currentStep.next ? this._currentStep.next(this.data) : "";
    }

    get _stepInvalidFields() {
        return (this._currentStep.fields || []).filter(
            (fName) => !this.fieldsValidators[fName](this),
        );
    }
}

export class AppCreator extends Component {
    static template = "web_studio.AppCreator";
    static components = { IconCreator, ModelConfigurator, MenuCreator };
    static props = { onNewAppCreated: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy(
            new AppCreatorState({
                onFinished: this.createNewApp.bind(this),
            }),
        );

        this.uiService = useService("ui");

        this.autofocusRef = elementRef();
        useAutofocus({ ref: this.autofocusRef });
        useListener(window, "keydown", this.onKeydown.bind(this));
    }

    /**
     * @returns {Promise}
     */
    async createNewApp() {
        this.uiService.block();
        const data = this.state.data;
        const iconData = data.iconData;

        const iconValue =
            iconData.type === "custom_icon"
                ? [iconData.iconClass, iconData.color, iconData.backgroundColor]
                : iconData.uploaded_attachment_id;

        try {
            const result = await rpc("/web_studio/create_new_app", {
                app_name: data.appName,
                menu_name: data.menu.menuName,
                model_choice: data.menu.modelChoice,
                model_id:
                    data.menu.modelChoice && data.menu.modelId && data.menu.modelId[0],
                model_options: data.modelOptions,
                icon: iconValue,
                context: user.context,
            });
            await this.props.onNewAppCreated(result);
        } finally {
            this.uiService.unblock();
        }
    }

    /**
     * @param {KeyboardEvent} ev
     */
    onKeydown(ev) {
        if (
            ev.key === "Enter" &&
            !(
                ev.target.classList &&
                ev.target.classList.contains("o_web_studio_app_creator_previous")
            )
        ) {
            ev.preventDefault();
            this.state.next();
        }
    }

    /** @param {Object} options */
    onConfirmOptions(options) {
        this.state.data.modelOptions = options;
        return this.state.next();
    }
}
