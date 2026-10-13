/** @odoo-module native */
import { EventBus, markRaw, proxy, toRaw } from "@odoo/owl";
import { rpc, rpcBus } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { Race } from "@web/core/utils/concurrency";
import { parseXML } from "@web/core/utils/dom/xml";
import { SignalStore } from "@web/core/utils/reactive";
import { SearchModel } from "@web/search/search_model";
import { GROUPABLE_TYPES } from "@web/search/utils/misc";
import { AlertDialog } from "@web/ui/dialog";
import { buildComponentProps } from "@web/views/view";
import { getModifier, resetViewCompilerCache } from "@web/views/view_compiler";
import {
    EditorOperations,
    SnackbarIndicator,
} from "@web_studio/client_action/editor/edition_flow";
import { getFieldsInArch, memoizeOnce } from "@web_studio/client_action/utils";
import {
    cleanClickedElements,
    xpathToLegacyXpathInfo,
} from "@web_studio/client_action/view_editor/editors/utils";
import {
    computeXpath,
    getNodeAttributes,
    getNodesFromXpath,
    parseStringToXml,
    serializeXmlToString,
} from "@web_studio/client_action/view_editor/editors/xml_utils";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";
import { viewTypeToString } from "@web_studio/studio_service";

const editorsRegistry = registry.category("studio_editors");
const viewRegistry = registry.category("views");

class EditorOperationsWithSnackbar extends EditorOperations {
    constructor(params) {
        super(...arguments);
        this.snackBar = params.snackBar;
        this.race = markRaw(new Race());
    }

    _wrapPromise(prom) {
        const _prom = super._wrapPromise(prom);
        this.snackBar.add(this.race.add(_prom));
        return _prom;
    }
}

function getSubarchPosition(mainArch, xpathToField, archTag) {
    const xpathToArch = `${xpathToField}/${archTag}[not(@studio_subview_inlined)]`;
    const nodes = getNodesFromXpath(xpathToArch, parseStringToXml(mainArch));
    let hasArch = false;
    let position = 1;
    for (const node of nodes) {
        if (
            getModifier(node, "invisible") !== "True" &&
            getModifier(node, "invisible") !== "1"
        ) {
            hasArch = true;
            break;
        }
        position++;
    }
    return { hasArch, position };
}

/**
 * @param {String} mainArch
 * @param {String} xpathToField
 * @param {String} archTag
 * @param {Number} position
 */
function getSubArch(mainArch, xpathToField, archTag, position) {
    const xpathToView = `${archTag}[${position}]`;
    const xpathToArch = `${xpathToField}/${xpathToView}`;
    const nodes = getNodesFromXpath(xpathToArch, parseStringToXml(mainArch));
    if (nodes.length !== 1) {
        throw new Error(`Single sub-view arch not found for xpath: ${xpathToArch}`);
    }
    return serializeXmlToString(nodes[0]);
}

function buildKey(...args) {
    return args.join("_");
}

