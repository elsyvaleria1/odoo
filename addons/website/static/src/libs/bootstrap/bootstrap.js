/** @odoo-module native */

import { Dropdown } from "@web/libs/bootstrap";

const bsGetOffsetFunction = Dropdown.prototype._getOffset;
Dropdown.prototype._getOffset = function () {
    const offset = bsGetOffsetFunction.apply(this, arguments);
    if (this._element.closest(".o_hoverable_dropdown .navbar")) {
        return [offset[0], 0];
    }
    return offset;
};
