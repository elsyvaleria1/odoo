/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { humanSize } from "@web/core/utils/format/binary";
import { useService } from "@web/core/utils/hooks";
import { CharField, charField } from "@web/fields/basic/char/char_field";
import { ConfirmationDialog } from "@web/ui/dialog";

export class YoutubeUploadField extends CharField {
    static template = "social_youtube.YoutubeUploadField";
    setup() {
        super.setup();
        this.fileInputRef = elementRef();
        this.state = proxy({
            uploading: false,
            showSocialYoutubeBar: true,
            socialYoutubeText: _t("Uploading... 0%"),
            uploadProgress: 0,
            uploadErrorMessage: false,
        });
        this.notification = useService("notification");
        this.dialogService = useService("dialog");

        this.useFileAPI = !!window.FileReader;
        this.maxUploadSize = 128 * 1024 * 1024 * 1024;
    }

    /** @private */
    _awaitPostProcessing(uploadedVideoId) {
        return new Promise((resolve, reject) => {
            this.uploadedVideoId = uploadedVideoId;
            this.videoProcessedResolve = resolve;
            this.videoProcessedReject = reject;
            this.processingInfoInterval = setInterval(
                this._updateProcessingInfo.bind(this),
                1500,
            );
        });
    }

    /** @private */
    _listenUploadProgress() {
        const xhr = new window.XMLHttpRequest();
        xhr.upload.addEventListener(
            "progress",
            (e) => {
                if (e.lengthComputable) {
                    const roundedProgress = Math.round((e.loaded / e.total) * 100);
                    this.state.uploadProgress = roundedProgress;
                    this.state.socialYoutubeText = _t(
                        "Uploading... %s%",
                        this.state.uploadProgress,
                    );
                }
            },
            false,
        );

        return xhr;
    }

    /**
     * @param {number} fileSize
     * @param {string} fileType
     * @private
     */
    async _openUploadSession(fileSize, fileType) {
        const data = this.props.record.data;
        const title = data.youtube_title;
        const description = data.youtube_description;

        try {
            const response = await fetch(
                "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=status%2Csnippet",
                {
                    method: "POST",
                    headers: {
                        Authorization: `Bearer ${this.props.record.data.youtube_access_token}`,
                        "Content-Type": "application/json",
                        "X-Upload-Content-Length": fileSize.toString(),
                        "X-Upload-Content-Type": fileType,
                    },
                    body: JSON.stringify({
                        status: { privacyStatus: "private" },
                        snippet: { title, description },
                    }),
                },
            );

            if (response.ok) {
                return response.headers.get("location");
            }
            throw new Error("Failed to open upload session");
        } catch (error) {
            this._uploadFailed();
            throw error;
        }
    }

    /** @private */
    async _updateProcessingInfo() {
        const params = new URLSearchParams({
            part: "processingDetails",
            id: this.uploadedVideoId,
        });
        let response;
        let data;
        try {
            response = await fetch(
                `https://www.googleapis.com/youtube/v3/videos?${params}`,
                {
                    method: "GET",
                    headers: {
                        Authorization: `Bearer ${this.props.record.data.youtube_access_token}`,
                    },
                },
            );
            data = response.ok ? await response.json() : undefined;
        } catch {
            return;
        }

        if (!response.ok) {
            clearInterval(this.processingInfoInterval);
            this._uploadFailed();
            this._resetYoutubeVideoValues();
            this.videoProcessedReject(
                new Error(
                    `Video processing check failed with status: ${response.status}`,
                ),
            );
            return;
        }
        if (
            "items" in data &&
            data.items.length === 1 &&
            "processingDetails" in data.items[0]
        ) {
            const processingDetails = data.items[0].processingDetails;
            this.state.socialYoutubeText = _t("Processing...");

            if (processingDetails.processingStatus === "succeeded") {
                clearInterval(this.processingInfoInterval);
                this.videoProcessedResolve();
            }
        }
    }

    /** @private */
    _uploadFailed() {
        this.notification.add(_t("Upload failed. Please try again."), {
            type: "warning",
        });
        this.fileInputRef.el.value = "";
    }

