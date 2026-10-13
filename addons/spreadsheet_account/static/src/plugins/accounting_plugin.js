/** @odoo-module native */
// @ts-check

import { EvaluationError } from "@odoo/o-spreadsheet";
import { camelToSnakeObject, toServerDateString } from "@spreadsheet/helpers/helpers";
import { OdooUIPlugin } from "@spreadsheet/plugins";
import { _t } from "@web/core/translation";
import { deepCopy } from "@web/core/utils/collections/objects";

/**
 * @typedef {import("@spreadsheet/helpers/period").DateRange} DateRange
 */

export class AccountingPlugin extends OdooUIPlugin {
    static getters = /** @type {const} */ ([
        "getAccountPrefixCredit",
        "getAccountPrefixDebit",
        "getAccountGroupCodes",
        "getFiscalStartDate",
        "getFiscalEndDate",
        "getAccountResidual",
        "getAccountPartnerData",
        "getAccountTagData",
    ]);
    constructor(config) {
        super(config);
        /** @type {import("@spreadsheet/data_sources/server_data").ServerData} */
        this._serverData = config.custom.odooDataProvider?.serverData;
    }

    get serverData() {
        if (!this._serverData) {
            throw new Error(
                "'serverData' is not defined, please make sure a 'OdooDataProvider' instance is provided to the model.",
            );
        }
        return this._serverData;
    }

    /**
     * @param {string[]} codes
     * @param {DateRange} dateRange
     * @param {number} offset
     * @param {number | null} companyId
     * @param {boolean} includeUnposted
     * @returns {number}
     */
    getAccountPrefixCredit(codes, dateRange, offset, companyId, includeUnposted) {
        const data = this._fetchAccountData(
            codes,
            dateRange,
            offset,
            companyId,
            includeUnposted,
        );
        return data.credit;
    }

    /**
     * @param {string[]} codes
     * @param {DateRange} dateRange
     * @param {number} offset
     * @param {number | null} companyId
     * @param {boolean} includeUnposted
     * @returns {number}
     */
    getAccountPrefixDebit(codes, dateRange, offset, companyId, includeUnposted) {
        const data = this._fetchAccountData(
            codes,
            dateRange,
            offset,
            companyId,
            includeUnposted,
        );
        return data.debit;
    }

    /**
     * @param {Date} date
     * @param {number | null} companyId
     * @returns {string | undefined}
     */
    getFiscalStartDate(date, companyId) {
        return this._fetchCompanyData(date, companyId).start;
    }

    /**
     * @param {Date} date
     * @param {number | undefined} companyId
     * @returns {string | undefined}
     */
    getFiscalEndDate(date, companyId) {
        return this._fetchCompanyData(date, companyId).end;
    }

    /**
     * @param {string} accountType
     * @returns {string[]}
     */
    getAccountGroupCodes(accountType) {
        return this.serverData.batch.get(
            "account.account",
            "get_account_group",
            accountType,
        );
    }

    /**
     * @private
     * @param {string[]} codes
     * @param {DateRange} dateRange
     * @param {number} offset
     * @param {number | null} companyId
     * @param {boolean} includeUnposted
     * @returns {{ debit: number, credit: number }}
     */
    _fetchAccountData(codes, dateRange, offset, companyId, includeUnposted) {
        dateRange = deepCopy(dateRange);
        dateRange.year += offset;
        if (dateRange.year < 1900) {
            throw new EvaluationError(_t("%s is not a valid year.", dateRange.year));
        }
        return this.serverData.batch.get(
            "account.account",
            "spreadsheet_fetch_debit_credit",
            camelToSnakeObject({ dateRange, codes, companyId, includeUnposted }),
        );
    }

    /**
     * @private
     * @param {Date} date
     * @param {number | null} companyId
     * @returns {{start: string, end: string}}
     */
    _fetchCompanyData(date, companyId) {
        const result = this.serverData.batch.get("res.company", "get_fiscal_dates", {
            date: toServerDateString(date),
            company_id: companyId,
        });
        if (result === false) {
            throw new EvaluationError(
                _t("The company fiscal year could not be found."),
            );
        }
        return result;
    }

    /**
     * @param {string[]} codes
     * @param {DateRange} dateRange
     * @param {number} offset
     * @param {number} companyId
     * @param {boolean} includeUnposted
     * @returns {number | undefined}
     */
    getAccountResidual(codes, dateRange, offset, companyId, includeUnposted) {
        dateRange = deepCopy(dateRange);
        dateRange.year += offset;
        if (dateRange.year < 1900) {
            throw new EvaluationError(_t("%s is not a valid year.", dateRange.year));
        }
        const result = this.serverData.batch.get(
            "account.account",
            "spreadsheet_fetch_residual_amount",
            camelToSnakeObject({ codes, dateRange, companyId, includeUnposted }),
        );
        if (result === false) {
            throw new EvaluationError(
                _t("The residual amount for given accounts could not be computed."),
            );
        }
        return result.amount_residual;
    }

    /**
     * @private
     * @param {string[]} codes
     * @param {DateRange} dateRange
     * @param {number} offset
     * @param {number | null} companyId
     * @param {boolean} includeUnposted
     * @param {number[]} partnerIds
     * @returns {number | undefined}
     */
    getAccountPartnerData(
        codes,
        dateRange,
        offset,
        companyId,
        includeUnposted,
        partnerIds,
    ) {
        dateRange = deepCopy(dateRange);
        dateRange.year += offset;
        if (dateRange.year < 1900) {
            throw new EvaluationError(_t("%s is not a valid year.", dateRange.year));
        }
        const result = this.serverData.batch.get(
            "account.account",
            "spreadsheet_fetch_partner_balance",
            camelToSnakeObject({
                dateRange,
                codes,
                companyId,
                includeUnposted,
                partnerIds,
            }),
        );
        if (result === false) {
            throw new EvaluationError(
                _t("The balance for given partners could not be computed."),
            );
        }
        return result.balance;
    }

    /**
     * @private
     * @param {number[]} accountTagIds
     * @param {DateRange} dateRange
     * @param {number} offset
     * @param {number | null} companyId
     * @param {boolean} includeUnposted
     * @returns {number | undefined}
     */
    getAccountTagData(accountTagIds, dateRange, offset, companyId, includeUnposted) {
        dateRange = deepCopy(dateRange);
        dateRange.year += offset;
        if (dateRange.year < 1900) {
            throw new EvaluationError(_t("%s is not a valid year.", dateRange.year));
        }
        const result = this.serverData.batch.get(
            "account.account",
            "spreadsheet_fetch_balance_tag",
            camelToSnakeObject({
                accountTagIds,
                dateRange,
                companyId,
                includeUnposted,
            }),
        );
        if (result === false) {
            throw new EvaluationError(
                _t("The balance for given account tag could not be computed."),
            );
        }
        return result.balance;
    }
}
