import zipfile

from odoo.exceptions import UserError
from odoo.tools import LazyTranslate

_lt = LazyTranslate(__name__)

MAX_UNCOMPRESSED_MEMBER_SIZE = 100 * 1024 * 1024


def check_zip_member_sizes(file) -> None:
    with zipfile.ZipFile(file) as archive:
        for info in archive.infolist():
            if info.file_size > MAX_UNCOMPRESSED_MEMBER_SIZE:
                raise UserError(
                    _lt(
                        "Import file %(member)s would expand to more than "
                        "%(cap)s MiB, which is not supported.",
                        member=info.filename,
                        cap=MAX_UNCOMPRESSED_MEMBER_SIZE // (1024 * 1024),
                    )
                )
