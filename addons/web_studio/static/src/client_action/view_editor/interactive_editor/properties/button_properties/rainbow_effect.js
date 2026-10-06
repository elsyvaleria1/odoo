/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { FileInput } from "@web/components/file_input";
import { SelectMenu } from "@web/components/select_menu";
import { evaluateExpr } from "@web/core/py_js/py";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { Property } from "@web_studio/client_action/view_editor/property/property";

export class RainbowEffect extends Component {
    static template = "web_studio.ViewEditorSidebar.RainbowEffect";
    static props = { effect: t.any().optional(), onChange: t.function() };
    static components = {
        FileInput,
        SelectMenu,
        Property,
    };
    props = useProps(this.constructor.props);
    setup() {
        this.user = user;
    }
    get choices() {
        return [
            { label: _t("Fast"), value: "fast" },
            { label: _t("Medium"), value: "medium" },
            { label: _t("Slow"), value: "slow" },
            { label: _t("None"), value: "no" },
        ];
    }
    get rainbowEffect() {
        const effect = this.props.effect;
        if (effect === undefined) {
            return null;
        }
        if (effect === "True") {
            return {};
        }
        return evaluateExpr(effect);
    }
    onRainbowEffectChange(name, value) {
        const effect = this.rainbowEffect;
        if (!value || !value.length) {
            delete effect[name];
        } else {
            effect[name] = value;
        }
        this.props.onChange(effect, "effect");
    }
    toggleRainbowMan() {
        const effect = this.rainbowEffect;
        const newValue = effect ? "False" : "{}";
        this.props.onChange(newValue, "effect");
    }
}