export class ViewEditorModel extends SignalStore {
    constructor({ env, services, editionFlow, viewRef, initialState = {} }) {
        super();
        this.initialState = initialState;
        this._isInEdition = false;
        this.mode = "interactive";
        this.env = env;
        this.bus = markRaw(new EventBus());
        this._services = markRaw(services);
        this._studio = services.studio;

        this._snackBar = new SnackbarIndicator();
        this._operations = new EditorOperationsWithSnackbar({
            do: this._handleOperations.bind(this),
            onDone: this._handleDone.bind(this),
            onError: this._handleError.bind(this),
            snackBar: this._snackBar,
        });

        this._decorateCall = async (callback, ...args) => {
            this._services.ui.block();
            const prom = callback(...args);
            this._snackBar.add(prom);
            try {
                return await prom;
            } finally {
                this._services.ui.unblock();
            }
        };
        this._decorateFunction =
            (callback) =>
            async (...args) =>
                this._decorateCall(callback, ...args);

        this._decoratedRpc = this._decorateFunction(rpc);

        this._editionFlow = editionFlow;

        this.GROUPABLE_TYPES = [...GROUPABLE_TYPES];
        this.MEASURABLE_TYPES = ["integer", "float", "monetary"];

        this._activeNodeXpath = undefined;
        this.lastActiveNodeXpath = undefined;

        this._getEditor = memoizeOnce(() => {
            const viewType = this.viewType;
            const view = viewRegistry.contains(viewType)
                ? viewRegistry.get(viewType)
                : null;
            const editor = editorsRegistry.contains(viewType)
                ? editorsRegistry.get(viewType)
                : null;

            const rendered =
                this.mode === "interactive" ? editor || view : view || editor;
            return {
                buildProps: (controllerProps, config) =>
                    editor?.props
                        ? editor.props(controllerProps, rendered, config)
                        : buildComponentProps(rendered, controllerProps, config),
                editor: rendered,
            };
        });

        this._getControllerProps = memoizeOnce(function () {
            let { resId, resIds } = this.isEditingSubview
                ? this._subviewInfo
                : this._studio.editedControllerState || {};
            resIds = resIds || [];
            resId = resId || resIds[0];

            const arch = parseXML(this.arch);
            if (this.mode !== "interactive") {
                arch.querySelectorAll(`[studio_no_fetch="1"]`).forEach((n) =>
                    n.remove(),
                );
            }

            const rootArchNode = this.xmlDoc.firstElementChild;
            const controllerClasses = Array.from(
                new Set([
                    "o_view_controller",
                    `o_${this.viewType}_view`,
                    ...(rootArchNode.getAttribute("class") || "").split(" "),
                ]),
            ).filter((c) => c);

            let controllerProps = {
                info: {},
                relatedModels: { ...toRaw(this.viewDescriptions.relatedModels) },
                useSampleModel: ["graph", "pivot"].includes(this.viewType),
                searchMenuTypes: [],
                className: controllerClasses.join(" "),
                resId,
                resIds,
                resModel: this.resModel,
                arch,
                fields: { ...toRaw(this.fields) },
            };

            if (
                ["list", "list", "form"].includes(this.viewType) &&
                this.mode === "interactive" &&
                this._subviewInfo
            ) {
                controllerProps.parentRecord = this._subviewInfo.parentRecord;
            }

            controllerProps = this.editorInfo.buildProps(
                controllerProps,
                this.env.config,
            );

            return markRaw(controllerProps);
        });

        this.__getDefaultStudioViewProps = memoizeOnce(() => {
            const editedAction = this._studio.editedAction;
            let globalState;
            if (this._views.search && !this.isEditingSubview) {
                globalState = editedAction.globalState;
            }

            const context = this._subviewInfo
                ? this._subviewInfo.context
                : editedAction.context;
            const searchModel = this.editorInfo.editor.SearchModel || SearchModel;
            let defaultGroupBy = [];
            if (!this.isEditingSubview) {
                defaultGroupBy = this.xmlDoc.firstElementChild.hasAttribute(
                    "default_group_by",
                )
                    ? this.xmlDoc.firstElementChild
                          .getAttribute("default_group_by")
                          .split(",")
                    : [];
            }
            return {
                context: { ...context, studio: 1 },
                domain: editedAction.domain,
                resModel: this.resModel,
                SearchModel: searchModel,
                setOverlay:
                    !["form", "list", "list", "kanban", "search"].includes(
                        this.viewType,
                    ) || this.mode !== "interactive",
                display: { controlPanel: false, searchPanel: false },
                globalState,
                defaultGroupBy,
            };
        });

        this._getActiveNode = memoizeOnce(() => {
            if (!this.activeNodeXpath) {
                return undefined;
            }

            const node = getNodesFromXpath(this.activeNodeXpath, this.xmlDoc)[0];
            if (!node) {
                return null;
            }
            const isField = node.tagName === "field";
            const attrs = getNodeAttributes(node);
            const humanName =
                this.editorInfo.editor.Sidebar.viewStructures?.[node.tagName]?.name ||
                node.tagName;

            let field;
            if (isField) {
                field = proxy(this.fields[attrs.name]);
                Object.defineProperty(field, "label", {
                    get() {
                        return field.string;
                    },
                    configurable: true,
                });
            }
            return proxy({
                arch: node,
                attrs,
                humanName,
                xpath: this.activeNodeXpath,
                field,
            });
        });

        this._getUnprocessedXmlDoc = memoizeOnce((arch) => parseStringToXml(arch));

        this.breadcrumbs = editionFlow.breadcrumbs;

        this._editionFlow = editionFlow;

        this._views = {};

        this.studioViewArch = "";
        this.viewDescriptions = {
            relatedModels: {},
            fields: [],
        };
        this.viewRef = viewRef;

        this.showInvisible = initialState.showInvisible || false;

        this._currentSidebarTab = undefined;

        this._getFieldsAllowedRename = memoizeOnce(() => new Set());
    }

