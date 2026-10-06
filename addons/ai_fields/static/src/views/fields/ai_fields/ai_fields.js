/** @odoo-module native */
import { HtmlField, htmlField } from "@html_editor/fields/html_field";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { BooleanField, booleanField } from "@web/fields/basic/boolean/boolean_field";
import { CharField, charField } from "@web/fields/basic/char/char_field";
import { FloatField, floatField } from "@web/fields/basic/float/float_field";
import { IntegerField, integerField } from "@web/fields/basic/integer/integer_field";
import {
    MonetaryField,
    monetaryField,
} from "@web/fields/basic/monetary/monetary_field";
import { TextField, textField } from "@web/fields/basic/text/text_field";
import {
    Many2ManyTagsField,
    many2ManyTagsField,
} from "@web/fields/relational/many2many_tags";
import {
    Many2ManyTagsAvatarField,
    many2ManyTagsAvatarField,
} from "@web/fields/relational/many2many_tags_avatar/many2many_tags_avatar_field";
import {
    buildM2OFieldDescription,
    Many2OneField,
} from "@web/fields/relational/many2one";
import {
    Many2OneAvatarField,
    many2OneAvatarField,
} from "@web/fields/relational/many2one_avatar/many2one_avatar_field";
import {
    SelectionField,
    selectionField,
} from "@web/fields/selection/selection/selection_field";
import { dateField, DateTimeField, dateTimeField } from "@web/fields/temporal/datetime";

const AiFieldMixin = (fieldClass) =>
    class extends fieldClass {
        setup() {
            super.setup();
            this.notification = useService("notification");
        }

        get isAiComputed() {
            return this.props.record.fields[this.props.name].ai;
        }

        async onAiClick() {
            await this.props.record.computeAiField(this.props.name);
        }
    };

class AiBooleanField extends AiFieldMixin(BooleanField) {
    static template = "ai_fields.AiBooleanField";
}

const aiBooleanField = {
    ...booleanField,
    component: AiBooleanField,
    displayName: _t("AI Checkbox"),
};

registry.category("fields").add("ai_boolean", aiBooleanField);

class AiCharField extends AiFieldMixin(CharField) {
    static template = "ai_fields.AiCharField";
}

const aiCharField = {
    ...charField,
    component: AiCharField,
    displayName: _t("AI Text"),
};

registry.category("fields").add("ai_char", aiCharField);

class AiDateTimeField extends AiFieldMixin(DateTimeField) {
    static template = "ai_fields.AiDateTimeField";
}

const aiDateField = {
    ...dateField,
    component: AiDateTimeField,
    displayName: _t("AI Date"),
};

registry.category("fields").add("ai_date", aiDateField);

const aiDateTimeField = {
    ...dateTimeField,
    component: AiDateTimeField,
    displayName: _t("AI Date & Time"),
};

registry.category("fields").add("ai_datetime", aiDateTimeField);

class AiFloatField extends AiFieldMixin(FloatField) {
    static template = "ai_fields.AiFloatField";
}

const aiFloatField = {
    ...floatField,
    component: AiFloatField,
    displayName: _t("AI Float"),
};

registry.category("fields").add("ai_float", aiFloatField);

class AiHtmlField extends AiFieldMixin(HtmlField) {
    static template = "ai_fields.AiHtmlField";
}

const aiHtmlField = {
    ...htmlField,
    additionalClasses: ["o_field_html"],
    component: AiHtmlField,
    displayName: _t("AI Html"),
};

registry.category("fields").add("ai_html", aiHtmlField);

class AiIntegerField extends AiFieldMixin(IntegerField) {
    static template = "ai_fields.AiIntegerField";
}

const aiIntegerField = {
    ...integerField,
    component: AiIntegerField,
    displayName: _t("AI Integer"),
};

registry.category("fields").add("ai_integer", aiIntegerField);

class AiMany2ManyTagsAvatarField extends AiFieldMixin(Many2ManyTagsAvatarField) {
    static template = "ai_fields.AiMany2ManyTagsAvatarField";
}

const aiMany2ManyTagsAvatarField = {
    ...many2ManyTagsAvatarField,
    component: AiMany2ManyTagsAvatarField,
    displayName: _t("AI Many2Many Tags Avatar"),
};

registry.category("fields").add("ai_many2many_tags_avatar", aiMany2ManyTagsAvatarField);

class AiMany2ManyTagsField extends AiFieldMixin(Many2ManyTagsField) {
    static template = "ai_fields.AiMany2ManyTagsField";
}

const aiMany2ManyTagsField = {
    ...many2ManyTagsField,
    component: AiMany2ManyTagsField,
    displayName: _t("AI Many2Many Tags"),
};

registry.category("fields").add("ai_many2many_tags", aiMany2ManyTagsField);

class AiMany2OneAvatarField extends AiFieldMixin(Many2OneAvatarField) {
    static template = "ai_fields.AiMany2OneAvatarField";
}

const aiMany2OneAvatarField = {
    ...many2OneAvatarField,
    component: AiMany2OneAvatarField,
    displayName: _t("AI Many2One"),
};

registry.category("fields").add("ai_many2one_avatar", aiMany2OneAvatarField);

class AiMany2OneField extends AiFieldMixin(Many2OneField) {
    static template = "ai_fields.AiMany2OneField";
}

const aiMany2OneField = {
    ...buildM2OFieldDescription(AiMany2OneField),
    displayName: _t("AI Many2One"),
};

registry.category("fields").add("ai_many2one", aiMany2OneField);

class AiMonetaryField extends AiFieldMixin(MonetaryField) {
    static template = "ai_fields.AiMonetaryField";
}

const aiMonetaryField = {
    ...monetaryField,
    component: AiMonetaryField,
    displayName: _t("AI Monetary"),
};

registry.category("fields").add("ai_monetary", aiMonetaryField);

class AiSelectionField extends AiFieldMixin(SelectionField) {
    static template = "ai_fields.AiSelectionField";
}

const aiSelectionField = {
    ...selectionField,
    component: AiSelectionField,
    displayName: _t("AI Selection"),
};

registry.category("fields").add("ai_selection", aiSelectionField);

class AiTextField extends AiFieldMixin(TextField) {
    static template = "ai_fields.AiTextField";
}

const aiTextField = {
    ...textField,
    additionalClasses: ["o_field_text"],
    component: AiTextField,
    displayName: _t("AI Text"),
};

registry.category("fields").add("ai_text", aiTextField);
