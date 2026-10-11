import re

CITATION_REGEX = re.compile(
    r"""
    \[SOURCE:
        ([0-9]+
            (?:\s*,\s*[0-9]+)*
        )
    \]
""",
    re.VERBOSE,
)


def get_attachment_ids_from_text(text):
    if not text:
        return []
    sources = CITATION_REGEX.findall(text)
    attachment_ids = [int(id.strip()) for source in sources for id in source.split(",")]
    return list(set(attachment_ids))


def apply_numeric_citations(
    text, attachment_data, link_attrs='target="_blank" rel="noreferrer noopener"'
):
    if not text:
        return ""

    new_content = ""
    text_pieces = CITATION_REGEX.split(text)
    resolved_citations = {}
    for index, text_piece in enumerate(text_pieces):
        if index % 2 == 0:
            new_content += text_piece.rstrip(" ")
        else:
            attachment_ids = text_piece.split(",")
            for attachment_id in attachment_ids:
                attachment_id_int = int(attachment_id.strip())
                attachment_info = attachment_data.get(attachment_id_int, {})
                if not attachment_info:
                    continue
                href = attachment_info["url"]
                if attachment_id_int not in resolved_citations:
                    citation_num = len(resolved_citations) + 1
                    resolved_citations[attachment_id_int] = citation_num
                else:
                    citation_num = resolved_citations[attachment_id_int]
                citation_html = f'<sup><a href="{href}" {link_attrs} style="text-decoration: none;"> [{citation_num}] </a></sup>'
                new_content += citation_html

    return new_content