    static sanitizeString(string) {
        string = string.normalize("NFD");
        string = string
            .toLowerCase()
            .trim()
            .replace(/[^\w\s-]/g, "")
            .replace(/[\s_-]+/g, "_")
            .replace(/^-+|-+$/g, "");
        return string;
    }

    get editorInfo() {
        return this._getEditor(buildKey(this.viewType, this.mode));
    }

    get controllerProps() {
        const key = buildKey(
            this.arch,
            this.viewType,
            this.mode,
            this.resModel,
            this.breadcrumbs.length > 1 ? this.breadcrumbs.length : 1,
        );
        return this._getControllerProps(key);
    }

    get studioViewProps() {
        const key = buildKey(
            this.viewType,
            this.resModel,
            this.mode,
            this.isEditingSubview,
            this.isEditingSubview ? false : this.arch,
        );
        return this.__getDefaultStudioViewProps(key);
    }

    get xmlDoc() {
        return this._getUnprocessedXmlDoc(this.arch);
    }

    get isEditingSubview() {
        return this.breadcrumbs.length > 1;
    }

    set isInEdition(value) {
        value = !!value;
        if (this.isInEdition === value) {
            return;
        }
        this._isInEdition = value;
        if (value) {
            this._services.ui.block();
        } else {
            this._services.ui.unblock();
        }
    }

    get isInEdition() {
        return this._isInEdition;
    }

    get mainView() {
        return this._views ? this._views[this.mainViewType] : undefined;
    }

    get mainArch() {
        return this.mainView ? this.mainView.arch : "";
    }

    get mainViewType() {
        return this._studio.editedViewType;
    }

    get mainResModel() {
        return this._studio.editedAction.res_model;
    }

    get arch() {
        return this.isEditingSubview
            ? this._subviewInfo.getArch(this.mainArch)
            : this.mainArch;
    }

    get viewType() {
        return this.isEditingSubview ? this._subviewInfo.viewType : this.mainViewType;
    }

    get view() {
        return this._views[this.viewType];
    }

    get resModel() {
        return this.isEditingSubview ? this._subviewInfo.resModel : this.mainResModel;
    }

    get fields() {
        return this.viewDescriptions.relatedModels[this.resModel].fields;
    }

    get activeNode() {
        return this._getActiveNode(buildKey(this.activeNodeXpath, this.arch));
    }

    get studioViewKey() {
        return buildKey(this.arch, JSON.stringify(this.fields));
    }

    get fieldsInArch() {
        return getFieldsInArch(this.xmlDoc);
    }

    get isChatterAllowed() {
        return !this.isEditingSubview && this._isChatterAllowed;
    }

    get activeNodeXpath() {
        return this._activeNodeXpath;
    }

    set activeNodeXpath(value) {
        this._activeNodeXpath = value;
        if (value) {
            this.lastActiveNodeXpath = value;
        }
    }

    get sidebarTab() {
        if (this.activeNodeXpath) {
            return "properties";
        }
        return this._currentSidebarTab;
    }

    set sidebarTab(newTab) {
        this._currentSidebarTab = newTab;
    }

