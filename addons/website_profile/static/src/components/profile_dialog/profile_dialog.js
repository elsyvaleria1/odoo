/** @odoo-module native */
import { endPos } from "@html_editor/utils/position";
import { Wysiwyg } from "@html_editor/wysiwyg";
import {
    Component,
    markup,
    observe,
    onMounted,
    onWillStart,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { FileUploader } from "@web/core/file_upload";
import { localization } from "@web/core/l10n/localization";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { isHtmlEmpty } from "@web/core/utils/dom/html";
import { elementRef } from "@web/core/utils/element_ref";
import { isEmail } from "@web/core/utils/format/strings";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

export class ProfileDialog extends Component {
    static template = "website_profile.ProfileDialog";
    static components = {
        Dialog,
        FileUploader,
        Wysiwyg,
    };
    static props = {
        close: t.function(),
        confirm: t.function().optional(() => () => {}),
        focusWebsiteDescription: t.boolean().optional(false),
        userId: t.number(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.debug = useDebugMode();
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.upload = elementRef();
        this.profileImg = elementRef();
        this.profileImgData = null;
        this.state = proxy({
            isProcessing: false,
            hasError: false,
            emailHasError: false,
            nameHasError: false,
        });
        const websiteDescriptionClass =
            "website_profile_profile_dialog_website_description";
        this.nameRef = elementRef();
        useAutofocus({ ref: this.nameRef });

        onWillStart(async () => {
            const [users, countries] = await Promise.all([
                this.orm.read(
                    "res.users",
                    [this.props.userId],
                    [
                        "city",
                        "country_id",
                        "email",
                        "name",
                        "website",
                        "website_description",
                        "website_published",
                    ],
                ),
                this.orm.searchRead("res.country", [], ["id", "name"]),
            ]);
            const userData = users[0];
            userData.country_id = userData.country_id && userData.country_id[0];
            userData.website_description = markup(userData.website_description || "");
            this.user = observe(userData, () => this.validate());
            this.countries = countries;
            const isInternalUser = await user.hasGroup("base.group_user");
            this.descriptionWysiwygConfig = {
                allowFile: isInternalUser,
                allowImage: isInternalUser,
                classList: ["form-control", websiteDescriptionClass],
                content: this.user.website_description,
                debug: !!this.debug,
                direction: localization.direction || "ltr",
                placeholder: _t("Write a few words about yourself..."),
            };
        });

        onMounted(() => {
            if (this.props.focusWebsiteDescription) {
                const websiteDescription = document.querySelector(
                    `.${websiteDescriptionClass}[contenteditable="true"]`,
                );
                if (websiteDescription) {
                    document.getSelection()?.setPosition(...endPos(websiteDescription));
                }
            }
            this.validate();
        });
    }

    validate() {
        this.state.emailHasError = !isEmail(this.user.email);
        this.state.nameHasError = !this.user.name || !this.user.name.trim().length;
        this.state.hasError = this.state.emailHasError || this.state.nameHasError;
    }

    get isEditingMyProfile() {
        return user.userId === this.props.userId;
    }

    get title() {
        return _t("Edit Profile");
    }

    onClearProfileImg() {
        this.profileImgData = false;
        this.profileImg.el.src = "/web/static/img/placeholder.png";
    }

    async onConfirm() {
        this.state.isProcessing = true;
        const descriptionElContent = this.websiteDescriptionEditor.getElContent();
        const data = {
            ...this.user,
            country_id: this.user.country_id && parseInt(this.user.country_id),
            website_description: isHtmlEmpty(descriptionElContent.innerText)
                ? ""
                : descriptionElContent.innerHTML,
            user_id: this.props.userId,
        };
        if (this.profileImgData != null) {
            data.image_1920 = this.profileImgData;
        }
        try {
            await rpc("/profile/user/save", data);
            if (this.props.confirm) {
                await this.props.confirm();
            }
            this.props.close();
        } catch (e) {
            const msg = e?.data?.message || e?.message || _t("Update failed.");
            this.notification.add(msg, { type: "danger" });
        } finally {
            this.state.isProcessing = false;
        }
    }

    onUploadProfileImg(file) {
        this.profileImg.el.src = `data:${file.type};base64,${file.data}`;
        this.profileImgData = file.data;
    }

    onWebsiteDescriptionEditorLoad(editor) {
        this.websiteDescriptionEditor = editor;
    }
}

registry
    .category("lazy_components")
    .add("website_profile.ProfileDialog", ProfileDialog);
