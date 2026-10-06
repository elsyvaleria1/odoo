import json
import sys
from pathlib import Path

from odoo.cli import DatabaseCommand, open_environment

from odoo.addons.speech.tools.measure import measure, read_corpus, report


class SpeechMeasure(DatabaseCommand):
    name = "speech_measure"
    description = (
        "Transcribe a folder of recordings with every engine a purpose may use, "
        "and score each against what was said"
    )

    def __init__(self) -> None:
        super().__init__()
        self.add_config_arguments(self.parser)
        self.parser.add_argument(
            "--corpus",
            required=True,
            help="directory holding corpus.tsv (file<TAB>what was said) and the recordings",
        )
        self.parser.add_argument(
            "--purpose",
            default="speech.transcription.command",
            help="the purpose the recordings are heard under (default: %(default)s)",
        )
        self.parser.add_argument("--language", default="es_MX")
        self.parser.add_argument(
            "--engine",
            action="append",
            dest="engines",
            help="measure only this engine; repeat for more than one",
        )
        self.parser.add_argument(
            "--transcripts",
            help="also write what each engine heard, one JSON object per clip and line",
        )

    def run(self, cmdargs: list[str]) -> None:
        parsed_args, unknown = self.parse_args(cmdargs)
        db_name = self.bootstrap_config(parsed_args, extra_args=unknown)
        clips = read_corpus(Path(parsed_args.corpus))
        transcripts: list[dict[str, str]] = []
        with open_environment(db_name) as env:
            scores = measure(
                env,
                clips,
                parsed_args.purpose,
                parsed_args.language,
                set(parsed_args.engines or ()),
                transcripts,
            )
        if parsed_args.transcripts:
            with Path(parsed_args.transcripts).open("w", encoding="utf-8") as out:
                out.writelines(
                    json.dumps(line, ensure_ascii=False) + "\n" for line in transcripts
                )
        if not scores:
            sys.stderr.write(
                f"No engine may hear {parsed_args.purpose!r} on {db_name}\n"
            )
            return
        sys.stdout.write(report(scores) + "\n")