    async editX2ManyView({ viewType, fieldName, record, xpath, fieldContext }) {
        const staticList = record.data[fieldName];
        const resIds = staticList.records.map((r) => r.resId).filter((id) => !!id);
        const resModel = staticList.resModel;
        const archTag = viewType;

        const currentFullXpath = this.getSubviewXpath();
        let xpathToField = xpath;
        if (currentFullXpath) {
            const xpathWithoutView = xpath.split("/").slice(2);
            xpathToField = `${currentFullXpath}/${xpathWithoutView.join("/")}`;
        }

        const { hasArch, position } = getSubarchPosition(
            this.mainArch,
            xpathToField,
            archTag,
        );
        if (!hasArch) {
            const subViewRef = fieldContext[`${archTag}_view_ref`] || null;
            this.studioViewArch = await this._createInlineView({
                subViewType: viewType,
                fullXpath: xpathToField,
                subViewRef,
                resModel,
                fieldName,
            });
            const viewDescriptions = await this._editionFlow.loadViews();
            this.viewDescriptions = viewDescriptions;
            Object.assign(this._views, viewDescriptions.views);
            this._operations.clear(false);
        }
        await this._decorateCall(() => this.fieldsGet(resModel));

        const context = Object.fromEntries(
            Object.entries(fieldContext).filter(
                ([key, val]) =>
                    !key.startsWith("default_") && !key.endsWith("_view_ref"),
            ),
        );

        const x2ManyEditionInfo = {
            name: _t("Subview %(viewType)s", { viewType: viewTypeToString(viewType) }),
            context,
            resModel,
            resId: resIds[0],
            resIds,
            viewType,
            parentRecord: record,
            xpath: `${xpath}/${archTag}[${position}]`,
            fieldName,
            getArch: memoizeOnce((mainArch) =>
                getSubArch(mainArch, xpathToField, archTag, position),
            ),
        };
        this._editionFlow.pushBreadcrumb(x2ManyEditionInfo);
    }

    async fieldsGet(resModel) {
        this.fieldsGetCache = this.fieldsGetCache || new Set();
        if (!this.fieldsGetCache.has(resModel)) {
            const fg = await this._services.orm.call(resModel, "fields_get");
            this.fieldsGetCache.add(resModel);
            Object.assign(this.viewDescriptions.relatedModels[resModel].fields, fg);
        }
    }

    async load() {
        const proms = [this._editionFlow.loadViews({ forceSearch: true })];

        if (this.viewType === "form") {
            proms.push(this._studio.IrModelInfo.read(this.mainResModel));
        }

        const [viewDescriptions, modelInfo] = await Promise.all(proms);
        this._isChatterAllowed =
            modelInfo?.is_mail_thread || modelInfo?.state === "manual";
        this.viewDescriptions = viewDescriptions || {
            relatedModels: {},
            fields: [],
        };
        Object.assign(this._views, viewDescriptions.views);
        const { mainViewId, viewId, arch } = await this._getStudioViewArch();
        this.studioViewArch = arch;
        this.studioViewId = viewId;
        if (!this.mainView.id) {
            rpcBus.trigger("CLEAR-CACHES");
            this.mainView.id = mainViewId;
        }
    }

    getSubviewXpath() {
        if (!this.isEditingSubview) {
            return null;
        }
        const temp = [`/${this.mainViewType}[1]`];
        this.breadcrumbs.slice(1).forEach(({ data }) => {
            const withoutView = data.xpath.split("/").slice(2);
            temp.push(...withoutView);
        });
        return temp.join("/");
    }

    getFullTarget(xpath, { isXpathFullAbsolute = true } = {}) {
        const nodes = getNodesFromXpath(xpath, this.xmlDoc);
        if (nodes.length !== 1) {
            throw new Error("Xpath resolved to nothing or multiple nodes");
        }
        const element = nodes[0];

        const attrs = {};
        ["name", "id", "class", "for"].forEach((attrName) => {
            if (element.hasAttribute(attrName)) {
                attrs[attrName] = element.getAttribute(attrName);
            }
        });

        let xpath_info;
        if (isXpathFullAbsolute) {
            xpath_info = xpathToLegacyXpathInfo(xpath);
        } else {
            const fullAbsolute = computeXpath(element, this.viewType);
            xpath_info = xpathToLegacyXpathInfo(fullAbsolute);
        }

        const target = {
            tag: element.tagName,
            attrs,
            xpath_info,
        };

        const subViewXpath = this.getSubviewXpath();
        if (subViewXpath) {
            target.subview_xpath = subViewXpath;

            const subViewTargetInfo = xpathToLegacyXpathInfo(subViewXpath);
            xpath_info.splice(0, 1, subViewTargetInfo[subViewTargetInfo.length - 1]);
        }
        return target;
    }

