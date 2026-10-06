import { fields, models } from "@web/../tests/web_test_helpers";

export class ApprovalDecisionWizard extends models.ServerModel {
    _name = "wizard.approval.request.decide";

    decision_type = fields.Char();

    _views = {
        form: `
            <form>
                <field name="decision_type"/>
                <footer>
                    <button name="action_confirm_refuse" type="object" string="Refuse"/>
                    <button special="cancel" string="Cancel"/>
                </footer>
            </form>`,
    };
}
