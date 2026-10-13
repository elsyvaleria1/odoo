ELLIPSIS = "…"


def button(text, data) -> dict:
    return {"text": text, "callback_data": data}


def web_app_button(text, url) -> dict:
    return {"text": text, "web_app": {"url": url}}


def keyboard(*rows) -> dict:
    return {"inline_keyboard": [list(row) for row in rows if row]}


def share_phone(text) -> dict:
    return {
        "keyboard": [[{"text": text, "request_contact": True}]],
        "one_time_keyboard": True,
        "resize_keyboard": True,
    }


def single(text, data):
    return keyboard([button(text, data)])


def confirm_cancel(confirm_text, confirm_data, cancel_text, cancel_data):
    return keyboard(
        [button(confirm_text, confirm_data), button(cancel_text, cancel_data)]
    )


def shorten(text, width=None):
    text = text or ""
    if not width or len(text) <= width:
        return text
    return text[: width - len(ELLIPSIS)] + ELLIPSIS


def record_list(records, label, data, *, limit=None, width=None, trailing=()):
    shown = list(records)[:limit] if limit else list(records)
    return keyboard(
        *([button(shorten(label(record), width), data(record))] for record in shown),
        trailing,
    )
