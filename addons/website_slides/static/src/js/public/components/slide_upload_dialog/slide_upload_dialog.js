/** @odoo-module native */
import { Component, onMounted, proxy, t, useProps } from "@odoo/owl";
import { DropdownItem } from "@web/components/dropdown";
import { SelectMenu } from "@web/components/select_menu";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { redirect } from "@web/core/utils/urls";
import { Dialog } from "@web/ui/dialog";

import { SlideUploadCategory } from "./slide_upload_category.js";
import { SlideCategoryIcon } from "./slide_upload_dialog_select.js";

export class SlideUploadDialog extends Component {
    static baseSettings = {
        page: "select",
        size: "md",
        alertMsg: "",
        title: _t("Add Content"),
    };
    static categoryData = {
        document: { icon: "fa-regular fa-file-pdf", label: _t("Presentation / Doc") },
        infographic: { icon: "fa-regular fa-file-image", label: _t("Image") },
        article: { icon: "fa-solid fa-file-lines", label: _t("Article") },
        video: { icon: "fa-regular fa-file-video", label: _t("Video") },
        quiz: { icon: "fa-solid fa-circle-question", label: _t("Quiz") },
    };
    static components = {
        Dialog,
        DropdownItem,
        SelectMenu,
        SlideCategoryIcon,
        SlideUploadCategory,
    };
    static pagesTemplates = {
        article: "website_slides.SlideCategoryTutorial.Article",
        document: "website_slides.SlideCategoryTutorial.Document",
        infographic: "website_slides.SlideCategoryTutorial.Infographic",
        select: "website_slides.SlideUploadDialogSelect",
        upload: "website_slides.UploadInProgressDialog",
        video: "website_slides.SlideCategoryTutorial.Video",
        quiz: "website_slides.SlideCategoryTutorial.Quiz",
    };
    static props = {
        canPublish: t.boolean(),
        canUpload: t.boolean(),
        categoryId: t.number().optional(),
        channelId: t.number(),
        close: t.function(),
        openModal: t.string().optional(),
    };
    static template = "website_slides.SlideUploadDialog";
    props = useProps(this.constructor.props);

    setup() {
        this.pagesTemplates = this.constructor.pagesTemplates;
        this.slideCategoryData = this.constructor.categoryData;
        this.state = proxy({ ...this.constructor.baseSettings });
        onMounted(() => {
            if (
                this.props.openModal &&
                this.props.openModal in this.slideCategoryData
            ) {
                this.onClickSlideCategoryIcon(this.props.openModal);
            }
        });
    }

    onClickSlideCategoryIcon(slideCategory) {
        this.state.page = slideCategory;
        this.state.size = "lg";
    }

    onClickGoBack() {
        Object.assign(this.state, SlideUploadDialog.baseSettings);
    }

    async uploadSlide(formValues, previousPage) {
        this.state.page = "upload";
        this.state.size = "md";
        const data = await rpc("/slides/add_slide", formValues);
        if (data.error) {
            this.state.page = previousPage;
            this.state.size = "lg";
            this.state.alertMsg = data.error;
            return;
        }
        if (data.url.includes("enable_editor")) {
            const { origin, pathname } = window.top.location;
            const url = new URL(data.url, `${origin}${pathname}`);
            if (url.origin === origin) {
                window.top.location = url.href;
            }
        } else {
            redirect(data.url);
        }
    }
}
