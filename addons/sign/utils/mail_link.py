from urllib.parse import quote as url_quote


def get_mail_link(email, subject) -> str:
    return "mailto:%s?subject=%s" % (url_quote(email or ""), url_quote(subject or ""))
