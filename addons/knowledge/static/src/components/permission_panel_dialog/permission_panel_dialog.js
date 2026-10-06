/** @odoo-module native */
import { PermissionPanel } from "@knowledge/components/permission_panel/permission_panel";
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

/**
 * This component is used exclusively on mobile devices to render the permissions
 * panel within a fullscreen dialog. The fullscreen mode improves usability by
 * providing a more accessible interface for managing article permissions and members.
 */
export class PermissionPanelDialog extends Component {
    static template = "knowledge.PermissionPanelDialog";
    static components = { Dialog, PermissionPanel };
    static props = {
        reactiveRecordWrapper: t.object(),
        openArticle: t.function(),
        sendArticleToTrash: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);
}
