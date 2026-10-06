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

/**
 * Icon creator
 *
 * Component which purpose is to design an app icon. It can be an uploaded image
 * which will be displayed as is, or an icon customized with the help of presets
 * of colors and icon symbols (@see web_studio/static/src/utils for the full list of colors
 * and icon classes).
 * @extends Component
 */
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
     * @param {string} [props.backgroundColor] Background color of the custom
     *      icon.
     * @param {string} [props.color] Color of the custom icon.
     * @param {boolean} props.editable
     * @param {string} [props.iconClass] Font Awesome class of the custom icon.
     * @param {string} props.type 'base64' (if an actual image) or 'custom_icon'.
     * @param {number} [props.uploaded_attachment_id] Databse ID of an uploaded
     *      attachment
     * @param {string} [props.webIconData] Base64-encoded string representing
     *      the icon image.
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

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    onDesignIconClick() {
        this.props.onIconChange(DEFAULT_ICON);
    }

    /**
     * @param {Object[]} files
     */
    async onFileUploaded([file]) {
        if (!file) {
            // Happens when cancelling upload
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
            return; // same value
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
