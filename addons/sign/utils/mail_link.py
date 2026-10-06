from urllib.parse import quote as url_quote


def get_mail_link(email, subject) -> str:
    """Build a ``mailto:`` link for a signature-request notification.

    :param email: recipient address (falsy allowed, e.g. an unset signer email)
    :param subject: ``sign.request.subject`` is an optional Char: it is False
        when unset, and urllib's quote raises TypeError on non-str input.
    """
    return "mailto:%s?subject=%s" % (url_quote(email or ""), url_quote(subject or ""))
