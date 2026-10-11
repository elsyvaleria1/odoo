/** @odoo-module native */
import {
    Component,
    onMounted,
    onWillStart,
    proxy,
    t,
    useListener,
    useProps,
} from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

export class SignItemCustomPopover extends Component {
    static template = "sign.SignItemCustomPopover";
    static components = {};
    static props = {
        id: t.number(),
        alignment: t.string(),
        header_title: t.string(),
        placeholder: t.string(),
        required: t.boolean(),
        constant: t.boolean(),
        option_ids: t.array(),
        onValidate: t.function(),
        type: t.string(),
        onDelete: t.function(),
        onDuplicate: t.function(),
        onClose: t.function(),
        debug: t.string(),
        close: t.function(),
        onCopyItem: t.function(),
        num_options: t.number().optional(),
        radio_set_id: t.number().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.alignmentOptions = [
            { title: _t("Left"), key: "left" },
            { title: _t("Center"), key: "center" },
            { title: _t("Right"), key: "right" },
        ];
        this.state = proxy({
            alignment: this.props.alignment,
            placeholder: this.props.placeholder,
            constant: this.props.constant,
            required: this.props.required,
            option_ids: this.props.option_ids,
            num_options: this.props.num_options,
            radio_set_id: this.props.radio_set_id,
            selectionOptionsText: "",
        });
        this.orm = useService("orm");
        onWillStart(async () => {
            const options = await this.orm.searchRead("sign.item.option", [
                ["id", "in", this.props.option_ids],
            ]);
            this.state.selectionOptionsText = options
                .map((option) => option.value)
                .join("\n");
        });

        onMounted(() => {
            if (this.props.type === "selection") {
                const textarea = document.querySelector(
                    ".o_sign_selection_input_option textarea",
                );
                if (textarea) {
                    textarea.focus();
                }
            }
        });

        this.notification = useService("notification");
        this.typesWithAlignment = new Set(["text", "textarea"]);
        useListener(window, "keydown", this.onGlobalKeyDown.bind(this), {
            capture: true,
        });
    }

    onGlobalKeyDown(event) {
        const target = event.target;
        if (
            target.isContentEditable ||
            ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
        ) {
            return;
        }
        if (event.key === "c" && (event.ctrlKey || event.metaKey)) {
            this.notification.add(_t("Sign Item Copied"), { type: "success" });
            this.props.onCopyItem(this.props.id);
        } else if (event.key === "Delete") {
            this.props.onDelete();
        }
    }

    handleNumOptionsChange(value) {
        if (Number(value) < 2) {
            return;
        }
        this.state["num_options"] = Number(value);
    }

    onChange(key, value) {
        this.state[key] = value;

        if (key === "constant") {
            if (value) {
                document.querySelector("#o_sign_name")?.focus();
            } else {
                this.state.placeholder = this.props.placeholder;
            }
        }
    }

    async onValidate() {
        if (this.props.type === "selection" && !this.state.selectionOptionsText) {
            this.notification.add(
                _t("Selection field cannot be empty. Please add at least one option."),
                {
                    type: "warning",
                },
            );
            return;
        }

        const options = this.state.selectionOptionsText
            .split("\n")
            .map((opt) => opt.trim())
            .filter((opt) => opt);
        this.state.option_ids = await this.orm.call(
            "sign.item.option",
            "get_or_create_option_ids",
            [options],
        );
        this.props.onValidate(this.state);
    }

    get showAlignment() {
        return this.typesWithAlignment.has(this.props.type);
    }

    onChangeSelectionOptions(value) {
        this.state.selectionOptionsText = value;
    }
}
