import io
import zipfile
from collections.abc import Iterable


def unique_filenames(filenames: Iterable[str]) -> list[str]:
    used = set()
    result = []
    for filename in filenames:
        candidate = filename
        base, dot, ext = filename.rpartition(".")
        if not dot:
            base, ext = filename, ""
        counter = 0
        while candidate in used:
            counter += 1
            candidate = f"{base} ({counter}){dot}{ext}"
        used.add(candidate)
        result.append(candidate)
    return result


def prepare_zip_from_data(docs_data) -> bytes:
    buffer = io.BytesIO()
    filenames = unique_filenames(doc_data["filename"] for doc_data in docs_data)
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zipfile_obj:
        for filename, doc_data in zip(filenames, docs_data, strict=True):
            zipfile_obj.writestr(filename, doc_data["content"])
    return buffer.getvalue()
