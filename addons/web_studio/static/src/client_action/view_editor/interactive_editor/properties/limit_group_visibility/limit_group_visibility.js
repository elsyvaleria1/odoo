/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { MultiRecordSelector } from "@web/components/record_selectors";
import { useEditNodeAttributes } from "@web_studio/client_action/view_editor/view_editor_model";

export class LimitGroupVisibility extends Component {
    static template = "web_studio.ViewEditor.LimitGroupVisibility";
    static components = {
        MultiRecordSelector,
    };
    static props = { node: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.editNodeAttributes = useEditNodeAttributes();
    }

    get studioGroups() {
        const groups = JSON.parse(this.props.node.attrs.studio_groups || "[]");
        return {
            current: groups.map((group) => group.id),
            allow: groups.filter((group) => !group.forbid).map((group) => group.id),
            forbid: groups.filter((group) => group.forbid).map((group) => group.id),
        };
    }

    get allowGroups() {
        return this.studioGroups.allow;
    }

    get forbidGroups() {
        return this.studioGroups.forbid;
    }

    get currentGroups() {
        return this.studioGroups.current;
    }

    handleNodeGroupsChange(allow, forbid) {
        allow = new Set(allow || this.allowGroups);
        forbid = new Set(forbid || this.forbidGroups);
        if (!allow.isDisjointFrom(forbid)) {
            throw new Error("Cannot allow and forbid at the same time");
        }
        const resIds = [];
        for (const g of allow) {
            resIds.push(g);
        }
        for (const g of forbid) {
            resIds.push(`!${g}`);
        }
        return this.editNodeAttributes({ groups: resIds });
    }

    onChangeAttribute(value, name) {
        return this.editNodeAttributes({ [name]: value });
    }

    get allowGroupsProps() {
        return {
            resModel: "res.groups",
            domain: [["id", "not in", this.currentGroups]],
            resIds: this.allowGroups,
            update: (resIds) => this.handleNodeGroupsChange(resIds, null),
        };
    }

    get forbidGroupsProps() {
        return {
            resModel: "res.groups",
            domain: [["id", "not in", this.currentGroups]],
            resIds: this.forbidGroups,
            update: (resIds) => this.handleNodeGroupsChange(null, resIds),
        };
    }
}
