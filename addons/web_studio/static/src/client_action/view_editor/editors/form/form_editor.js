/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { deepCopy, omit } from "@web/core/utils/collections/objects";
import { parseXML } from "@web/core/utils/dom/xml";
import { formView } from "@web/views/form";
import { elementToIR } from "@web/views/ir/view_ir";
import { visitIR } from "@web/views/view_arch_parser";
import {
    makeModelErrorResilient,
    randomName,
} from "@web_studio/client_action/view_editor/editors/utils";

import { getStudioNoFetchFields } from "../utils.js";
import { FormEditorCompiler } from "./form_editor_compiler.js";
import { FormEditorController } from "./form_editor_controller/form_editor_controller.js";
import { FormEditorRenderer } from "./form_editor_renderer/form_editor_renderer.js";
import { FormEditorSidebar } from "./form_editor_sidebar/form_editor_sidebar.js";

class EditorArchParser extends formView.ArchParser {
    parse() {
        const archInfo = super.parse(...arguments);
        this.omitStudioNoFetchFields(archInfo);
        archInfo.disableAutofocus = true;
        return archInfo;
    }

    omitStudioNoFetchFields(archInfo) {
        const noFetch = getStudioNoFetchFields(archInfo.fieldNodes);
        archInfo.fieldNodes = omit(archInfo.fieldNodes, ...noFetch.fieldNodes);

        for (const fieldNode of Object.values(archInfo.fieldNodes)) {
            if (fieldNode.views) {
                for (const fieldArchInfo of Object.values(fieldNode.views)) {
                    this.omitStudioNoFetchFields(fieldArchInfo);
                }
            }
        }
    }
}

class Model extends formView.Model {}
Model.Record = class RecordNoEdit extends formView.Model.Record {
    get isInEdition() {
        return false;
    }
    saveLocked() {
        return true;
    }
};

export const formEditor = {
    ...formView,
    ArchParser: EditorArchParser,
    Compiler: FormEditorCompiler,
    Renderer: FormEditorRenderer,
    Controller: FormEditorController,
    props(genericProps, editor, config) {
        const { arch, ir } = genericProps;
        const pruned = deepCopy(
            ir ?? elementToIR(typeof arch === "string" ? parseXML(arch) : arch),
        );
        visitIR(pruned, (node) => {
            if (node.kind !== "field" || !node.children) {
                return;
            }
            node.children = node.children.filter(
                (child) =>
                    !["list", "form", "kanban"].includes(child.kind) ||
                    !child.attrs?.invisible,
            );
        });
        const props = formView.props({ ...genericProps, ir: pruned }, editor, config);
        props.Model = makeModelErrorResilient(Model, props.archInfo.activeActions);
        props.preventEdit = true;
        return props;
    },
    Sidebar: FormEditorSidebar,
};
Object.assign(formEditor, {
    label: _t("Form"),
    icon: "fa-solid fa-address-card",
    group: "general",
});
registry.category("studio_editors").add("form", formEditor);

const HOOK_CLASS_WHITELIST = [
    "o_web_studio_field_signature",
    "o_web_studio_field_html",
    "o_web_studio_field_many2many",
    "o_web_studio_field_one2many",
    "o_web_studio_field_tabs",
    "o_web_studio_field_columns",
    "o_web_studio_field_lines",
];
const HOOK_TYPE_BLACKLIST = [
    "genericTag",
    "afterGroup",
    "afterNotebook",
    "insideSheet",
];

const isBlackListedHook = (draggedEl, hookEl) =>
    !HOOK_CLASS_WHITELIST.some((cls) => draggedEl.classList.contains(cls)) &&
    HOOK_TYPE_BLACKLIST.some((t) => hookEl.dataset.type === t);

function canDropNotebook(hookEl) {
    if (hookEl.dataset.type === "page") {
        return false;
    }
    if (hookEl.closest(".o_group") || hookEl.closest(".o_inner_group")) {
        return false;
    }
    return true;
}

function canDropGroup(hookEl) {
    if (hookEl.dataset.type === "insideGroup") {
        return false;
    }
    if (hookEl.closest(".o_group") || hookEl.closest(".o_inner_group")) {
        return false;
    }
    return true;
}

function isValidFormHook({ hook, element }) {
    const draggingStructure = element.dataset.structure;
    switch (draggingStructure) {
        case "notebook": {
            if (!canDropNotebook(hook)) {
                return false;
            }
            break;
        }
        case "group": {
            if (!canDropGroup(hook)) {
                return false;
            }
            break;
        }
    }
    if (isBlackListedHook(element, hook)) {
        return false;
    }

    return true;
}
formEditor.isValidHook = isValidFormHook;

function addFormViewStructure(structure) {
    switch (structure) {
        case "notebook":
        case "group": {
            return {
                node: {
                    tag: structure,
                    attrs: {
                        name: randomName(`studio_${structure}`),
                    },
                },
            };
        }
    }
}
formEditor.addViewStructure = addFormViewStructure;
