/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { omit } from "@web/core/utils/collections/objects";
import { getGroupKey } from "@web/model/relational_model/group_key";
import { nodeAttrs } from "@web/views/ir/view_ir";
import { KANBAN_CARD_ATTRIBUTE, kanbanView } from "@web/views/kanban";
import { KanbanEditorRecord } from "@web_studio/client_action/view_editor/editors/kanban/kanban_editor_record";
import { KanbanEditorRenderer } from "@web_studio/client_action/view_editor/editors/kanban/kanban_editor_renderer";
import { makeModelErrorResilient } from "@web_studio/client_action/view_editor/editors/utils";

import { getStudioNoFetchFields, useModelConfigFetchInvisible } from "../utils.js";
import { computeIRXpath } from "../xml_utils.js";
import { KanbanEditorCompiler } from "./kanban_editor_compiler.js";
import { KanbanEditorSidebar } from "./kanban_editor_sidebar/kanban_editor_sidebar.js";

function parseStudioGroups(node) {
    return nodeAttrs(node).studio_groups;
}

class EditorArchParser extends kanbanView.ArchParser {
    parse(arch, models, modelName) {
        const parsed = super.parse(...arguments);
        const noFetch = getStudioNoFetchFields(parsed.fieldNodes);
        parsed.fieldNodes = omit(parsed.fieldNodes, ...noFetch.fieldNodes);
        return parsed;
    }

    // the kanban parser walks the view IR; `this.parents` is its tree
    processButton(node) {
        const parsed = super.processButton(node);
        parsed.studioXpath = computeIRXpath(node, this.parents, ["kanban"]);
        parsed.studio_groups = parseStudioGroups(node);
        return parsed;
    }
}
class OneRecordModel extends kanbanView.Model {
    async load() {
        this.progressAttributes = false;
        await super.load(...arguments);
        let list = this.root;
        let hasRecords;
        const isGrouped = list.isGrouped;
        if (!isGrouped) {
            hasRecords = list.records.length;
        } else {
            hasRecords = list.groups.some((g) => g.list.records.length);
        }
        if (!hasRecords) {
            if (isGrouped) {
                const commonConfig = {
                    resModel: list.config.resModel,
                    fields: list.config.fields,
                    activeFields: list.config.activeFields,
                    groupByFieldName: list.groupByField.name,
                    context: list.context,
                    list: {
                        resModel: list.config.resModel,
                        fields: list.config.fields,
                        activeFields: list.config.activeFields,
                        groupBy: [],
                        context: list.context,
                    },
                };

                const data = {
                    count: 0,
                    length: 0,
                    records: [],
                    __domain: [],
                    value: "fake",
                    displayName: "Fake Group",
                    groups: [
                        {
                            display_name: false,
                            count: 0,
                        },
                    ],
                };

                // the model keys a group's config by getGroupKey(value)
                // (e56e1adb1ace), not by the raw value
                list.config.groups[getGroupKey(data.value)] = commonConfig;

                const group = list._createGroupDatapoint(data);
                list.groups.push(group);
                list = group.list;
            }
            await list.addNewRecord();
        }
    }
}

class KanbanEditorController extends kanbanView.Controller {
    setup() {
        super.setup();
        useModelConfigFetchInvisible(this.model);
    }

    get modelParams() {
        const params = super.modelParams;
        params.groupsLimit = 1;
        return params;
    }
}

function isValidKanbanHook({ hook, element }) {
    const draggingStructure = element.dataset.structure;
    return hook.dataset.structures.split(",").includes(draggingStructure);
}

async function addKanbanViewStructure(structure) {
    switch (structure) {
        case "aside": {
            if (!this.viewEditorModel.xmlDoc.querySelector("main")) {
                this.viewEditorModel.pushOperation({
                    type: "kanban_wrap_main",
                    wrap_type: "aside",
                });
            }
            return {
                node: {
                    tag: "aside",
                    attrs: {
                        class: "col-2",
                    },
                },
                target: {
                    tag: "main",
                },
            };
        }
        case "footer": {
            if (!this.viewEditorModel.xmlDoc.querySelector("main")) {
                this.viewEditorModel.pushOperation({
                    type: "kanban_wrap_main",
                    wrap_type: "footer",
                });
            }
            return {
                node: {
                    tag: "footer",
                },
                target: {
                    tag: "main",
                },
                position: "inside",
            };
        }
        case "t": {
            return { type: "kanban_menu" };
        }
        case "ribbon": {
            const cardTemplate = this.viewEditorModel.xmlDoc.querySelector(
                `[t-name="${KANBAN_CARD_ATTRIBUTE}"]`,
            );
            let ribbonTarget;
            if (cardTemplate.children.length) {
                ribbonTarget = [
                    `//kanban//t[@t-name="${KANBAN_CARD_ATTRIBUTE}"]/*[1]`,
                    "before",
                ];
            } else {
                ribbonTarget = [
                    `//kanban//t[@t-name="${KANBAN_CARD_ATTRIBUTE}"]`,
                    "inside",
                ];
            }
            return {
                node: {
                    tag: "widget",
                    attrs: {
                        name: "web_ribbon",
                        title: "Demo",
                    },
                },

                target: this.viewEditorModel.getFullTarget(ribbonTarget[0], {
                    isXpathFullAbsolute: false,
                }),
                position: ribbonTarget[1],
            };
        }
        case "kanban_colorpicker": {
            if (!this.viewEditorModel.xmlDoc.querySelector("t[t-name=menu]")) {
                this.viewEditorModel.pushOperation({
                    type: "kanban_menu",
                });
            }
            return {
                type: "kanban_colorpicker",
                view_id: this.viewEditorModel.mainView.id,
            };
        }
    }
}

function prepareForKanbanDrag({ element, ref }) {
    const hooksToStylize = [...ref.el.querySelectorAll(".o_web_studio_hook")].filter(
        (e) => e.dataset.structures?.split(",").includes(element.dataset.structure),
    );
    hooksToStylize.forEach((e) => e.classList.add("o_web_studio_hook_visible"));
    return () => {
        ref.el
            .querySelectorAll(".o_web_studio_hook_visible")
            .forEach((el) => el.classList.remove("o_web_studio_hook_visible"));
    };
}

const kanbanEditor = {
    ...kanbanView,
    Compiler: KanbanEditorCompiler,
    Controller: KanbanEditorController,
    ArchParser: EditorArchParser,
    Renderer: KanbanEditorRenderer,
    Record: KanbanEditorRecord,
    Model: OneRecordModel,
    Sidebar: KanbanEditorSidebar,
    isValidHook: isValidKanbanHook,
    addViewStructure: addKanbanViewStructure,
    prepareForDrag: prepareForKanbanDrag,
    props(genericProps, editor, config) {
        const props = kanbanView.props(genericProps, editor, config);
        props.Model = makeModelErrorResilient(
            OneRecordModel,
            props.archInfo.activeActions,
        );
        props.limit = 1;
        props.Renderer = KanbanEditorRenderer;
        return props;
    },
};

// The object itself, not a copy: the hooks assigned below register on it.
Object.assign(kanbanEditor, {
    label: _t("Kanban"),
    icon: "oi oi-view-kanban",
    group: "multiple",
});
registry.category("studio_editors").add("kanban", kanbanEditor);
