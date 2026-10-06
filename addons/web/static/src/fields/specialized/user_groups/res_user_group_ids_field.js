// @ts-check
/** @odoo-module native */

import { computed, toRaw } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { x2ManyCommands } from "@web/core/network/commands";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { deepCopy } from "@web/core/utils/collections/objects";
import { parseXML } from "@web/core/utils/dom/xml";
import { escape } from "@web/core/utils/format/strings";
import { provideChildWebContext } from "@web/core/web_context_hooks";
import { registerField } from "@web/fields/_registry";
import { FieldComponent } from "@web/fields/field_component";
import { standardFieldProps } from "@web/fields/standard_field_props";
import { Record as RecordComponent } from "@web/model/record";

const viewRegistry = registry.category("views");

/**
 * @typedef {{
 * id: string | number,
 * name: string,
 * privilege_ids?: Array<string | number>,
 * privileges: Privilege[],
 * }} PrivilegeCategory
 * @typedef {{ id: string | number } & Record<string, any>} Privilege
 * @typedef {{
 * name: string,
 * id: number,
 * privilege_id: number | false,
 * comment: string | false,
 * impliedByIds: number[],
 * implyIds: number[],
 * selected: boolean,
 * disjointIds: number[],
 * }} GroupState
 * @typedef {{
 * groups: Record<string, GroupState>,
 * selections: Record<string, Array<[number | false, string]>>,
 * values: Record<string, number | boolean>,
 * shadowedGroupIds: number[],
 * }} RenderState
 */

const log = makeLogger("web.fields.res_user_group_ids");

/**
 * @param {Array<number | string>} previous
 * @param {Array<number | string>} next
 * @returns {boolean}
 */
function sameIds(previous, next) {
    const same =
        previous.length === next.length &&
        previous.every((id, index) => id === next[index]);
    log.logic("selectedIds", () => ({
        same,
        previous: previous.join(","),
        next: next.join(","),
    }));
    return same;
}

class ResUserGroupIdsField extends FieldComponent {
    static template = "web.ResUserGroupIdsField";
    static get components() {
        return {
            Record: RecordComponent,
            FormRenderer: viewRegistry.get("form").Renderer,
        };
    }
    static props = { ...standardFieldProps };

    /** @type {Record<string, any>} */
    hierarchyGroups;

    /** @type {PrivilegeCategory[]} */
    categories;

    /** @type {PrivilegeCategory} */
    extraCategory;

    /** @type {Record<string, any>} */
    _fields;

    /** @type {Record<string, any>} */
    fields;

    /** @type {Record<string, any>} */
    info;

    /** @type {RenderState | undefined} */
    appliedRenderState;

    setup() {
        const { groups, privileges, categories } = deepCopy(
            toRaw(this.props.record.data.view_group_hierarchy),
        );
        this.hierarchyGroups = groups;
        this.categories = /** @type {PrivilegeCategory[]} */ (
            this.getCategories(categories, privileges)
        );
        this.extraCategory = this.getExtraCategory(groups);

        const booleanFieldToGroupId = this.getFields(privileges, groups);
        this.fields = deepCopy(this._fields);
        this.archInfo = this.getArch();

        this.info = { booleanFieldToGroupId, groups: {}, privileges };
        provideChildWebContext({ resUserGroupsInfo: this.info });
        const selectedIds = computed(
            () => [...this.props.record.data[this.props.name].currentIds],
            { equals: sameIds },
        );
        this.renderState = computed(() =>
            this.deriveRenderState(new Set(selectedIds())),
        );

        this.hooks = {
            lifecycle: {
                onRecordChanged: this.onRecordChanged.bind(this),
            },
        };
    }

    /**
     * @param {Array<{ id: string|number, name: string, privilege_ids: Array<string|number> }>} categories
     * @param {Object<string, any>} privileges
     * @returns {Array<Object<string, any>>}
     */
    getCategories(categories, privileges) {
        const orphans = Object.values(privileges)
            .filter((privilege) => !privilege.category_id)
            .sort((p1, p2) => p1.sequence - p2.sequence);
        if (orphans.length) {
            categories.push({
                id: "other",
                name: _t("Other"),
                privilege_ids: orphans.map((privilege) => privilege.id),
            });
        }
        return categories;
    }

    /**
     * @param {Object<string, any>} groups
     * @returns {PrivilegeCategory}
     */
    getExtraCategory(groups) {
        return {
            id: "extra",
            name: _t("Extra Rights"),
            privileges: Object.values(groups)
                .filter((group) => !group.privilege_id)
                .map((group) => {
                    const privilege = {
                        description: group.comment,
                        groupId: group.id,
                        id: `group_${group.id}`,
                        name: group.name,
                    };
                    privilege.groupFieldName = this.getFieldName(privilege);
                    return privilege;
                })
                .sort((p1, p2) => p1.name.localeCompare(p2.name)),
        };
    }

