/** @odoo-module native */
import { getRandomIcon } from "@knowledge/js/knowledge_utils";
import { Component, t, useProps } from "@odoo/owl";
import { useEmojiPicker } from "@web/components/emoji_picker";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { exprToBoolean } from "@web/core/utils/format/strings";
import { standardFieldProps } from "@web/fields/standard_field_props";

export default class KnowledgeIcon extends Component {
    static template = "knowledge.KnowledgeIcon";
    static props = {
        record: t.object(),
        readonly: t.boolean(),
        iconClasses: t.string().optional(),
        allowRandomIconSelection: t.boolean().optional(),
        autoSave: t.boolean().optional(),
        fallbackDefaultIcon: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.iconRef = elementRef();
        this.emojiPicker = useEmojiPicker(this.iconRef, {
            hasRemoveFeature: true,
            onSelect: this.updateIcon.bind(this),
        });
    }

    get icon() {
        return this.props.record.data.icon || (this.props.fallbackDefaultIcon && "📄");
    }

    async selectRandomIcon() {
        this.updateIcon(await getRandomIcon());
    }

    updateIcon(icon) {
        this.props.record.update({ icon });
        if (this.props.autoSave) {
            this.props.record.save();
        }
    }
}

class KnowledgeIconField extends KnowledgeIcon {
    static props = {
        ...standardFieldProps,
        allowRandomIconSelection: t.boolean(),
        autoSave: t.boolean(),
    };
}

registry.category("fields").add("knowledge_icon", {
    component: KnowledgeIconField,
    extractProps({ attrs, viewType }, dynamicInfo) {
        return {
            autoSave: viewType === "kanban",
            readonly: dynamicInfo.readonly,
            allowRandomIconSelection: exprToBoolean(attrs.allow_random_icon_selection),
        };
    },
});
