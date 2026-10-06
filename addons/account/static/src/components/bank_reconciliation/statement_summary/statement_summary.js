/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useSearchModel } from "@web/search/search_model";

export const bankRecStatementSummaryProps = {
    label: t.string(),
    amount: t.string().optional(),
    action: t.function(),
    journalId: t.number().optional(),
    isValid: t.boolean().optional(true),
    journalIsInvalid: t.boolean().optional(),
};

export class BankRecStatementSummary extends Component {
    static template = "account.BankRecStatementSummary";

    static props = bankRecStatementSummaryProps;
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.searchModel = useSearchModel();
    }

    actionApplyInvalidStatement() {
        const facets = this.searchModel.facets;
        const searchItems = this.searchModel.searchItems;
        const invalidStatementFilter = Object.values(searchItems).find(
            (i) => i.name === "invalid_statement",
        );
        const invalidStatementFacet = facets.filter(
            (i) => i.groupId === invalidStatementFilter.groupId,
        );
        if (
            invalidStatementFacet.length === 0 ||
            !invalidStatementFacet[0].values.includes(
                invalidStatementFilter.description,
            )
        ) {
            this.searchModel.toggleSearchItem(invalidStatementFilter.id);
        }
    }
}
