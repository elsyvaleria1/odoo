/** @odoo-module native */
import { Component, onMounted, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { Dialog } from "@web/ui/dialog";

export class PromptEmbeddedViewNameDialog extends Component {
    static template = "knowledge.PromptEmbeddedViewNameDialog";
    static components = { Dialog };
    static props = {
        defaultName: t.string().optional(),
        isNew: t.boolean().optional(),
        viewType: t.string(),
        save: t.function(),
        close: t.function().optional(),
    };
    props = useProps(this.constructor.props);

    /**
     * @override
     */
    setup() {
        super.setup();
        this.input = elementRef();
        onMounted(() => {
            window.setTimeout(() => {
                this.input.el?.focus(); // auto-focus
            }, 0);
        });
    }
    async save() {
        await this.props.save(this.input.el.value);
        this.props.close();
    }
    /**
     * @returns {String}
     */
    get placeholder() {
        if (this.props.viewType === "kanban") {
            return _t("e.g. Buildings");
        }
        if (this.props.viewType === "list") {
            return _t("e.g. Todos");
        }
        return "";
    }
    /**
     * @returns {String}
     */
    get title() {
        if (this.props.viewType === "list") {
            return _t("Insert a List View");
        }
        if (this.props.viewType === "kanban") {
            return _t("Insert a Kanban View");
        }
        return _t("Embed a View");
    }
    /**
     * @param {Event} event
     */
    onInputKeydown(event) {
        if (event.key === "Enter") {
            this.save();
        }
    }
}
