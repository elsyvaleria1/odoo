/** @odoo-module native */
import { Editor } from "@html_editor/editor";
import { closestElement } from "@html_editor/utils/dom_traversal";
import {
    Component,
    onMounted,
    onWillDestroy,
    onWillStart,
    onWillUnmount,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { CheckBox } from "@web/components/checkbox";
import { useDebugMode } from "@web/core/debug/debug_context";
import { makeLogger } from "@web/core/debug/debug_logger";
import { ModelEvent } from "@web/core/events";
import { _t } from "@web/core/translation";
import { omit } from "@web/core/utils/collections/objects";
import { useOwnedDialogs, useService, useServices } from "@web/core/utils/hooks";
import { BooleanField } from "@web/fields/basic/boolean/boolean_field";
import { CharField } from "@web/fields/basic/char/char_field";
import { Many2ManyTagsField } from "@web/fields/relational/many2many_tags";
import { Many2OneField } from "@web/fields/relational/many2one";
import { Record as _Record } from "@web/model/record";
import { ConfirmationDialog } from "@web/ui/dialog";
import { useEditorMenuItem } from "@web_studio/client_action/editor/edition_flow";
import { useStudioEditorContext } from "@web_studio/client_action/editor/studio_editor_context";
import { ReportEditorSnackbar } from "@web_studio/client_action/report_editor/report_editor_snackbar";
import { memoizeOnce } from "@web_studio/client_action/utils";

import { ReportEditorIframe } from "../report_editor_iframe.js";
import { ReportRecordNavigation } from "../report_editor_xml/report_record_navigation.js";
import { getReportEditorPlugins } from "./editor_plugins/report_editor_plugin.js";

const log = makeLogger("web_studio.report_editor");

class __Record extends _Record.components._Record {
    setup() {
        super.setup();
        this.studioContext = useStudioEditorContext();
        const flushPendingEdits = (/** @type {CustomEvent} */ { detail }) =>
            detail.proms.push(this.model.urgentSave.flushPendingEdits());
        onMounted(() => {
            this.studioContext.reportEditorModel.bus.addEventListener(
                ModelEvent.WILL_SAVE_URGENTLY,
                flushPendingEdits,
            );
        });

        onWillDestroy(() =>
            this.studioContext.reportEditorModel.bus.removeEventListener(
                ModelEvent.WILL_SAVE_URGENTLY,
                flushPendingEdits,
            ),
        );
    }
}

class Record extends _Record {
    static components = { ..._Record.components, _Record: __Record };
}

class UndoRedo extends Component {
    static template = "web_studio.ReportEditorWysiwyg.UndoRedo";
    static props = { state: t.object(), className: t.string().optional() };
    props = useProps(this.constructor.props);
}

class ResetConfirmationPopup extends ConfirmationDialog {
    static template = "web_studio.ReportEditorWysiwyg.ResetConfirmationPopup";
    static props = { ...omit(ConfirmationDialog.props, "body"), state: t.object() };
}

export class ReportEditorWysiwyg extends Component {
    static components = {
        CharField,
        Record,
        Many2ManyTagsField,
        Many2OneField,
        BooleanField,
        UndoRedo,
        ReportEditorIframe,
        ReportRecordNavigation,
        CheckBox,
    };
    static props = { paperFormatStyle: t.string() };
    static template = "web_studio.ReportEditorWysiwyg";
    props = useProps(this.constructor.props);

    setup() {
        this.appServices = useServices();
        this.studioContext = useStudioEditorContext();
        this.debug = useDebugMode();
        this.dialog = useService("dialog");
        this.action = useService("action");
        this.addDialog = useOwnedDialogs();
        this.notification = useService("notification");

        this._getReportQweb = memoizeOnce(() => {
            const tree = new DOMParser().parseFromString(
                this.reportEditorModel.reportQweb,
                "text/html",
            );
            const htmlNode = tree.firstElementChild;
            htmlNode.translate = false;
            return htmlNode;
        });

        const reportEditorModel = (this.reportEditorModel = proxy(
            this.studioContext.reportEditorModel,
        ));
        this.reportRecordHooks = {
            lifecycle: {
                onRecordChanged: (rec) =>
                    (this.reportEditorModel.reportData = rec.data),
            },
        };

        useEditorMenuItem({
            component: ReportEditorSnackbar,
            props: {
                state: reportEditorModel,
                onSave: this.save.bind(this),
                onDiscard: this.discard.bind(this),
            },
        });

        this.undoRedoState = proxy({
            canUndo: false,
            canRedo: false,
            undo: () => this.editor?.shared.history.undo(),
            redo: () => this.editor?.shared.history.redo(),
        });

        onWillStart(() => this.reportEditorModel.loadReportQweb());

        onWillUnmount(() => this.saveOnLeave());
    }

    instantiateEditor({ editable } = {}) {
        this.undoRedoState.canUndo = false;
        this.undoRedoState.canRedo = false;
        const onEditorChange = () => {
            const canUndo = this.editor.shared.history.canUndo();
            this.reportEditorModel.isDirty = canUndo;
            Object.assign(this.undoRedoState, {
                canUndo: canUndo,
                canRedo: this.editor.shared.history.canRedo(),
            });
        };

        editable.querySelectorAll("[ws-view-id]").forEach((el) => {
            el.setAttribute("contenteditable", "true");
        });
        const editor = new Editor(
            {
                Plugins: getReportEditorPlugins(),
                onChange: onEditorChange,
                getRecordInfo: () => {
                    const { anchorNode } =
                        this.editor.shared.selection.getEditableSelection();
                    if (!anchorNode) {
                        return {};
                    }
                    const lastViewParent = closestElement(anchorNode, "[ws-view-id]");
                    if (!lastViewParent) {
                        return {};
                    }
                    return {
                        resModel: "ir.ui.view",
                        resId: parseInt(lastViewParent.getAttribute("ws-view-id")),
                        field: "arch",
                    };
                },
                reportResModel: this.reportEditorModel.reportResModel,
                allowVideo: false,
                allowImageTransform: false,
                allowImageResize: false,
            },
            this.appServices,
        );
        editor.attachTo(editable);
        editable.classList.remove("odoo-editor-qweb");
        return editor;
    }

    onIframeLoaded({ iframeRef }) {
        if (this.editor) {
            this.editor.destroy(true);
            this.editor = null;
        }
        this.iframeRef = iframeRef;
        const doc = iframeRef.el.contentDocument;
        doc.body.classList.remove("container");

        if (odoo.debug) {
            ["t-esc", "t-out", "t-field"].forEach((tAtt) => {
                doc.querySelectorAll(`*[${tAtt}]`).forEach((e) => {
                    if (e.hasAttribute("title")) {
                        e.setAttribute("data-oe-title", e.getAttribute("title"));
                    }
                    e.setAttribute("title", e.getAttribute(tAtt));
                });
            });
        }
        if (
            !this.reportEditorModel._errorMessage &&
            !this.reportEditorModel.inPreview
        ) {
            this.editor = this.instantiateEditor({
                editable: doc.querySelector("#wrapwrap"),
            });
        }
        this.reportEditorModel.setInEdition(false);
    }

    get reportQweb() {
        const model = this.reportEditorModel;
        return this._getReportQweb(`${model.renderKey}_${model.reportQweb}`).outerHTML;
    }

    get reportRecordProps() {
        const model = this.reportEditorModel;
        return {
            fields: model.reportFields,
            activeFields: model.reportActiveFields,
            values: model.reportData,
        };
    }

    saveOnLeave() {
        const htmlParts = this.collectHtmlParts();
        /** @type {Promise<unknown>[]} */
        const proms = [];
        this.reportEditorModel.bus.trigger(ModelEvent.WILL_SAVE_URGENTLY, { proms });
        this.editor?.destroy(true);
        const reportEditorModel = this.reportEditorModel;
        Promise.allSettled(proms).then(() => {
            log.logic("save on leave", () => ({
                flushed: proms.length,
                htmlParts: Object.keys(htmlParts ?? {}).length,
                dirty: Boolean(reportEditorModel.isDirty),
            }));
            return reportEditorModel.saveReport({ htmlParts, urgent: true });
        });
    }

    async save({ urgent = false } = {}) {
        await this.reportEditorModel.saveReport({
            htmlParts: this.collectHtmlParts(),
            urgent,
        });
    }

    /** @returns {Record<string, object[]> | undefined} */
    collectHtmlParts() {
        if (!this.editor) {
            return undefined;
        }
        const htmlParts = {};
        const editable = this.editor.getElContent();

        if (odoo.debug) {
            editable.querySelectorAll("*[t-field],*[t-out],*[t-esc]").forEach((e) => {
                if (e.hasAttribute("data-oe-title")) {
                    e.setAttribute("title", e.getAttribute("data-oe-title"));
                    e.removeAttribute("data-oe-title");
                } else {
                    e.removeAttribute("title");
                }
            });
        }

        editable.querySelectorAll("[ws-view-id].o_dirty").forEach((el) => {
            el.classList.remove("o_dirty");
            el.removeAttribute("contenteditable");
            const viewId = el.getAttribute("ws-view-id");
            if (!viewId) {
                return;
            }
            Array.from(el.querySelectorAll("[t-call]")).forEach((el) => {
                el.removeAttribute("contenteditable");
                el.replaceChildren();
            });

            Array.from(el.querySelectorAll("[oe-origin-t-out]")).forEach((el) => {
                el.replaceChildren();
            });
            if (
                !el.hasAttribute("oe-origin-class") &&
                el.getAttribute("class") === ""
            ) {
                el.removeAttribute("class");
            }

            const callGroupKey = el.getAttribute("ws-call-group-key");
            const type = callGroupKey ? "in_t_call" : "full";

            const escaped_html = el.outerHTML;
            htmlParts[viewId] = htmlParts[viewId] || [];

            htmlParts[viewId].push({
                call_key: el.getAttribute("ws-call-key"),
                call_group_key: callGroupKey,
                type,
                html: escaped_html,
            });
        });
        return htmlParts;
    }

    async discard() {
        if (this.editor) {
            const selection = this.editor.document.getSelection();
            if (selection) {
                selection.removeAllRanges();
            }
        }
        this.dialog.add(ConfirmationDialog, {
            body: _t(
                "If you discard the current edits, all unsaved changes will be lost. You can cancel to return to edit mode.",
            ),
            confirm: () => this.reportEditorModel.discardReport(),
            cancel: () => {},
        });
    }

    async resetReport() {
        const state = proxy({ includeHeaderFooter: true });
        this.addDialog(ResetConfirmationPopup, {
            title: _t("Reset report"),
            confirmLabel: _t("Reset report"),
            confirmClass: "btn-danger",
            cancelLabel: _t("Go back"),
            state,
            cancel: () => {},
            confirm: async () => {
                await this.reportEditorModel.saveReport();
                try {
                    await this.reportEditorModel.resetReport(state.includeHeaderFooter);
                } finally {
                    this.reportEditorModel.renderKey++;
                }
            },
        });
    }

    async openReportFormView() {
        await this.save();
        return this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "ir.actions.report",
                res_id: this.reportEditorModel.editedReportId,
                views: [[false, "form"]],
                target: "current",
            },
            { clearBreadcrumbs: true },
        );
    }

    async editSources() {
        await this.save();
        this.reportEditorModel.mode = "xml";
    }

    async togglePreview(toValue) {
        if (toValue) {
            const saved = await this.save();
            if (!saved) {
                await this.reportEditorModel.loadReportHtml();
            }
        }
        this.reportEditorModel.inPreview = toValue;
    }
}
