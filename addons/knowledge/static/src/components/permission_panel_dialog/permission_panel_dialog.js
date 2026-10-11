/** @odoo-module native */
import { PermissionPanel } from "@knowledge/components/permission_panel/permission_panel";
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

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