    /**
     * @param {Object<string, any>} privileges
     * @param {Object<string, any>} groups
     * @returns {Object<string, number>}
     */
    getFields(privileges, groups) {
        this._fields = {};
        /** @type {Record<string, number>} */
        const booleanFieldToGroupId = {};
        for (const category of this.categories) {
            category.privileges = [];
            for (const privilegeId of category.privilege_ids) {
                const privilege = privileges[privilegeId];
                category.privileges.push(privilege);
                this._fields[this.getFieldName(privilege)] = {
                    help: this.getPrivilegeHelp(privilege, groups),
                    selection: this.getPrivilegeSelection(privilege, groups),
                    string: privilege.name,
                    type: "selection",
                };
            }
        }
        for (const privilege of this.extraCategory.privileges) {
            this._fields[privilege.groupFieldName] = {
                help: privilege.description,
                string: privilege.name,
                type: "boolean",
            };
            booleanFieldToGroupId[privilege.groupFieldName] = privilege.groupId;
        }
        return booleanFieldToGroupId;
    }

    /**
     * @param {Object<string, any>} privilege
     * @param {Object<string, any>} groups
     * @returns {string}
     */
    getPrivilegeHelp(privilege, groups) {
        const lines = privilege.description ? [privilege.description] : [];
        for (const gid of privilege.group_ids) {
            if (groups[gid].comment) {
                lines.push(`- ${groups[gid].name}: ${groups[gid].comment}`);
            }
        }
        return lines.join("\n");
    }

    /**
     * @param {Object<string, any>} privilege
     * @param {Object<string, any>} groups
     * @returns {Array<[number|false, string]>}
     */
    getPrivilegeSelection(privilege, groups) {
        const selection = privilege.group_ids.map((gId) => [gId, groups[gId].name]);
        selection.unshift([false, privilege.placeholder || ""]);
        return selection;
    }

    /** @returns {Object<string, any>} */
    getArch() {
        const arch = `
            <t>
                <group>
                    ${this.categories.map((category) => this.getCategoryArch(category)).join("")}
                </group>
                ${odoo.debug ? this.getExtraGroupsArch() : ""}
            </t>`;
        const { ArchParser } = viewRegistry.get("form");
        return new ArchParser().parse(
            parseXML(arch),
            { main: { fields: this._fields } },
            "main",
        );
    }

    /** @returns {Record<string, any>} */
    get values() {
        return this.applyRenderState(this.renderState()).values;
    }

    /**
     * @param {RenderState} state
     * @returns {RenderState}
     */
    applyRenderState(state) {
        if (state === this.appliedRenderState) {
            return state;
        }
        log.logic("applyRenderState", () => ({
            groups: Object.keys(state.groups).length,
            narrowed: Object.keys(state.selections)
                .filter(
                    (fieldName) =>
                        state.selections[fieldName] !==
                        this._fields[fieldName].selection,
                )
                .join(","),
            shadowed: state.shadowedGroupIds.join(","),
        }));
        Object.assign(this.info.groups, state.groups);
        for (const [fieldName, selection] of Object.entries(state.selections)) {
            this.fields[fieldName].selection = selection;
        }
        this.appliedRenderState = state;
        return state;
    }

    /**
     * @param {Set<number>} selectedIds
     * @returns {RenderState}
     */
    deriveRenderState(selectedIds) {
        log.logic("deriveRenderState", () => ({
            selected: [...selectedIds].join(","),
        }));
        const groups = this.deriveGroupStates(selectedIds);
        this.deriveDisjointIds(groups);
        const selections = this.deriveReachableSelections(groups);
        return {
            groups,
            selections,
            ...this.deriveValues(selectedIds, selections),
        };
    }

    /**
     * @param {Set<number>} selectedIds
     * @returns {Record<string, GroupState>}
     */
    deriveGroupStates(selectedIds) {
        /** @type {Record<string, GroupState>} */
        const groups = {};
        for (const group of Object.values(this.hierarchyGroups)) {
            const selected = selectedIds.has(group.id);
            groups[group.id] = {
                name: group.name,
                id: group.id,
                privilege_id: group.privilege_id,
                comment: group.comment,
                impliedByIds: group.all_implied_by_ids.filter(
                    (/** @type {number} */ gid) =>
                        gid !== group.id && selectedIds.has(gid),
                ),
                implyIds: selected
                    ? group.all_implied_ids.filter(
                          (/** @type {number} */ gid) => gid !== group.id,
                      )
                    : [],
                selected,
                disjointIds: [],
            };
        }
        return groups;
    }

    /** @param {Record<string, GroupState>} groups */
    deriveDisjointIds(groups) {
        for (const group of Object.values(this.hierarchyGroups)) {
            const { selected, impliedByIds } = groups[group.id];
            groups[group.id].disjointIds =
                selected || impliedByIds.length
                    ? group.disjoint_ids.filter(
                          (/** @type {number} */ gid) =>
                              groups[gid].selected || groups[gid].impliedByIds.length,
                      )
                    : [];
        }
    }

