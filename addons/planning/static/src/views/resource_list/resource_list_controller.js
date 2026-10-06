/** @odoo-module native */
import { _t } from "@web/core/translation";
import { ListController } from "@web/views/list";

export class ResourceListController extends ListController {
    /**
     * @override
     */
    get archiveDialogProps() {
        const result = super.archiveDialogProps;
        result["body"] = _t(
            "Archiving this resource will transform all of its future shifts into open shifts. Are you sure you want to continue?",
        );
        return result;
    }
}
