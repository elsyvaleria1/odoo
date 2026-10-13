/** @odoo-module native */
import {
    AutoResizeImage,
    ImageSelector,
} from "@html_editor/main/media/media_dialog/image_selector";
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useChildRef, useService } from "@web/core/utils/hooks";
import { ConfirmationDialog, Dialog } from "@web/ui/dialog";
import { UnsplashError } from "@web_unsplash/unsplash_error/unsplash_error";

export class AutoResizeCover extends AutoResizeImage {
    setup() {
        super.setup();
        this.orm = useService("orm");
    }

    /** @override */
    remove() {
        this.dialogs.add(ConfirmationDialog, {
            body: _t(
                "Are you sure you want to delete this cover? It will be removed from every article it is used in.",
            ),
            confirm: async () => {
                const res = await this.orm.unlink(this.props.model, [this.props.resId]);
                if (res) {
                    this.props.onRemoved(this.props.id, this.props.resId);
                }
            },
        });
    }
}

export class KnowledgeCoverSelector extends ImageSelector {
    static defaultProps = {
        resModel: "knowledge.cover",
        orientation: "landscape",
    };
    static attachmentsListTemplate = "knowledge.CoversListTemplate";
    static components = {
        ...ImageSelector.components,
        AutoResizeCover,
        UnsplashError,
    };
    setup() {
        super.setup();
        this.unsplashService = useService("unsplash");
        this.state.needle = this.props.searchTerm;
        this.searchUnsplash(this.state.needle);
    }

    /** @override */
    get attachmentsDomain() {
        return [
            "&",
            ["res_model", "=", this.props.resModel],
            ["name", "ilike", this.state.needle],
        ];
    }

    /** @override */
    onClickAttachment(attachment) {
        this.props.save(attachment.res_id);
    }

    /** @override */
    onClickRecord(unsplashRecord) {
        this.unsplashService.uploadUnsplashRecords(
            [unsplashRecord],
            { resModel: this.props.resModel },
            async (attachments) => this.onUploaded(attachments[0]),
        );
    }

    /** @override */
    onRemoved(attachmentId, coverId) {
        super.onRemoved(attachmentId);
        if (coverId === this.props.articleCoverId) {
            this.props.save(false);
        }
    }

    /** @override */
    async onUploaded(attachment) {
        const [coverId] = await this.orm.create(this.props.resModel, [
            { attachment_id: attachment.id },
        ]);
        this.props.save(coverId);
    }

    /** @override */
    get selectedAttachmentIds() {
        return [];
    }

    /** @override */
    get selectedRecordIds() {
        return [];
    }
}

export class KnowledgeCoverDialog extends Component {
    static template = "knowledge.KnowledgeCoverDialog";
    static components = {
        KnowledgeCoverSelector,
        Dialog,
    };
    static props = {
        articleCoverId: t.number().optional(),
        articleName: t.string(),
        save: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.size = "xl";
        this.contentClass = "o_select_media_dialog h-100";
        this.modalRef = useChildRef();
    }

    save(coverId) {
        this.props.save(coverId);
        this.props.close();
    }
}