    /**
     * @param {Record<string, GroupState>} groups
     * @returns {Record<string, Array<[number | false, string]>>}
     */
    deriveReachableSelections(groups) {
        /** @type {Record<string, Array<[number | false, string]>>} */
        const selections = {};
        for (const fieldName of Object.keys(this.fields)) {
            if (this.fields[fieldName].type !== "selection") {
                continue;
            }
            const options = this._fields[fieldName].selection;
            selections[fieldName] = options;
            for (let i = options.length - 1; i > 0; i--) {
                const group = groups[options[i][0]];
                const isImplied = group.impliedByIds.some(
                    (gid) => groups[gid].privilege_id !== group.privilege_id,
                );
                if (isImplied) {
                    selections[fieldName] = options.slice(i);
                    break;
                }
            }
        }
        return selections;
    }

    /**
     * @param {Set<number>} selectedIds
     * @param {Record<string, Array<[number | false, string]>>} selections
     * @returns {{ values: Record<string, number | boolean>, shadowedGroupIds: number[] }}
     */
    deriveValues(selectedIds, selections) {
        /** @type {Record<string, number | boolean>} */
        const values = {};
        /** @type {number[]} */
        const shadowedGroupIds = [];
        for (const category of this.categories) {
            for (const privilege of category.privileges) {
                let groupId =
                    privilege.group_ids.findLast((/** @type {number} */ gId) =>
                        selectedIds.has(gId),
                    ) || false;
                const fieldName = this.getFieldName(privilege);
                if (
                    groupId &&
                    !selections[fieldName].some((option) => option[0] === groupId)
                ) {
                    shadowedGroupIds.push(groupId);
                    groupId = false;
                }
                values[fieldName] = groupId;
            }
        }
        for (const privilege of this.extraCategory.privileges) {
            values[this.getFieldName(privilege)] = selectedIds.has(privilege.groupId);
        }
        return { values, shadowedGroupIds };
    }

    /** @returns {string} */
    getExtraGroupsArch() {
        return `
            <group string="${escape(this.extraCategory.name)}" class="o_extra_rights_group">
                <group>
                    ${this.extraCategory.privileges
                        .filter((cat, index) => index % 2 === 0)
                        .map((privilege) => this.getPrivilegeArch(privilege))
                        .join("")}
                </group>
                <group>
                    ${this.extraCategory.privileges
                        .filter((cat, index) => index % 2 === 1)
                        .map((privilege) => this.getPrivilegeArch(privilege))
                        .join("")}
                </group>
            </group>`;
    }

    /**
     * @param {Privilege} privilege
     * @returns {string}
     */
    getFieldName(privilege) {
        return `field_${privilege.id}`;
    }

    /**
     * @param {Privilege} privilege
     * @returns {string}
     */
    getPrivilegeArch(privilege) {
        const fieldName = this.getFieldName(privilege);
        return `<field name="${escape(fieldName)}" widget="res_user_group_ids_privilege"/>`;
    }

    /**
     * @param {PrivilegeCategory} category
     * @returns {string}
     */
    getCategoryArch(category) {
        return `
            <group string="${escape(category.name)}">
                ${category.privileges.map((privilege) => this.getPrivilegeArch(privilege)).join("")}
            </group>`;
    }

    /**
     * @param {unknown} _
     * @param {{[key: string]: number | boolean}} values
     * @returns {Promise<void>}
     */
    onRecordChanged(_, values) {
        let selectedGroupIds = Object.entries(values)
            .filter(
                ([fieldName, gid]) =>
                    this.fields[fieldName].type === "selection" && gid,
            )
            .map(([_, gid]) => gid);
        const { groups, privileges } = this.info;
        const shadowedGroupIds = this.applyRenderState(
            this.renderState(),
        ).shadowedGroupIds.filter(
            (gid) => !values[this.getFieldName(privileges[groups[gid].privilege_id])],
        );
        selectedGroupIds = [...selectedGroupIds, ...shadowedGroupIds];
        for (const privilege of this.extraCategory.privileges) {
            if (values[privilege.groupFieldName]) {
                selectedGroupIds.push(privilege.groupId);
            }
        }
        return this.field.update([x2ManyCommands.set(selectedGroupIds)]);
    }
}

/** @type {import("registries").FieldsRegistryItemShape} */
const resUserGroupIdsField = {
    component: ResUserGroupIdsField,
    displayName: _t("User Groups"),
    fieldDependencies: [{ name: "view_group_hierarchy", type: "json", readonly: true }],
    additionalClasses: ["w-100"],
    supportedTypes: ["many2many"],
};

registerField("res_user_group_ids", resUserGroupIdsField);
