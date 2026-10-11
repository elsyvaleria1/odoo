from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sherpa_onnx

from odoo.libs.documents import AUDIO_SAMPLE_RATE, Cue

ENCODER = "encoder.onnx"
DECODER = "decoder.onnx"
TOKENS = "tokens.txt"
VAD = "vad.onnx"
SEGMENTATION = "segmentation.onnx"
EMBEDDING = "embedding.onnx"
REQUIRED = (ENCODER, DECODER, TOKENS, VAD)
RELEASE_VAD = "silero_vad.onnx"

MAX_UTTERANCE_S = 20.0
MIN_SILENCE_S = 0.5
WHISPER_TAIL_PADDINGS = 3000
FULL_WINDOW_SIZES = ("turbo", "large")
CLUSTER_THRESHOLD = 0.5


def num_threads() -> int:
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def whisper_language(language: str | None) -> str:
    return (language or "").replace("-", "_").split("_")[0].lower()


def model_files(model_dir: Path) -> tuple[dict[str, Path], list[str]]:
    found: dict[str, Path] = {
        name: model_dir / name for name in REQUIRED if (model_dir / name).is_file()
    }
    if VAD not in found and (model_dir / RELEASE_VAD).is_file():
        found[VAD] = model_dir / RELEASE_VAD
    whisper = (ENCODER, DECODER, TOKENS)
    if not all(name in found for name in whisper) and model_dir.is_dir():
        sizes = sorted(
            path.name.removesuffix("-tokens.txt")
            for path in model_dir.glob("*-tokens.txt")
        )
        if len(sizes) == 1:
            size = sizes[0]
            for suffix in (".int8.onnx", ".onnx"):
                encoder = model_dir / f"{size}-encoder{suffix}"
                decoder = model_dir / f"{size}-decoder{suffix}"
                if encoder.is_file() and decoder.is_file():
                    found[ENCODER], found[DECODER] = encoder, decoder
                    found[TOKENS] = model_dir / f"{size}-tokens.txt"
                    break
    return found, [name for name in REQUIRED if name not in found]


@dataclass(frozen=True)
class Utterance:
    start: float
    end: float
    samples: np.ndarray


class LocalEngine:
    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir
        self.files = model_files(model_dir)[0]
        self._recognizers: dict[str, sherpa_onnx.OfflineRecognizer] = {}
        self._diarizer = LocalDiarizer(model_dir)
        self._lock = threading.Lock()

    @classmethod
    def missing_files(cls, model_dir: Path) -> list[str]:
        return model_files(model_dir)[1]

    @property
    def diarizes(self) -> bool:
        return LocalDiarizer.available(self.model_dir)

    def transcribe(self, samples: np.ndarray, language: str | None = None) -> list[Cue]:
        with self._lock:
            utterances = self._utterances(samples)
            if not utterances:
                return []
            texts = self._recognize(utterances, whisper_language(language))
            turns = self._diarizer.turns(samples) if self.diarizes else []
        return [
            Cue(
                start=round(utterance.start, 2),
                end=round(utterance.end, 2),
                text=text,
                speaker=speaker_of(utterance, turns),
            )
            for utterance, text in zip(utterances, texts, strict=True)
            if text
        ]

    def _utterances(self, samples: np.ndarray) -> list[Utterance]:
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(self.files[VAD])
        config.silero_vad.min_silence_duration = MIN_SILENCE_S
        config.silero_vad.max_speech_duration = MAX_UTTERANCE_S
        config.sample_rate = AUDIO_SAMPLE_RATE
        config.num_threads = 1
        buffer_s = samples.size / AUDIO_SAMPLE_RATE + MAX_UTTERANCE_S
        vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=buffer_s)
        window = config.silero_vad.window_size
        utterances = []
        for offset in range(0, samples.size, window):
            vad.accept_waveform(samples[offset : offset + window])
            utterances.extend(self._drain(vad))
        vad.flush()
        utterances.extend(self._drain(vad))
        return utterances

    def _drain(self, vad: sherpa_onnx.VoiceActivityDetector) -> list[Utterance]:
        found = []
        while not vad.empty():
            segment = vad.front
            samples = np.asarray(segment.samples, dtype=np.float32)
            start = segment.start / AUDIO_SAMPLE_RATE
            found.append(
                Utterance(start, start + samples.size / AUDIO_SAMPLE_RATE, samples)
            )
            vad.pop()
        return found

    def _recognize(self, utterances: list[Utterance], language: str) -> list[str]:
        recognizer = self._recognizer(language)
        streams = []
        for utterance in utterances:
            stream = recognizer.create_stream()
            stream.accept_waveform(AUDIO_SAMPLE_RATE, utterance.samples)
            streams.append(stream)
        recognizer.decode_streams(streams)
        return [stream.result.text.strip() for stream in streams]

    def _recognizer(self, language: str) -> sherpa_onnx.OfflineRecognizer:
        if language not in self._recognizers:
            self._recognizers[language] = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=str(self.files[ENCODER]),
                decoder=str(self.files[DECODER]),
                tokens=str(self.files[TOKENS]),
                language=language,
                task="transcribe",
                num_threads=num_threads(),
                **self._window(),
            )
        return self._recognizers[language]

    def _window(self) -> dict[str, int]:
        size = self.files[ENCODER].name.partition("-encoder")[0]
        if size.startswith(FULL_WINDOW_SIZES):
            return {"tail_paddings": WHISPER_TAIL_PADDINGS}
        return {}


class LocalDiarizer:
    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir
        self._diarizer: sherpa_onnx.OfflineSpeakerDiarization | None = None
        self._lock = threading.Lock()

    @classmethod
    def available(cls, model_dir: Path) -> bool:
        return all((model_dir / name).is_file() for name in (SEGMENTATION, EMBEDDING))

    def turns(self, samples: np.ndarray) -> list[tuple[float, float, int]]:
        with self._lock:
            result = self._loaded().process(samples).sort_by_start_time()
        return [(turn.start, turn.end, turn.speaker) for turn in result]

    def _loaded(self) -> sherpa_onnx.OfflineSpeakerDiarization:
        if self._diarizer is None:
            config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
                segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                    pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                        model=str(self.model_dir / SEGMENTATION)
                    ),
                    num_threads=num_threads(),
                ),
                embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                    model=str(self.model_dir / EMBEDDING),
                    num_threads=num_threads(),
                ),
                clustering=sherpa_onnx.FastClusteringConfig(
                    num_clusters=-1, threshold=CLUSTER_THRESHOLD
                ),
                min_duration_on=0.3,
                min_duration_off=MIN_SILENCE_S,
            )
            if not config.validate():
                raise ValueError(
                    f"The speaker models in {self.model_dir} cannot be loaded"
                )
            self._diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)
        return self._diarizer


def speaker_of(utterance: Utterance, turns: list[tuple[float, float, int]]) -> str:
    overlap: dict[int, float] = {}
    for start, end, speaker in turns:
        shared = min(end, utterance.end) - max(start, utterance.start)
        if shared > 0:
            overlap[speaker] = overlap.get(speaker, 0.0) + shared
    if not overlap:
        return ""
    return f"SPEAKER_{max(overlap, key=overlap.__getitem__)}"
