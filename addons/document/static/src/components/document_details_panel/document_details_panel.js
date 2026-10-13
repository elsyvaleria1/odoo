/** @odoo-module native */
import { DocumentsDetailsMany2ManyTagsField } from "@document/views/fields/document_details_many2many_tags/document_details_many2many_tags_field";
import { DocumentsDetailsMany2OneField } from "@document/views/fields/document_details_many2one/document_details_many2one_field";
import { DocumentsTypeIcon } from "@document/views/fields/document_type_icon/document_type_icon";
import { UserFolder } from "@document/views/utils";
import { Component, proxy, status, t, useProps } from "@odoo/owl";
import { ModelSelector } from "@web/components/model_selector";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { humanSize } from "@web/core/utils/format/binary";
import { useService } from "@web/core/utils/hooks";
import { CharField } from "@web/fields/basic/char/char_field";
import { Many2OneField } from "@web/fields/relational/many2one";
import { Many2OneAvatarField } from "@web/fields/relational/many2one_avatar/many2one_avatar_field";
import { SelectCreateDialog } from "@web/views/view_dialogs";

export class DocumentsDetailsPanel extends Component {
    static components = {
        CharField,
        DocumentsDetailsMany2ManyTagsField,
        DocumentsDetailsMany2OneField,
        DocumentsTypeIcon,
        Many2OneAvatarField,
        Many2OneField,
        ModelSelector,
    };
    static props = { record: t.object(), nbViewItems: t.number().optional() };
    static template = "document.DocumentsDetailsPanel";
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        /** @type {import("@document/core/document_service").DocumentService} */
        this.documentService = useService("document.document");
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.state = proxy({ pendingModel: null, models: [] });
        this.documentService.getDetailsPanelResModels().then((models) => {
            if (status(this) !== "destroyed") {
                this.state.models = models;
            }
        });
    }

    get record() {
        return wrapAsDetailsPanelRecord(this.props.record);
    }

    get resModel() {
        return this.state.pendingModel?.technical || this.record.data.res_model;
    }

    get resModelName() {
        if (this.state.pendingModel) {
            return this.state.pendingModel.label || "";
        }
        return this.record.data.res_model ? this.record.data.res_model_name || "" : "";
    }

    async openLinkedRecord() {
        const { res_model, res_id } = this.record.data || {};
        if (!res_id?.resId || !res_model) {
            return;
        }
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_id: res_id.resId,
            res_model,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openAccessLog() {
        const action = await this.orm.call(
            "document.document",
            "action_view_access_log",
            [this.record.resId],
        );
        return this.action.doAction(action);
    }

    get canViewAccessLog() {
        return this.documentService.userIsDocumentManager && !!this.record.resId;
    }

    get userPermissionViewOnly() {
        return (
            Boolean(this.record.data?.is_locked_by_other) ||
            this.record.data?.user_permission !== "edit" ||
            (!this.documentService.userIsDocumentManager &&
                this.record.data?.user_folder_id === UserFolder.COMPANY)
        );
    }

    get fileSize() {
        const data = this.record.data;
        const isFolderTotal = this.props.record.isContainer;
        if (data.type === "folder" && !isFolderTotal) {
            return "";
        }
        const nBytes = data.file_size || 0;
        if (!nBytes) {
            return "";
        }
        return `${isFolderTotal ? "~" : ""}${humanSize(nBytes)}`;
    }

    get rootFolderPlaceholder() {
        return {
            MY: _t("My Drive"),
            COMPANY: _t("Company"),
            SHARED: _t("Shared with me"),
        }[this.props.record.data?.user_folder_id];
    }

    get multiCompany() {
        return user.allowedCompanies.length > 1;
    }

    get canCreateAliasDomain() {
        return user.isAdmin;
    }

    get canCreateActivityType() {
        return user.isSystem;
    }

    get activeCompanies() {
        return user.activeCompanies.map((c) => c.id);
    }

    async onModelSelected(value) {
        if (!value.technical) {
            this.state.pendingModel = null;
            await this.record.update(
                { res_id: false, res_model: false },
                { save: true },
            );
            return;
        }
        this.state.pendingModel = value;
        this.dialog.add(
            SelectCreateDialog,
            {
                title: _t("Select a Record To Link"),
                noCreate: true,
                multiSelect: false,
                resModel: value.technical,
                onSelected: async ([resId]) => {
                    if (resId) {
                        await this.record.update(
                            { res_id: resId, res_model: value.technical },
                            { save: true },
                        );
                    }
                },
            },
            { onClose: () => (this.state.pendingModel = null) },
        );
    }

    async onRecordReset() {
        await this.onModelSelected({ technical: false, label: false });
    }
}

const detailsPanelRecords = new WeakMap();

/**
 * @param {Object} record
 * @returns {Object}
 */
function wrapAsDetailsPanelRecord(record) {
    let wrapped = detailsPanelRecords.get(record);
    if (!wrapped) {
        wrapped = new Proxy(record, {
            get(target, prop, receiver) {
                if (prop === "isDetailsPanelRecord") {
                    return true;
                }
                if (prop === "selected") {
                    return false;
                }
                return Reflect.get(target, prop, receiver);
            },
        });
        detailsPanelRecords.set(record, wrapped);
    }
    return wrapped;
}
