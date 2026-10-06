import re

_TAG_RE = re.compile(r"^>\s*<([^>]+)>")


def parse_sdf(text):
    """Split an SDF document into its records.

    :param str text: content of the SDF file
    :return: one dict per record with ``name``, ``molblock`` and ``tags``
    :rtype: list[dict]
    """
    records = []
    for chunk in text.replace("\r\n", "\n").split("$$$$"):
        if not chunk.strip():
            continue
        lines = chunk.lstrip("\n").split("\n")
        try:
            end = next(i for i, line in enumerate(lines) if line.startswith("M  END"))
        except StopIteration:
            continue
        tags = {}
        tag = None
        for line in lines[end + 1 :]:
            match = _TAG_RE.match(line)
            if match:
                tag = match.group(1)
                tags[tag] = []
            elif tag and line.strip():
                tags[tag].append(line.strip())
            else:
                tag = None
        records.append(
            {
                "name": lines[0].strip(),
                "molblock": "\n".join(lines[: end + 1]) + "\n",
                "tags": {key: "\n".join(value) for key, value in tags.items()},
            }
        )
    return records
