from __future__ import annotations

import csv
import re
import statistics
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from odoo.libs.documents import METERED, Document, mimetype_for

from .engines import transcription_engines

CORPUS_FILE = "corpus.tsv"
_WORD = re.compile(r"\d+(?:[.,]\d+)?|\w+")

_NUMBER_WORDS = {
    **dict.fromkeys(("cero", "zero"), 0),
    **dict.fromkeys(("un", "uno", "una", "one"), 1),
    **dict.fromkeys(("dos", "two"), 2),
    **dict.fromkeys(("tres", "three"), 3),
    **dict.fromkeys(("cuatro", "four"), 4),
    **dict.fromkeys(("cinco", "five"), 5),
    **dict.fromkeys(("seis", "six"), 6),
    **dict.fromkeys(("siete", "seven"), 7),
    **dict.fromkeys(("ocho", "eight"), 8),
    **dict.fromkeys(("nueve", "nine"), 9),
    **dict.fromkeys(("diez", "ten"), 10),
    **dict.fromkeys(("once", "eleven"), 11),
    **dict.fromkeys(("doce", "twelve"), 12),
    **dict.fromkeys(("trece", "thirteen"), 13),
    **dict.fromkeys(("catorce", "fourteen"), 14),
    **dict.fromkeys(("quince", "fifteen"), 15),
    **dict.fromkeys(("dieciseis", "sixteen"), 16),
    **dict.fromkeys(("diecisiete", "seventeen"), 17),
    **dict.fromkeys(("dieciocho", "eighteen"), 18),
    **dict.fromkeys(("diecinueve", "nineteen"), 19),
    **dict.fromkeys(("veinte", "twenty"), 20),
    "veintiun": 21,
    "veintiuno": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
    **dict.fromkeys(("treinta", "thirty"), 30),
    **dict.fromkeys(("cuarenta", "forty"), 40),
    **dict.fromkeys(("cincuenta", "fifty"), 50),
    **dict.fromkeys(("sesenta", "sixty"), 60),
    **dict.fromkeys(("setenta", "seventy"), 70),
    **dict.fromkeys(("ochenta", "eighty"), 80),
    **dict.fromkeys(("noventa", "ninety"), 90),
    **dict.fromkeys(("cien", "ciento", "hundred"), 100),
    "doscientos": 200,
    "trescientos": 300,
    "cuatrocientos": 400,
    "quinientos": 500,
    "seiscientos": 600,
    "setecientos": 700,
    "ochocientos": 800,
    "novecientos": 900,
}
_THOUSAND = frozenset({"mil", "thousand"})
_NUMBER_AND = frozenset({"y", "and"})
_POINT = frozenset({"punto", "point"})


def _read_number(tokens: list[str], start: int) -> tuple[str, int] | None:
    zeros = ""
    while (
        start + 1 < len(tokens)
        and tokens[start] in ("cero", "zero")
        and tokens[start + 1] in _NUMBER_WORDS
    ):
        zeros += "0"
        start += 1
    total = current = 0
    index = start
    while index < len(tokens):
        token = tokens[index]
        if token in _NUMBER_AND and index > start and index + 1 < len(tokens):
            if tokens[index + 1] in _NUMBER_WORDS:
                index += 1
                continue
            break
        if token in _THOUSAND:
            total += (current or 1) * 1000
            current = 0
        elif token == "hundred" and current:
            current *= 100
        elif token in _NUMBER_WORDS:
            current += _NUMBER_WORDS[token]
        else:
            break
        index += 1
    if index == start:
        return None
    value = zeros + str(total + current)
    if index + 1 < len(tokens) and tokens[index] in _POINT:
        digits = ""
        index += 1
        while index < len(tokens) and _NUMBER_WORDS.get(tokens[index], 100) < 100:
            digits += str(_NUMBER_WORDS[tokens[index]])
            index += 1
        if digits:
            value = f"{value}.{digits}"
    return value, index


