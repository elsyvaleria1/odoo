// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { isMacOS } from "@web/core/browser/feature_detection";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { registry } from "@web/core/registry";

const commandSetupRegistry = registry.category("command_setup");

/** @type {Record<string, any>} */
export const COMMAND_ITEM_PROPS = {
    slots: t.object().optional(),
    name: t.string().optional(),
    searchValue: t.string().optional(),
    executeCommand: t.function().optional(),
};

export class DefaultCommandItem extends Component {
    static template = "web.DefaultCommandItem";
    static props = { ...COMMAND_ITEM_PROPS };
    props = useProps(this.constructor.props);
}

export class DefaultFooter extends Component {
    static template = "web.DefaultFooter";
    static props = { switchNamespace: t.function() };
    props = useProps(this.constructor.props);
    /** @returns {{ namespace: string, name: any }[]} */
    get elements() {
        return commandSetupRegistry
            .getEntries()
            .map(([namespace, { name }]) => ({ namespace, name }))
            .filter((el) => el.name);
    }

    onClick(/** @type {string} */ namespace) {
        this.props.switchNamespace(namespace);
    }
}

export class HotkeyCommandItem extends Component {
    static template = "web.HotkeyCommandItem";
    static props = {
        ...COMMAND_ITEM_PROPS,
        hotkey: t.string(),
        hotkeyOptions: t.object().optional(),
    };
    props = useProps(this.constructor.props);
    setup() {
        useHotkey(
            this.props.hotkey,
            this.props.executeCommand,
            this.props.hotkeyOptions,
        );
    }

    /** @returns {string[]} */
    get keysToPress() {
        /** @type {string[]} */
        let result = this.props.hotkey.split("+");
        if (isMacOS()) {
            result = result
                .map((x) => x.replace("control", "command"))
                .map((x) => x.replace("alt", "control"));
        }
        return result.map((key) => key.toUpperCase());
    }
}