    async doOperation(operation, write = true) {
        return this._operations.do(operation, !write);
    }

    pushOperation(operation) {
        return this._operations.pushOp(operation);
    }

    resetSidebar(tab = null) {
        this.sidebarTab = tab;
        this.activeNodeXpath = undefined;

        const resetEl = this.viewRef.el;
        if (resetEl) {
            cleanClickedElements(resetEl);
        }
    }

    switchMode() {
        resetViewCompilerCache();
        this.mode = this.mode === "interactive" ? "xml" : "interactive";
    }

    setRenameableField(fieldName, add = true) {
        if (add) {
            this._fieldsAllowedRename.add(fieldName);
        } else {
            this._fieldsAllowedRename.delete(fieldName);
        }
    }

    isFieldRenameable(fieldName) {
        return this._fieldsAllowedRename.has(fieldName);
    }

    async renameField(fieldName, newName, { label, autoUnique = true } = {}) {
        newName = ViewEditorModel.sanitizeString(newName);

        if (!newName.startsWith("x_studio_")) {
            newName = `x_studio_${newName}`;
        }

        const existingFields = this.fields;
        if (autoUnique) {
            const baseName = newName;
            let index = 1;
            while (newName in existingFields) {
                newName = baseName + "_" + index;
                index++;
            }
        }

        if (!autoUnique && newName in existingFields) {
            this._services.dialog.add(AlertDialog, {
                body: _t("A field with the same name already exists."),
            });
            return;
        }
        this.isInEdition = true;
        const prom = rpc("/web_studio/rename_field", {
            studio_view_id: this.studioViewId,
            studio_view_arch: this.studioViewArch,
            model: this.resModel,
            old_name: fieldName,
            new_name: newName,
            new_label: label,
        });

        this._snackBar.add(prom);

        try {
            await prom;
        } catch (e) {
            this.isInEdition = false;
            throw e;
        }

        const strOperations = JSON.stringify(this._operations.operations);
        const chars = "[^\\w\\u007F-\\uFFFF]";
        const re = new RegExp(`(${chars}|^)${fieldName}(${chars}|$)`, "g");
        this._operations.clear();
        this.setRenameableField(fieldName, false);
        this.setRenameableField(newName, true);
        this._operations.doMulti(
            JSON.parse(strOperations.replace(re, `$1${newName}$2`)),
        );
    }

    async _createInlineView({
        subViewType,
        fullXpath,
        subViewRef,
        resModel,
        fieldName,
    }) {
        const context = { ...user.context, lang: false, studio: true };
        if (subViewRef) {
            context[`${subViewType}_view_ref`] = subViewRef;
        }

        const studioViewArch = await this._decoratedRpc(
            "/web_studio/create_inline_view",
            {
                model: resModel,
                view_id: this.mainView.id,
                field_name: fieldName,
                subview_type: subViewType,
                subview_xpath: fullXpath,
                context,
            },
        );
        rpcBus.trigger("CLEAR-CACHES");
        return studioViewArch;
    }

    async _editView(operations) {
        const context = {
            ...user.context,
            ...this._studio.editedAction.context,
            lang: false,
            studio: true,
        };
        return rpc("/web_studio/edit_view", {
            view_id: this.mainView.id,
            studio_view_arch: this.studioViewArch,
            operations: operations,
            model: this.resModel,
            context,
        });
    }