# a recogniser writes "38" for "treinta y ocho" and the grammar reads both, so a
# spoken number is compared as the number it names, not word by word
def words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower())
    bare = "".join(char for char in folded if not unicodedata.combining(char))
    tokens = [token.replace(",", ".") for token in _WORD.findall(bare)]
    compared: list[str] = []
    index = 0
    while index < len(tokens):
        number = _read_number(tokens, index)
        if number:
            compared.append(number[0])
            index = number[1]
        else:
            compared.append(tokens[index])
            index += 1
    return compared


def word_errors(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, expected in enumerate(reference, start=1):
        current = [row]
        for column, heard in enumerate(hypothesis, start=1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (expected != heard),
                )
            )
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class Clip:
    path: Path
    text: str

    @property
    def mimetype(self) -> str:
        return mimetype_for(self.path.suffix) or "audio/wav"


def read_corpus(directory: Path) -> list[Clip]:
    with (directory / CORPUS_FILE).open(encoding="utf-8", newline="") as corpus:
        return [
            Clip(directory / row[0].strip(), row[1].strip())
            for row in csv.reader(corpus, delimiter="\t")
            if len(row) >= 2 and row[0].strip() and not row[0].startswith("#")
        ]


@dataclass
class Score:
    engine: str
    clips: int = 0
    words: int = 0
    errors: int = 0
    exact: int = 0
    failed: int = 0
    seconds: list[float] = field(default_factory=list)

    def add(self, expected: str, heard: str, seconds: float) -> None:
        reference, hypothesis = words(expected), words(heard)
        self.clips += 1
        self.words += len(reference)
        self.errors += word_errors(reference, hypothesis)
        self.exact += reference == hypothesis
        self.seconds.append(seconds)

    @property
    def wer(self) -> float:
        return self.errors / self.words if self.words else 0.0

    @property
    def exact_rate(self) -> float:
        return self.exact / self.clips if self.clips else 0.0

    def percentile(self, share: float) -> float:
        if not self.seconds:
            return 0.0
        ranked = sorted(self.seconds)
        return ranked[min(len(ranked) - 1, int(share * len(ranked)))]


# engines are interleaved clip by clip, so a machine that slows down mid-run
# slows every engine alike instead of whichever ran last
def measure(
    env: Any,
    clips: list[Clip],
    purpose: str,
    language: str | None = None,
    only: set[str] | None = None,
    transcripts: list[dict[str, str]] | None = None,
) -> list[Score]:
    scores: dict[str, Score] = {}
    for clip in clips:
        data = clip.path.read_bytes()
        for engine in transcription_engines(clip.mimetype, env, purpose):
            if only and engine.name not in only:
                continue
            score = scores.setdefault(engine.name, Score(engine.name))
            document = Document(
                data,
                clip.mimetype,
                clip.path.name,
                env=env,
                read_up_to=METERED,
                purpose=purpose,
                language=language,
            )
            start = time.perf_counter()
            try:
                cues = engine.read(document) or []
            except Exception:
                score.failed += 1
                continue
            heard = " ".join(cue.text.strip() for cue in cues)
            score.add(clip.text, heard, time.perf_counter() - start)
            if transcripts is not None:
                transcripts.append(
                    {
                        "file": clip.path.name,
                        "engine": engine.name,
                        "purpose": purpose,
                        "said": clip.text,
                        "heard": heard,
                    }
                )
    return list(scores.values())


def _row(score: Score) -> str:
    median = statistics.median(score.seconds) if score.seconds else 0.0
    return (
        f"{score.engine:<24} {score.clips:>5} {score.failed:>6} "
        f"{score.wer:>7.1%} {score.exact_rate:>7.1%} "
        f"{median:>7.2f} {score.percentile(0.95):>7.2f}"
    )


def report(scores: list[Score]) -> str:
    header = (
        f"{'engine':<24} {'clips':>5} {'failed':>6} {'WER':>7} {'exact':>7} "
        f"{'p50 s':>7} {'p95 s':>7}"
    )
    rows = [_row(score) for score in sorted(scores, key=lambda score: score.wer)]
    return "\n".join([header, *rows])
