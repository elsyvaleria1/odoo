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

    /**
     * When the file upload is complete, Youtube triggers its own video "processing"
     * that can take up to a few minutes and during which we can't alter the video
     * in any way nor embed it in the YouTube preview.
     *
     * It's necessary to wait for the process to be complete before letting the user
     * proceed with posting, since we can't alter video properties during this process.
     *
     * So we just periodically ping the API to check the status of this "video processing".
     * When it's done, we resolve the Promise returned by this method.
     *
     * @private
     */
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

    /**
     * Small method that listens to the file upload progress and updates the UI accordingly to give
     * user feedback.
     *
     * @private
     */
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
     * We use the resumable upload protocol of YouTube to upload our videos, because it allows
     * setting the video as 'private' before uploading it, meaning it will not publicly appear for
     * followers of the channel before the video is actually "posted" on the social application.
     *
     * However, to simplify the implementation, we do not split the video in "chucks" and still
     * upload all at once.
     * Depending on the feedback we get, it would maybe be nice to actually split the file in chunks
     * and implement a "retry" behavior whenever an upload sequence fails.
     *
     * This method will open the upload session and return a 'location' that will be used to upload
     * the file chunks.
     *
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

    /**
     * See #_awaitPostProcessing for more information.
     *
     * @private
     */
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

    /**
     * Notify that the upload failed and clear the value of the file input.
     *
     * @private
     */
    _uploadFailed() {
        this.notification.add(_t("Upload failed. Please try again."), {
            type: "warning",
        });
        this.fileInputRef.el.value = "";
    }

    /**
     * See #_openUploadSession for more information about the upload process.
     *
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

    /**
     * Clear the value and ask the user if they also want to delete the actual
     * video from their YouTube channel.
     *
     * @private
     */
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
     * When the user selects a file:
     * - We start the upload process
     * - Periodically update the UI to show how many % are uploaded
     * - Wait for YouTube post-processing to finish
     * - Change the values of the 'youtube_video_id' and 'youtube_video_category_id' fields when the
     *   upload is complete.
     *
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

    /**
     * Pre-validates the title and description of the video before initiating
     * the upload, So that we can avoid upload failures from YouTube.
     *
     * Some special characters may not have consistent lengths across different encodings.
     * YouTube checks for length using UTF-8 encoding, while JavaScript uses UTF-16.
     * To obtain the correct UTF-8 length, we are destructuring the title and description.
     *
     * @private
     */
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
