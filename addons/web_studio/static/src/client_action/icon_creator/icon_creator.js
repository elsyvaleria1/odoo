/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dropdown } from "@web/components/dropdown";
import { FileInput } from "@web/components/file_input";
import { SelectMenu } from "@web/components/select_menu";
import { user } from "@web/core/user";
import { resizeBlobImg } from "@web/core/utils/files";
import { useService } from "@web/core/utils/hooks";
import { FontAwesomeIconSelector } from "@web_studio/client_action/components/font_awesome_icon_selector/font_awesome_icon_selector";
import { BG_COLORS, COLORS } from "@web_studio/utils";

export const DEFAULT_ICON = {
    backgroundColor: BG_COLORS[0],
    color: COLORS[10],
    iconClass: "fa-solid fa-house",
    type: "custom_icon",
};

/** @extends Component */
export class IconCreator extends Component {
    static components = {
        Dropdown,
        FileInput,
        FontAwesomeIconSelector,
        SelectMenu,
    };
    static props = {
        backgroundColor: t.string().optional(DEFAULT_ICON.backgroundColor),
        color: t.string().optional(DEFAULT_ICON.color),
        editable: t.boolean().optional(),
        iconClass: t.string().optional(DEFAULT_ICON.iconClass),
        type: t
            .customValidator(t.any(), (t) => ["base64", "custom_icon"].includes(t))
            .optional(DEFAULT_ICON.type),
        uploaded_attachment_id: t.number().optional(),
        webIconData: t.string().optional(),
        onIconChange: t.function(),
    };
    static template = "web_studio.IconCreator";
    props = useProps(this.constructor.props);

    /**
     * @param {Object} [props]
     * @param {string} [props.backgroundColor]
     * @param {string} [props.color]
     * @param {boolean} props.editable
     * @param {string} [props.iconClass]
     * @param {string} props.type
     * @param {number} [props.uploaded_attachment_id]
     * @param {string} [props.webIconData]
     */
    setup() {
        this.orm = useService("orm");

        const onWillUploadFiles = async (fileList) =>
            Promise.all(
                fileList.map(async (file) => {
                    const blob = await resizeBlobImg(file, { height: 64, width: 64 });
                    return new File([blob], file.name);
                }),
            );
        this.fileInputProps = {
            acceptedFileExtensions: "image/png",
            resModel: "res.users",
            resId: user.userId,
            onWillUploadFiles,
        };
    }

    get backgroundColorChoices() {
        return this.getChoices(BG_COLORS);
    }

    get colorChoices() {
        return this.getChoices(COLORS);
    }

    getChoices(object) {
        return object.map((color) => ({
            label: color,
            value: color,
        }));
    }

    onDesignIconClick() {
        this.props.onIconChange(DEFAULT_ICON);
    }

    /**
     * @param {Object[]} files
     */
    async onFileUploaded([file]) {
        if (!file) {
            return;
        }
        const res = await this.orm.read("ir.attachment", [file.id], ["datas"]);

        this.props.onIconChange({
            type: "base64",
            uploaded_attachment_id: file.id,
            webIconData: "data:image/png;base64," + res[0].datas.replace(/\s/g, ""),
        });
    }

    /**
     * @param {string} palette
     * @param {string} value
     */
    onPaletteItemClick(palette, value) {
        if (this.props[palette] === value) {
            return;
        }
        this.props.onIconChange({
            backgroundColor: this.props.backgroundColor,
            color: this.props.color,
            iconClass: this.props.iconClass,
            type: "custom_icon",
            [palette]: value,
        });
    }
}
