/** @odoo-module native */
import { useCapTableSampleData } from "@equity/components/cap_table/cap_table_sample_data";
import { Component, markup, onWillStart, proxy, useProps } from "@odoo/owl";
import {
    formatFieldFloat,
    formatMonetary,
    formatPercentage,
} from "@web/core/formatters";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { EmptyState } from "@web/views/empty_state/empty_state";
import { standardActionServiceProps } from "@web/webclient/actions";

export class CapTable extends Component {
    static template = "equity.CapTable";
    static props = { ...standardActionServiceProps };
    static components = { EmptyState, ControlPanel };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();

        this.orm = useService("orm");
        this.action = useService("action");
        this.partnerHolderData = proxy({});
        this.partnerClassesIds = proxy({});
        this.partnerData = proxy({});
        this.classData = proxy({});
        this.isSample = false;
        this.sampleData = useCapTableSampleData();

        onWillStart(async () => {
            let res = await this.orm.call("equity.cap.table", "get_cap_table_data", [
                this.props.action.context?.active_ids || [],
            ]);
            if (Object.keys(res["partner_holder_data"]).length === 0) {
                // no data, then use sample data
                res = this.sampleData.getSampleData();
                this.isSample = true;
            }
            this.partnerHolderData = res["partner_holder_data"];
            this.partnerClassesIds = res["partner_classes_ids"];
            this.partnerData = res["partner_data"];
            this.classData = res["class_data"];
        });
    }

    createTransaction() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "equity.transaction",
            target: "current",
            views: [[false, "form"]],
        });
    }

    async sendToPartner(partnerId) {
        const action = await this.orm.call(
            "res.partner",
            "action_partner_equity_send",
            [parseInt(partnerId)],
        );
        this.action.doAction(action);
    }

    openRecord(resModel, resId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            res_id: parseInt(resId),
            views: [[false, "form"]],
            target: "current",
        });
    }

    openTransactions(partnerId, holderId, classId, totalCell = false) {
        const domain = [["partner_id", "=", parseInt(partnerId)]];

        if (holderId && !isNaN(holderId)) {
            holderId = parseInt(holderId);
            domain.push(
                "|",
                ["subscriber_id", "=", holderId],
                ["seller_id", "=", holderId],
            );
        } else if (!totalCell) {
            domain.push(["subscriber_id", "=", false]);
        }
        if (classId && !isNaN(classId)) {
            domain.push(
                "|",
                ["security_class_id", "=", parseInt(classId)],
                ["destination_class_id", "=", parseInt(classId)],
            );
        }

        this.action.doAction({
            name: _t("Transactions"),
            type: "ir.actions.act_window",
            res_model: "equity.transaction",
            domain,
            target: "current",
            views: [
                [false, "list"],
                [false, "form"],
            ],
        });
    }

    getHeadersLength(partnerId) {
        return this.partnerClassesIds[partnerId].length + 6;
    }

    getHeaders(partnerId) {
        return [
            {
                label: this.partnerData[partnerId]["display_name"],
                onClick: () => this.openRecord("res.partner", partnerId),
            },
            ...this.partnerClassesIds[partnerId].map((classId) => ({
                label: this.classData[classId]["display_name"],
            })),
            { label: _t("Total") },
            { label: _t("Ownership") },
            { label: _t("Voting Rights") },
            { label: _t("Dividend Payout") },
            { label: _t("Fully Diluted") },
            { label: _t("Valuation") },
        ];
    }

    getSecurities(partnerId, holderId, classId) {
        let res = 0;
        const partnerHolderData = this.partnerHolderData[partnerId];
        for (const innerHolderId of Object.keys(partnerHolderData)) {
            if (!holderId || innerHolderId === String(holderId)) {
                const innerHolderRow = partnerHolderData[innerHolderId]["classes"];
                for (const innerClassId of Object.keys(innerHolderRow)) {
                    if (!classId || innerClassId === String(classId)) {
                        res += innerHolderRow[innerClassId];
                    }
                }
            }
        }
        return formatFieldFloat(res, { trailingZeros: false });
    }

    getStat(partnerId, holderId, statName) {
        let res = 0;
        const partnerHolderData = this.partnerHolderData[partnerId];
        for (const innerHolderId of Object.keys(partnerHolderData)) {
            if (!holderId || innerHolderId === String(holderId)) {
                res += partnerHolderData[innerHolderId][statName];
            }
        }
        return res;
    }

    getOwnership(partnerId, holderId) {
        return formatPercentage(this.getStat(partnerId, holderId, "ownership"));
    }

    getVotingRights(partnerId, holderId) {
        return formatPercentage(this.getStat(partnerId, holderId, "voting_rights"));
    }

    getDividendPayout(partnerId, holderId) {
        return formatPercentage(this.getStat(partnerId, holderId, "dividend_payout"));
    }

    getDilution(partnerId, holderId) {
        return formatPercentage(this.getStat(partnerId, holderId, "dilution"));
    }

    getValuation(partnerId, holderId) {
        const res = this.getStat(partnerId, holderId, "valuation");
        return formatMonetary(res, {
            currencyId: this.partnerData[partnerId]["equity_currency_id"],
        });
    }

    getRow(partnerId, holderId, totalLabel = false) {
        const totalSecurities = this.getSecurities(partnerId, holderId, null);

        if (!totalSecurities && !totalLabel) {
            return null;
        }

        return [
            {
                partnerId: !isNaN(holderId) && holderId,
                label:
                    totalLabel ||
                    (!isNaN(holderId) && this.partnerData[holderId]["display_name"]) ||
                    _t("Unassigned"),
                onClick:
                    holderId && !isNaN(holderId)
                        ? () => this.openRecord("res.partner", holderId)
                        : null,
            },
            ...this.partnerClassesIds[partnerId].map((classId) => ({
                label: this.getSecurities(partnerId, holderId, classId) || "",
                onClick: () =>
                    this.openTransactions(
                        partnerId,
                        holderId,
                        classId,
                        Boolean(totalLabel),
                    ),
            })),
            {
                label: totalSecurities,
                onClick: () =>
                    this.openTransactions(
                        partnerId,
                        holderId,
                        null,
                        Boolean(totalLabel),
                    ),
            },
            { label: this.getOwnership(partnerId, holderId) },
            { label: this.getVotingRights(partnerId, holderId) },
            { label: this.getDividendPayout(partnerId, holderId) },
            { label: this.getDilution(partnerId, holderId) },
            { label: this.getValuation(partnerId, holderId) },
        ];
    }

    getPartnerAvatarSrc(partnerId) {
        if (this.isSample) {
            return `/base/static/img/res_partner_address_${partnerId}.jpg`;
        }
        return `/web/image?model=res.partner&field=avatar_128&id=${partnerId}`;
    }

    get noContentHelp() {
        const helpTitle = _t("No shareholders yet!");
        const helpDescription = _t(
            "Manage transactions, equity, cap table, and shareholders.",
        );
        return markup`<p class="o_view_nocontent_smiling_face">${helpTitle}</p><p>${helpDescription}</p>`;
    }
}

registry.category("actions").add("equity.CapTable", CapTable);