    async _editViewArch(viewId, viewArch) {
        const context = {
            ...user.context,
            ...this._studio.editedAction.context,
            lang: false,
            studio: true,
        };
        const result = await rpc("/web_studio/edit_view_arch", {
            view_id: viewId,
            view_arch: viewArch,
            context,
        });
        return result;
    }

    async _handleOperations({ mode, operations, lastOp }) {
        this.isInEdition = true;
        if (lastOp.type !== "replace_arch") {
            operations = operations.filter((op) => op.type !== "replace_arch");
            return this._editView(operations);
        } else {
            const viewId = lastOp.viewId;
            const arch = mode === "undo" ? lastOp.oldArch : lastOp.newArch;
            return this._editViewArch(viewId, arch);
        }
    }

    async restoreDefaultView(viewId) {
        const result = await this._editionFlow.restoreDefaultView(
            viewId,
            this.mainViewType,
        );
        if (result) {
            this.viewDescriptions.relatedModels = result.models;
            this._views[this.mainViewType].arch = result.views[this.mainViewType].arch;
            this._operations.clear();
        }
    }

    _handleDone({ mode, pending, pendingUndone, result }) {
        rpcBus.trigger("CLEAR-CACHES");
        if (this.mainViewType === "kanban") {
            resetViewCompilerCache();
        }
        if (result) {
            this.viewDescriptions.relatedModels = result.models;

            const oldArch = this._views[this.mainViewType].arch;
            const newArch = result.views[this.mainViewType].arch;
            this._views[this.mainViewType].arch = newArch;
            if (oldArch === newArch) {
                this.isInEdition = false;
            }

            if (!this.studioViewId && result.studio_view_id) {
                this.studioViewId = result.studio_view_id;
            }
        }

        const isUndoing = mode === "undo";
        const pendingOps = isUndoing ? pendingUndone : pending;
        const lastOperation = pendingOps[pendingOps.length - 1];
        if (lastOperation && lastOperation.type === "replace_arch") {
            if (lastOperation.viewId === this.studioViewId) {
                this.studioViewArch = isUndoing
                    ? lastOperation.oldArch
                    : lastOperation.newArch;
                this._operations.clear();
                const ops = isUndoing
                    ? this._operations.undone
                    : this._operations.operations;
                ops.push(lastOperation);
            }
        }
    }

    async _handleError({ mode, pending, error }) {
        this.isInEdition = false;
        this._services.notification.add(
            _t("This operation caused an error, probably because a xpath was broken"),
            {
                type: "danger",
            },
        );

        Promise.resolve().then(() => {
            throw error;
        });

        this.resetSidebar("view");
        this.bus.trigger("error");
    }

    async _getStudioViewArch() {
        const result = await rpc("/web_studio/get_studio_view_arch", {
            model: this.resModel,
            view_type: this.viewType,
            view_id: this.mainView.id,
            context: { ...user.context, lang: false },
        });
        return {
            arch: result.studio_view_arch,
            viewId: result.studio_view_id,
            mainViewId: result.main_view_id,
        };
    }

    get _subviewInfo() {
        if (!this.isEditingSubview) {
            return null;
        }
        const length = this.breadcrumbs.length;
        return this.breadcrumbs[length - 1].data;
    }

    get _fieldsAllowedRename() {
        return this._getFieldsAllowedRename(
            this.breadcrumbs.length > 1 ? this.breadcrumbs.length : 1,
        );
    }
}

export function useEditNodeAttributes({ isRoot = false } = {}) {
    const vem = useCurrentViewEditorModel();
    function editNodeAttributes(newAttributes) {
        let target;
        let node;
        if (isRoot) {
            target = vem.getFullTarget(`/${vem.viewType}`);
            target.isSubviewAttr = true;
        } else {
            target = vem.getFullTarget(vem.activeNodeXpath);
            const { arch, attrs } = vem.activeNode;
            node = {
                tag: arch.tagName,
                attrs,
            };
        }

        const operation = {
            new_attrs: newAttributes,
            type: "attributes",
            position: "attributes",
            target,
        };
        if (node) {
            operation.node = node;
        }
        return vem.doOperation(operation);
    }
    return editNodeAttributes;
}
