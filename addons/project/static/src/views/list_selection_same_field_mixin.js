/** @odoo-module native */
import { getRawValue } from "@web/views/kanban";

export const ListSelectionSameFieldMixin = (T) =>
    class ListSelectionSameField extends T {
        static rowsDependOnSelection = true;

        /** @returns {boolean} */
        haveAllSelectedSameField(field) {
            this._sameFieldCache ??= {};
            if (!(field in this._sameFieldCache)) {
                const selection = this.props.list.selection;
                const value = selection.length && getRawValue(selection[0], field);
                this._sameFieldCache[field] = selection.every(
                    (record) => getRawValue(record, field) === value,
                );
                Promise.resolve().then(() => {
                    delete this._sameFieldCache;
                });
            }
            return this._sameFieldCache[field];
        }
    };
