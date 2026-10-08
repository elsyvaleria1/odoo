/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

import { ProjectTemplateButtons } from "./project_template_buttons.js";

export class TemplateDropdown extends Component {
    static template = "project.TemplateDropdown";
    static components = {
        Dropdown,
        DropdownItem,
        ProjectTemplateButtons,
    };

    static props = {
        hotkey: t.string().optional("c"),
        newButtonClasses: t.string(),
        onCreate: t.function(),
        context: t.object(),
        getAdditionalContext: t.function().optional(),
        isDisabled: t.boolean().optional(false),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = proxy({ templates: [] });
        this.isProjectManager = false;
        onWillStart(this.onWillStart);
    }

    /** @returns {{ id: number, name: string }[]} */
    get templates() {
        return this.state.templates;
    }

    /** @returns {string} */
    get templateResModel() {
        throw new Error("TemplateDropdown subclasses define templateResModel");
    }

    /** @returns {string} */
    get templateItemClass() {
        return "";
    }

    /** @returns {string} */
    get newRecordLabel() {
        return "";
    }

    /** @returns {string} */
    get templatesHeader() {
        return "";
    }

    get templateItemClasses() {
        return `btn btn-link o-dropdown-item-indent ${this.templateItemClass} d-flex align-items-center${
            this.isProjectManager ? " pe-0" : ""
        }`;
    }

    async onWillStart() {
        await Promise.all([
            user
                .hasGroup("project.group_project_manager")
                .then((isProjectManager) => (this.isProjectManager = isProjectManager)),
            this.fetchTemplates(this.props),
        ]);
    }

    async fetchTemplates() {}

    /**
     * @param {(templates: any[]) => void} onChange
     */
    cachedOrm(onChange) {
        return this.orm.cache({
            type: "disk",
            update: "always",
            callback: (result, hasChanged) => {
                if (hasChanged) {
                    onChange(result);
                }
            },
        });
    }

    /** @returns {Record<string, any>} */
    getCreateContext() {
        return {
            ...this.props.context,
            ...this.props.getAdditionalContext?.(),
        };
    }

    async createFromTemplate() {}
}
