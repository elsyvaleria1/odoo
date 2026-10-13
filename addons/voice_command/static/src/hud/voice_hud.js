// @ts-check
/** @odoo-module native */

import { Component, proxy, useProps } from "@odoo/owl";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { mainComponentEntry } from "@web/ui/main_components_container";

const EXAMPLES_PER_KIND = 3;

export class VoiceHud extends Component {
    static template = "voice_command.VoiceHud";
    static props = null;
    props = useProps(this.constructor.props);

    setup() {
        this.voice = /** @type {import("../voice_service.js").VoiceService} */ (
            useService("voice")
        );
        this.state = proxy(this.voice.state);
        useHotkey("enter", () => this.voice.confirm(), {
            global: true,
            bypassEditableProtection: true,
            isAvailable: () => Boolean(this.state.pending),
        });
        useHotkey("escape", () => this.voice.close(), {
            global: true,
            isAvailable: () => this.state.open,
        });
    }

    /** @returns {string} */
    get heard() {
        if (this.state.interim) {
            return this.state.interim;
        }
        if (this.state.heard) {
            return this.state.heard;
        }
        return this.state.listening ? _t("Listening…") : _t("Say or type a command");
    }

    /** @returns {string} */
    get correctionText() {
        const { as, heard } = this.state.correction || { as: "", heard: "" };
        return _t("Understood “%(as)s” (heard “%(heard)s”)", { as, heard });
    }

    /** @returns {string[]} */
    get examples() {
        const vocabulary = this.voice.vocabulary();
        const view = vocabulary.view;
        const take = (/** @type {string[]} */ list) => list.slice(0, EXAMPLES_PER_KIND);
        /** @type {string[]} */
        const examples = [...(this.voice.screens.current?.examples?.() || [])];
        if (view?.form) {
            examples.push(...take(view.form.fields.map((f) => _t("%s …", f.label))));
            examples.push(
                ...take(view.form.buttons.map((b) => b.spoken?.[0] || b.label)),
            );
            examples.push(
                _t("save"),
                _t("discard changes"),
                _t("new record"),
                _t("next"),
            );
        } else if (view) {
            examples.push(...take(view.filters.map((f) => f.label)));
            examples.push(
                ...take(view.groupBys.map((g) => _t("group by %s", g.label))),
            );
            if (view.groupBys.filter((g) => g.isDate).length === 1) {
                examples.push(_t("group by month"));
            }
            examples.push(
                ...take(view.dateFilters.map(() => _t("last month"))).slice(0, 1),
            );
            examples.push(
                ...view.viewTypes
                    .filter((t) => t !== view.viewType)
                    .slice(0, 1)
                    .map((t) => _t("%s view", t)),
            );
        }
        const apps = vocabulary.menus.filter((term) => term.isApp).slice(0, 2);
        examples.push(
            ...apps.map((term) => _t("open %s", term.label)),
            _t("home"),
            _t("show numbers"),
            _t("undo"),
        );
        return examples;
    }

    close() {
        this.voice.close();
    }
}

registry
    .category("main_components")
    .add("voice_command.VoiceHud", mainComponentEntry(VoiceHud));
