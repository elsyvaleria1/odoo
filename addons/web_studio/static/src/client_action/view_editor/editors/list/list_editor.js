/** @odoo-module native */
import { Component, t, useProps, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { omit } from "@web/core/utils/collections/objects";
import { nodeAttrs } from "@web/views/ir/view_ir";
import { listView } from "@web/views/list";

import { getStudioNoFetchFields, useModelConfigFetchInvisible } from "../utils.js";
import { computeIRXpath } from "../xml_utils.js";
import { columnsStyling, ListEditorRenderer } from "./list_editor_renderer.js";
import { ListEditorSidebar } from "./list_editor_sidebar/list_editor_sidebar.js";

function parseStudioGroups(node) {
    return nodeAttrs(node).studio_groups;
}

class EditorArchParser extends listView.ArchParser {
    parse(arch, models, modelName) {
        const parsed = super.parse(...arguments);
        const noFetch = getStudioNoFetchFields(parsed.fieldNodes);
        parsed.fieldNodes = omit(parsed.fieldNodes, ...noFetch.fieldNodes);
        const noFetchFieldNames = noFetch.fieldNames;
        parsed.columns = parsed.columns.filter(
            (col) => col.type !== "field" || !noFetchFieldNames.includes(col.name),
        );
        return parsed;
    }

    // the list parser walks the view IR; `this.parents` is its walk
    parseFieldNode(node, models, modelName) {
        const parsed = super.parseFieldNode(...arguments);
        if ("data-used-by" in nodeAttrs(node)) {
            return parsed;
        }
        parsed.studioXpath = computeIRXpath(node, this.parents, ["list", "tree"]);
        parsed.studio_groups = parseStudioGroups(node);
        return parsed;
    }

    parseWidgetNode(node, models, modelName) {
        const parsed = super.parseWidgetNode(...arguments);
        parsed.studioXpath = computeIRXpath(node, this.parents, ["list", "tree"]);
        parsed.studio_groups = parseStudioGroups(node);
        return parsed;
    }

    processButton(node) {
        const parsed = super.processButton(node);
        parsed.studioXpath = computeIRXpath(node, this.parents, ["list", "tree"]);
        parsed.studio_groups = parseStudioGroups(node);
        return parsed;
    }
}

/**
 * X2Many fields can have their subview edited. There are some challenges currently with the RelationalModel
 * - We need to inject the parent record in the evalContext. That way, within the subview's arch
 *   a snippet like `<field name="..." invisible="not parent.id" />` works.
 * - We already know the resIds we have, since we are coming from a x2m. There is no need to search_read them, just to read them
 * - The RelationalModel doesn't really supports creatic staticLists as the root record
 *
 * StaticList supports the two first needs and not DynamicList, we assume that the amount of hacking
 * would be slightly bigger if our starting point is DynamicList. Hence, we choose
 * to extend StaticList instead of DynamicList, and make it the root record of the model.
 */
function useParentedStaticList(model, parentRecord, resIds) {
    const config = model.config;
    config.resIds = resIds;
    config.offset = 0;
    config.limit = Math.max(7, resIds.length); // don't load everything

    model._createRoot = (config, data) => {
        const options = { parent: parentRecord };
        // _loadData returns `{ records, length }` for a multi-record root;
        // StaticList expects the raw array of record data.
        return new model.constructor.StaticList(
            model,
            { ...config },
            data.records,
            options,
        );
    };
    model._createEmptyRoot = () => null;
}

class ListEditorController extends listView.Controller {
    static props = {
        ...listView.Controller.props,
        parentRecord: t.object().optional(),
    };
    setup() {
        super.setup();
        useModelConfigFetchInvisible(this.model);
        if (this.props.parentRecord) {
            useParentedStaticList(
                this.model,
                this.props.parentRecord,
                this.props.resIds,
            );
        }
    }
}

class ControllerShadow extends Component {
    static props = { ...ListEditorController.props };
    static template = xml`<t t-component="this.Component" t-props="this.componentProps" />`;
    props = useProps(this.constructor.props);
    get Component() {
        return ListEditorController;
    }

    get componentProps() {
        const props = { ...this.props };
        props.groupBy = [];
        return props;
    }
}

const listEditor = {
    ...listView,
    Controller: ControllerShadow,
    ArchParser: EditorArchParser,
    Renderer: ListEditorRenderer,
    props() {
        const props = listView.props(...arguments);
        props.allowSelectors = false;
        props.readonly = true;
        props.showButtons = false;
        return props;
    },
    Sidebar: ListEditorSidebar,
};
// The object itself, not a copy: the hooks assigned below register on it.
Object.assign(listEditor, {
    label: _t("List"),
    icon: "oi oi-view-list",
    group: "multiple",
});
registry.category("studio_editors").add("list", listEditor);

/**
 *  Drag/Drop styling
 */

const colNearestHookClass = "o_web_studio_nearest_hook";
listEditor.styleNearestHook = function styleNearestColumn(mainRef, nearestHook) {
    const xpath = nearestHook.dataset.xpath;
    const position = nearestHook.dataset.position;
    columnsStyling(
        mainRef.el,
        `.o_web_studio_hook[data-xpath='${xpath}'][data-position='${position}']`,
        [colNearestHookClass],
    );
};

listEditor.styleClickedElement = (mainRef, params) => {
    columnsStyling(
        mainRef.el,
        `[data-studio-xpath='${params.xpath}']:not(.o_web_studio_hook)`,
        ["o-web-studio-editor--element-clicked"],
    );
};
