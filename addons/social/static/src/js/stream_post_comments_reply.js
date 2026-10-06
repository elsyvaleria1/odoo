/** @odoo-module native */
import { Component, markup, onMounted, proxy, t, useProps } from "@odoo/owl";
import { useEmojiPicker } from "@web/components/emoji_picker";
import { FileUploader } from "@web/core/file_upload";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus, useService } from "@web/core/utils/hooks";

export class StreamPostCommentsReply extends Component {
    static template = "social.StreamPostCommentsReply";
    static components = { FileUploader };
    static props = {
        comment: t.object().optional(),
        account: t.object().optional(),
        originalPost: t.object().optional(),
        bubble_design: t.boolean().optional(),
        classes: t.string().optional(),
        initialValue: t.string().optional(),
        attachmentSrc: t.string().optional(),
        isCommentEdit: t.boolean().optional(false),
        isCommentReply: t.boolean().optional(false),
        mediaSpecificProps: t.object(),
        onAddComment: t.function(),
        preventAddComment: t.function(),
        toggleEditMode: t.function().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.state = proxy({
            disabled: false,
            attachmentSrc: false,
        });
        this.autofocusRef = elementRef();
        this.inputRef = useAutofocus({ ref: this.autofocusRef });
        this._onAddEmoji = this._onAddEmoji.bind(this);
        this.notification = useService("notification");
        this.emojiPickerRef = elementRef();
        useEmojiPicker(this.emojiPickerRef, {
            onSelect: (str) => this._onAddEmoji(str),
            onClose: () => this.state.autofocus++,
        });
        onMounted(() => {
            this.inputRef.el.value = this.initialValue || "";
        });
    }

    /**
     * Method called when the user presses 'Enter' after writing a comment in the textarea.
     *
     * @param {KeyboardEvent} event
     * @private
     */
    _onAddComment(event) {
        if (event.key !== "Enter" || event.ctrlKey || event.shiftKey) {
            return;
        }
        event.preventDefault();
        const textarea = event.currentTarget;
        if (
            textarea.value.trim() === "" &&
            (!this.state.attachmentSrc || !this.allowImageOnlyComment)
        ) {
            return;
        }
        this.state.disabled = true;
        this._addComment(textarea);
    }

    //---------
    // Private
    //---------

    async _addComment(textarea) {
        if (
            this.props.preventAddComment(
                textarea,
                this.isCommentReply ? this.comment.id : undefined,
            )
        ) {
            return;
        }
        const formData = new FormData(
            textarea.closest(".o_social_write_reply").querySelector("form"),
        );
        const xhr = new window.XMLHttpRequest();
        xhr.open("POST", this.addCommentEndpoint);
        formData.append("csrf_token", odoo.csrf_token);
        formData.append("stream_post_id", this.originalPost.id.raw_value);
        if (this.isCommentEdit) {
            formData.append("is_edit", this.isCommentEdit);
        }
        if (this.isCommentEdit || this.isCommentReply) {
            formData.append("comment_id", this.comment.id);
        }
        if (this.state.attachmentSrc) {
            // convert to base 64 encoded file into a Blob object
            // (with the correct Content-Type)
            const base64Response = await fetch(this.state.attachmentSrc);
            const blob = await base64Response.blob();
            const file = new File([blob], "attachment", { type: blob.type });
            formData.set("attachment", file);
        }
        const existingAttachmentId = textarea.dataset.existingAttachmentId;
        if (existingAttachmentId) {
            formData.append("existing_attachment_id", this.props.attachmentSrc);
        }
        xhr.send(formData);
        xhr.onload = () => {
            let comment = JSON.parse(xhr.response);
            if (this.isCommentEdit) {
                // preserve other keys if they didn't change (e.g. like summary, etc)
                comment = { ...this.comment, ...comment };
            }
            if (comment.error) {
                this.notification.add(
                    markup`
                        ${_t("Something went wrong while posting the comment.")}
                        <br/><br/>
                        ${comment.error}
                    `,
                    { type: "danger" },
                );
            } else {
                this.props.onAddComment(comment);
            }
            this.state.attachmentSrc = false;
            this.inputRef.el.value = "";
            this.state.disabled = false;
            if (this.isCommentEdit) {
                this.props.toggleEditMode();
            }
        };
    }

    /**
     * This method adds the emoji just after the user selection. After it's inserted it
     * gives back the focus to the textarea just after the added emoji.
     *
     * @param {string} str: emoji
     * @private
     */
    _onAddEmoji(str) {
        const input = this.inputRef.el;
        const selectionStart = input.selectionStart;
        input.value =
            input.value.slice(0, selectionStart) +
            str +
            input.value.slice(selectionStart);
        input.focus();
        input.setSelectionRange(
            selectionStart + str.length,
            selectionStart + str.length,
        );
    }

    //------------------------
    // Image Upload Processing
    //------------------------

    /**
     * Triggers image selection (file system browse).
     *
     * @param {MouseEvent} event
     */
    _onAddImage(event) {
        event.currentTarget
            .closest(".o_social_write_reply")
            .querySelector(".o_input_file")
            .click();
    }

    /**
     * When the user selects a file to attach to the comment,
     * a preview of the image is shown below the comment.
     *
     * This is very similar to what Facebook does when commenting a post.
     *
     * @param {Object} file
     * @param {String} file.data
     * @param {String} file.type
     */
    _onImageChange({ data, type }) {
        this.state.attachmentSrc = "data:" + type + ";base64," + data;
    }

    /**
     * Removes the image preview when the user decides to remove it.
     */
    _onImageRemove() {
        this.state.attachmentSrc = false;
    }

    //--------
    // Getters
    //--------

    get comment() {
        return this.props.comment;
    }

    get account() {
        return this.props.account;
    }

    get originalPost() {
        return this.props.originalPost;
    }

    get authorPictureSrc() {
        return "";
    }

    get addCommentEndpoint() {
        return null;
    }

    get isCommentReply() {
        return this.props.isCommentReply;
    }

    get isCommentEdit() {
        return this.props.isCommentEdit;
    }

    get initialValue() {
        return this.props.initialValue;
    }

    get canAddImage() {
        return true;
    }

    get allowImageOnlyComment() {
        return false;
    }
}
