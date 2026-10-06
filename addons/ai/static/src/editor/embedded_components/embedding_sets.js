/** @odoo-module native */
import {
    MAIN_EMBEDDINGS,
    READONLY_MAIN_EMBEDDINGS,
} from "@html_editor/others/embedded_components/embedding_sets";

import { aiReadonlyVoiceTranscriptionEmbeddedComponent } from "./core/readonly_voice_transcription.js";
import { aiVoiceTranscriptionEmbeddedComponent } from "./core/voice_transcription.js";

MAIN_EMBEDDINGS.push(aiVoiceTranscriptionEmbeddedComponent);
READONLY_MAIN_EMBEDDINGS.push(aiReadonlyVoiceTranscriptionEmbeddedComponent);