    /**
     * @param {string} location
     * @param {File} file
     * @private
     */
    async _uploadFile(location, file) {
        const promise = new Promise((resolve, reject) => {
            const xhr = this._listenUploadProgress();
            xhr.open("PUT", location);
            xhr.setRequestHeader(
                "Authorization",
                `Bearer ${this.props.record.data.youtube_access_token}`,
            );
            xhr.setRequestHeader("Content-Type", "application/octet-stream");
            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        resolve({
                            videoId: response.id,
                            categoryId: response.snippet.categoryId,
                        });
                    } catch (error) {
                        reject(error);
                    }
                } else {
                    reject(new Error(`Upload failed with status: ${xhr.status}`));
                }
            };

            xhr.onerror = () => {
                reject(new Error("Upload failed due to network error"));
            };

            xhr.send(file);
        });

        return promise.catch((error) => {
            this._uploadFailed();
            throw error;
        });
    }

    /** @private */
    _onClearClick() {
        this.dialogService.add(ConfirmationDialog, {
            confirmLabel: _t("Yes, delete it"),
            cancelLabel: _t("No"),
            title: _t("Confirmation"),

            body: _t("Do you also want to remove the video from your YouTube account?"),
            confirm: async () => {
                const params = new URLSearchParams({
                    id: this.props.record.data.youtube_video_id,
                });
                let removed;
                try {
                    const response = await fetch(
                        `https://www.googleapis.com/youtube/v3/videos?${params}`,
                        {
                            method: "DELETE",
                            headers: {
                                Authorization: `Bearer ${this.props.record.data.youtube_access_token}`,
                            },
                        },
                    );
                    removed = response.ok;
                } catch {
                    removed = false;
                }
                this.uploadedVideoId = null;
                this._resetYoutubeVideoValues();
                if (!removed) {
                    this.notification.add(
                        _t("The video could not be removed from your YouTube account."),
                        { type: "warning" },
                    );
                }
            },
            cancel: () => {
                this._resetYoutubeVideoValues();
            },
        });
    }

    _resetYoutubeVideoValues() {
        this.props.record.update({
            youtube_video: false,
            youtube_video_id: false,
            youtube_video_category_id: false,
        });
    }

    /**
     * @param {Event} e
     * @private
     */
    async _onFileChanged(e) {
        const fileNodes = e.target;
        const hasReadableFile = this.useFileAPI && fileNodes.files.length !== 0;
        const accessToken = this.props.record.data.youtube_access_token;
        if (!accessToken || !hasReadableFile) {
            return;
        }

        const file = fileNodes.files[0];
        if (file.size > this.maxUploadSize) {
            const message = _t(
                "The selected video exceeds the maximum allowed size of %s.",
                humanSize(this.maxUploadSize),
            );
            this.notification.add(message, {
                title: _t("Video Upload"),
                type: "danger",
            });
            return false;
        }

        this.state.uploading = true;

        const sessionLocation = await this._openUploadSession(file.size, file.type);
        const { videoId, categoryId } = await this._uploadFile(sessionLocation, file);
        await this._awaitPostProcessing(videoId);

        const fileName = this.fileInputRef.el.value.match(/([^\\.]+)\.\w+$/)[0];

        this.state.uploading = false;
        await this.props.record.update({
            [this.props.name]: fileName,
            youtube_video_id: videoId,
            youtube_video_category_id: categoryId,
        });
    }

    /** @private */
    _onUploadClick() {
        const title = this.props.record.data.youtube_title;
        const description = this.props.record.data.youtube_description;
        let message;
        if (!title) {
            message = _t("You need to give your video a title.");
        } else if (!description) {
            message = _t("You need to give your video a description.");
        } else if (
            title.includes("<") ||
            title.includes(">") ||
            description.includes("<") ||
            description.includes(">")
        ) {
            message = _t("You cannot use '>' or '<' in both title and description.");
        } else if ([...title].length > 100) {
            message = _t("Your title cannot exceed 100 characters.");
        } else if ([...description].length > 5000) {
            message = _t("Your description cannot exceed 5000 characters.");
        } else {
            message = false;
        }
        if (message) {
            this.state.uploadErrorMessage = message;
            return;
        }
        this.state.uploadErrorMessage = false;
        this.fileInputRef.el.click();
    }
}

export const youtubeUploadField = {
    ...charField,
    component: YoutubeUploadField,
    fieldDependencies: [
        { name: "youtube_video_category_id", type: "char", readonly: false },
    ],
};

registry.category("fields").add("youtube_upload", youtubeUploadField);
