/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { useService } from "@web/core/utils/hooks";
import { ActionMenus } from "@web/search/action_menus/action_menus";
import { SIZES } from "@web/ui/viewport";

export class DocumentsAction extends Component {
    static template = "document.DocumentsAction";
    static components = {
        ActionMenus,
        Dropdown,
        DropdownItem,
    };
    static props = {
        targetRecords: t.array(),
        folderId: t.or([t.string(), t.number(), t.boolean()]),
        isPreview: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.documentService = useService("document.document");
        this.ui = proxy(useService("ui"));
        this.selectionActions = proxy(this.documentService.selectionActions);
    }

    get selection() {
        return this.selectionActions.provider?.();
    }

    get topbarActions() {
        const selection = this.selection;
        if (!selection) {
            return [];
        }
        return Object.values(selection.getTopbarActions())
            .sort((a, b) => a.groupNumber - b.groupNumber)
            .filter((action) => !action.isAvailable || action.isAvailable());
    }

    get actionMenuProps() {
        const selection = this.props.isPreview && this.selection;
        if (!selection) {
            return null;
        }
        const actionMenuProps = selection.getMenuProps();
        actionMenuProps.items.action = actionMenuProps.items.action.filter(
            this.isPreviewAction,
        );
        const previewedIds = this.props.targetRecords
            .filter(Boolean)
            .map((record) => record.resId);
        return {
            ...actionMenuProps,
            getActiveIds: () => previewedIds,
            isDomainSelected: false,
        };
    }

    get visibleTopbarActions() {
        return this.ui.size >= SIZES.XL ? 3 : 2;
    }

    isPreviewAction(action) {
        return action.key !== "export";
    }
}
