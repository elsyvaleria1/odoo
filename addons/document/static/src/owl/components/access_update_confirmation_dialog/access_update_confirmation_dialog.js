/** @odoo-module native */
import { t } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { ConfirmationDialog } from "@web/ui/dialog";

const LEVEL_LABELS = {
    view: _t("Viewer"),
    edit: _t("Editor"),
    none: _t("None"),
};
const LEVEL_DESCRIPTIONS = {
    view: _t("Can only view contents. Cannot add, modify, or delete items."),
    edit: _t("Can add, modify, and delete files within this folder."),
};

export class AccessRightsUpdateConfirmationDialog extends ConfirmationDialog {
    static template = "document.AccessRightsUpdateConfirmationDialog";

    static props = {
        ...ConfirmationDialog.props,
        folderName: t.string(),
        changes: t.object({
            access_internal: t.array(t.string()),
            access_via_link: t.or([t.string(), t.literal(false)]),
            documents: t.number(),
            contents: t.number(),
        }),
    };

    get title() {
        return _t("Moving to: %s", this.props.folderName);
    }

    get summary() {
        const { documents, contents } = this.props.changes;
        if (!contents) {
            return _t(
                "Moving the document(s) will change their access rights to the following settings:",
            );
        }
        if (!documents) {
            return _t(
                "Moving will change the access rights of %(contents)s item(s) the moved folder(s) contain to the following settings:",
                { contents },
            );
        }
        return _t(
            "Moving will change the access rights of %(documents)s document(s) and of %(contents)s item(s) they contain to the following settings:",
            { documents, contents },
        );
    }

    get internalLabel() {
        return this.props.changes.access_internal
            .map((level) => LEVEL_LABELS[level])
            .join(" / ");
    }

    get internalDescription() {
        const [level, ...others] = this.props.changes.access_internal;
        if (others.length) {
            return _t("Each document keeps the higher access set on it");
        }
        return (
            LEVEL_DESCRIPTIONS[level] ??
            _t("Only people with access can open with the link")
        );
    }

    get linkLabel() {
        return LEVEL_LABELS[this.props.changes.access_via_link];
    }

    get linkDescription() {
        return (
            LEVEL_DESCRIPTIONS[this.props.changes.access_via_link] ??
            _t("No one on the internet can access")
        );
    }
}
