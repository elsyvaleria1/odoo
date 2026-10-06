// @ts-check
/** @odoo-module native */
import { Record } from "@mail/core/common/record";

export class ResLang extends Record {
    static id = "id";
    static _name = "res.lang";

    /** @type {number} */
    id;
    /** @type {string} */
    name;
    /** @type {string} */
    code;

    get baseCode() {
        return this.code ? this.code.split(/[_@]/)[0] : undefined;
    }
}

ResLang.register();
