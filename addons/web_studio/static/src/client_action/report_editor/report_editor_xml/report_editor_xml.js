/** @odoo-module native */
import {
    Component,
    onWillStart,
    onWillUnmount,
    proxy,
    t,
    toRaw,
    useProps,
} from "@odoo/owl";
import { CheckBox } from "@web/components/checkbox";
import { useDebugMode } from "@web/core/debug/debug_context";
import { localization } from "@web/core/l10n/localization";
import { user } from "@web/core/user";
import { useBus, useOwnedDialogs } from "@web/core/utils/hooks";
import { TranslationDialog } from "@web/fields/translation_dialog";
import { View } from "@web/views/view";
import { useEditorMenuItem } from "@web_studio/client_action/editor/edition_flow";
import { useStudioEditorContext } from "@web_studio/client_action/editor/studio_editor_context";
import { ReportEditorSnackbar } from "@web_studio/client_action/report_editor/report_editor_snackbar";
import { XmlResourceEditor } from "@web_studio/client_action/xml_resource_editor/xml_resource_editor";

import { ReportEditorIframe } from "../report_editor_iframe.js";
import { ReportRecordNavigation } from "./report_record_navigation.js";

class ReportResourceEditor extends XmlResourceEditor {
    static props = { ...XmlResourceEditor.props, slots: t.object() };
    setup() {
        super.setup();
        this.studioContext = useStudioEditorContext();
        useBus(this.studioContext.reportEditorModel.bus, "node-clicked", (ev) => {
            const { viewId } = ev.detail;
            const nextResource = this.state.resourcesOptions.find(
                (opt) => opt.value === viewId,
            );
            if (nextResource) {
                this.state.currentResourceId = nextResource.value;
            }
        });
    }
}

class TranslationButton extends Component {
    static template = "web.TranslationButton";
    static props = { resourceId: t.number() };
    props = useProps(this.constructor.props);

    setup() {
        this.studioContext = useStudioEditorContext();
        this.addDialog = useOwnedDialogs();
    }

    get isMultiLang() {
        return localization.multiLang;
    }
    get lang() {
        return new Intl.Locale(user.lang).language.toUpperCase();
    }
    onClick() {
        this.addDialog(TranslationDialog, {
            fieldName: "arch_db",
            resModel: "ir.ui.view",
            resId: this.props.resourceId,
            onSave: () => {
                const model = this.studioContext.reportEditorModel;
                model.loadReportHtml({ resId: model.reportEnv.currentId });
            },
        });
    }
}

class _View extends View {
    async loadView() {
        const res = await super.loadView(...arguments);
        const Controller = this.Controller;
        if (
            !("afterExecuteActionButton" in Controller.props) &&
            "afterExecuteActionButton" in Controller.prototype
        ) {
            class _Controller extends Controller {
                afterExecuteActionButton(clickParams) {
                    const res = super.afterExecuteActionButton(...arguments);
                    this.props.afterExecuteActionButton(this.model, ...arguments);
                    return res;
                }
            }
            _Controller.props = {
                ...Controller.props,
                afterExecuteActionButton: t.function(),
            };
            this.Controller = _Controller;
        }
        return res;
    }
}

export class ReportEditorXml extends Component {
    static components = {
        XmlResourceEditor: ReportResourceEditor,
        ReportRecordNavigation,
        ReportEditorIframe,
        TranslationButton,
        View: _View,
        CheckBox,
    };
    static template = "web_studio.ReportEditorXml";
    static props = { paperFormatStyle: t.string() };
    props = useProps(this.constructor.props);

    setup() {
        this.studioContext = useStudioEditorContext();
        this.debug = useDebugMode();
        this.reportEditorModel = proxy(this.studioContext.reportEditorModel);
        this.state = proxy({
            xmlChanges: null,
            reloadSources: 1,
            viewIdToDiff: false,
            warningMessage: "",
            get isDirty() {
                return !!this.xmlChanges;
            },
        });

        useEditorMenuItem({
            component: ReportEditorSnackbar,
            props: {
                state: this.state,
                onSave: this.save.bind(this),
                onDiscard: this.discardChanges.bind(this),
            },
        });

        onWillStart(() => this.reportEditorModel.loadReportHtml());

        onWillUnmount(() => {
            this.save({ urgent: true });
        });
    }

    get minWidth() {
        const factor = this.state.viewIdToDiff ? 0.2 : 0.4;
        return Math.floor(document.documentElement.clientWidth * factor);
    }

    async onCloseXmlEditor() {
        await this.save();
        this.reportEditorModel.mode = "wysiwyg";
    }

    onXmlChanged(changes) {
        this.state.xmlChanges = changes;
    }

    getDefaultResource(resourcesOptions, mainKey) {
        let mainResource;
        if (mainKey) {
            mainResource = resourcesOptions.find((opt) => opt.resource.key === mainKey);
        }
        if (mainResource) {
            const studioExtension = resourcesOptions.find((opt) => {
                const key = opt.resource.key;
                const parentId = opt.resource.inherit_id && opt.resource.inherit_id[0];
                return (
                    key.includes("web_studio.report_editor_customization") &&
                    parentId === mainResource.resource.id
                );
            });
            return studioExtension || mainResource;
        }
    }

    async save({ urgent = false } = {}) {
        const changes = { ...toRaw(this.state.xmlChanges) };
        const result = await this.reportEditorModel.saveReport({
            urgent,
            xmlVerbatim: changes,
        });
        this.state.warningMessage = this.reportEditorModel.warningMessage;
        if (result !== false) {
            this.state.xmlChanges = null;
            if (!urgent && Object.keys(changes).length) {
                this.state.reloadSources++;
            }
        }
    }

    async discardChanges() {
        this.state.xmlChanges = null;
        this.state.reloadSources++;
    }

    onIframeLoaded({ iframeRef }) {
        iframeRef.el.contentWindow.document.addEventListener("click", (ev) => {
            const target = ev.target;
            const brandingTarget = target.closest(
                `[data-oe-model="ir.ui.view"][data-oe-field="arch"]`,
            );
            if (!brandingTarget) {
                return;
            }
            const viewId = parseInt(brandingTarget.getAttribute("data-oe-id"));
            this.reportEditorModel.bus.trigger("node-clicked", { viewId });
        });
        this.reportEditorModel.setInEdition(false);
    }

    async switchToDiff(viewId) {
        await this.save();
        this.state.viewIdToDiff = viewId;
    }

    get diffProps() {
        return {
            type: "form",
            resModel: "wizard.ir.ui.view.reset.arch",
            context: {
                studio: false,
                studio_report_diff: true,
                active_ids: [this.state.viewIdToDiff],
                active_model: "ir.ui.view",
            },
            afterExecuteActionButton: (model, clickParams) => {
                if (
                    model.root.resModel === "wizard.ir.ui.view.reset.arch" &&
                    clickParams.name === "reset_view_button"
                ) {
                    this.state.reloadSources++;
                    this.reportEditorModel._resetInternalArchs();
                    this.reportEditorModel.loadReportHtml();
                }
            },
            preventCreate: true,
        };
    }

    onResourceChanged(resource) {
        if (this.state.viewIdToDiff) {
            this.state.viewIdToDiff = resource.id;
        }
    }
}
