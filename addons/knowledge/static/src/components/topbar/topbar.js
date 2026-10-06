/** @odoo-module native */
import KnowledgeHierarchy from "@knowledge/components/hierarchy/hierarchy";
import { OptionsDropdown } from "@knowledge/components/options_dropdown/options_dropdown";
import { PermissionPanel } from "@knowledge/components/permission_panel/permission_panel";
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useRecordObserver } from "@web/fields/hooks/record_observer";
import { usePopover } from "@web/ui/popover";
import { standardWidgetProps } from "@web/views/widgets";

import { PermissionPanelDialog } from "../permission_panel_dialog/permission_panel_dialog.js";

class KnowledgeTopbar extends Component {
    static template = "knowledge.KnowledgeTopbar";
    static props = standardWidgetProps;
    static components = {
        KnowledgeHierarchy,
        OptionsDropdown,
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
        this.ui = useService("ui");

        this.dialog = useService("dialog");
        this.permissionPopover = usePopover(PermissionPanel, {
            closeOnClickAway: true,
            arrow: false,
            onClose: () => (this.state.shareBtnIsActive = false),
            position: "bottom-end",
        });
        this.state = proxy({
            shareBtnIsActive: false,
        });
        this.commentsState = proxy(this.knowledgeContext.commentsState);
        this.chatterPanelState = proxy(this.knowledgeContext.chatterPanelState);
        this.propertiesPanelState = proxy(this.knowledgeContext.propertiesPanelState);

        onWillStart(async () => {
            this.isInternalUser = await user.hasGroup("base.group_user");
        });

        this.reactiveRecordWrapper = proxy({ record: this.props.record });
        useRecordObserver((record) => {
            this.reactiveRecordWrapper.record = record;
        });
    }

    get chatterButtonTitle() {
        return this.chatterPanelState.isDisplayed
            ? _t("Close chatter panel")
            : _t("Open chatter panel");
    }

    get commentButtonTitle() {
        return this.commentsState.isDisplayed
            ? _t("Close comments panel")
            : _t("Open comments panel");
    }

    get favoriteButtonTitle() {
        return this.props.record.data.is_user_favorite
            ? _t("Remove from favorites")
            : _t("Add to favorites");
    }

    togglePermissionPanel(event) {
        if (this.ui.isSmall && !this.state.shareBtnIsActive) {
            this.dialog.add(PermissionPanelDialog, {
                reactiveRecordWrapper: this.reactiveRecordWrapper,
                openArticle: this.knowledgeContext.openArticle,
                sendArticleToTrash: this.knowledgeContext.sendArticleToTrash,
            });
        } else if (this.permissionPopover.isOpen) {
            this.permissionPopover.close();
        } else {
            if (this.props.record.dirty) {
                this.props.record.save();
            }
            this.permissionPopover.open(event.currentTarget, {
                reactiveRecordWrapper: this.reactiveRecordWrapper,
                openArticle: this.knowledgeContext.openArticle,
                sendArticleToTrash: this.knowledgeContext.sendArticleToTrash,
            });
            this.state.shareBtnIsActive = true;
        }
    }
}

export const knowledgeTopbar = {
    component: KnowledgeTopbar,
    fieldDependencies: [
        { name: "create_uid", type: "many2one", relation: "res.users" },
        { name: "display_name", type: "char" },
        { name: "last_edition_uid", type: "many2one", relation: "res.users" },
        { name: "active", type: "boolean" },
        { name: "article_properties", type: "jsonb" },
        { name: "cover_image_id", type: "many2one", relation: "knowledge.cover" },
        { name: "full_width", type: "boolean" },
        { name: "icon", type: "char" },
        { name: "inherited_permission", type: "char" },
        {
            name: "inherited_permission_parent_id",
            type: "many2one",
            relation: "knowledge.article",
        },
        { name: "is_article_item", type: "boolean" },
        { name: "is_locked", type: "boolean" },
        { name: "is_desynchronized", type: "boolean" },
        { name: "is_user_favorite", type: "boolean" },
        { name: "name", type: "char" },
        { name: "parent_id", type: "char" },
        { name: "parent_path", type: "char" },
        { name: "root_article_id", type: "many2one", relation: "knowledge.article" },
        { name: "has_item_parent", type: "boolean" },
        { name: "is_listed_in_templates_gallery", type: "boolean" },
        { name: "to_delete", type: "boolean" },
        { name: "user_can_write", type: "boolean" },
    ],
};

registry.category("view_widgets").add("knowledge_topbar", knowledgeTopbar);
