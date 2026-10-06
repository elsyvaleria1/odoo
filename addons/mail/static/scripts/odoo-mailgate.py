#!/usr/bin/env python3

EX_USAGE = 64
EX_NOUSER = 67
EX_UNAVAILABLE = 69
EX_SOFTWARE = 70
EX_TEMPFAIL = 75

DEFAULT_TIMEOUT = 120


import sys  # noqa: E402 - sys must exist before the guarded import block below, whose handler writes to stderr

try:
    import argparse
    import base64
    import json
    import pathlib
    import traceback
    import urllib.error
    import urllib.request
    from typing import NoReturn
except ImportError as e:
    sys.stderr.write("%s\n" % e)
    sys.exit(EX_SOFTWARE)


class ArgumentParser(argparse.ArgumentParser):
    # Postfix bounces on every exit status but EX_TEMPFAIL and EX_OSERR: a
    # mistake in master.cf must keep the mail queued until it is fixed
    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if message:
            sys.stderr.write(message)
        sys.exit(0 if status == 0 else EX_TEMPFAIL)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl) -> None:
        return None


def postfix_exit(
    exit_code: int = EX_SOFTWARE, message: str | None = None, debug: bool = False
) -> NoReturn:
    try:
        if debug:
            traceback.print_exc(None, sys.stderr)
        if message:
            sys.stderr.write(message)
    except Exception:  # noqa: S110 - already on the failure path; a failure to report it must not mask the original
        pass
    finally:
        sys.exit(exit_code)


def prepare_mailgate_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="odoo-mailgate.py",
        description="Deliver one message from the MTA to an Odoo incoming mail server.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s v3.0")
    parser.add_argument(
        "--url",
        required=True,
        help="The incoming mail server's inbound URL, "
        "https://odoo.example.com/mail/inbound/<server id>",
    )
    parser.add_argument(
        "--token-file",
        required=True,
        help="File holding the server's inbound token, readable by the MTA's "
        "pipe user only",
    )
    parser.add_argument(
        "--sender",
        default="",
        help="Envelope sender (Postfix: ${sender}, with null_sender= so that the "
        "null sender is empty)",
    )
    parser.add_argument(
        "--recipient",
        dest="recipients",
        action="append",
        required=True,
        help="Envelope recipient (Postfix: ${recipient}), once per recipient",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Seconds to wait for Odoo before deferring the message "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print tracebacks to stderr, which the MTA logs",
    )
    return parser


def read_token(options: argparse.Namespace) -> str:
    try:
        token = pathlib.Path(options.token_file).read_text(encoding="utf-8").strip()
    except OSError as err:
        postfix_exit(EX_TEMPFAIL, "cannot read token file: %s\n" % err, options.debug)
    if not token:
        postfix_exit(EX_TEMPFAIL, "the token file is empty\n", options.debug)
    return token


def prepare_envelope(options: argparse.Namespace, message: bytes) -> bytes:
    return json.dumps(
        {
            "sender": options.sender,
            "recipients": options.recipients,
            "message": base64.b64encode(message).decode("ascii"),
        }
    ).encode("ascii")


def get_exit_status(status: int, body: bytes) -> tuple[int, str]:
    if 200 <= status < 300:
        return 0, ""
    try:
        problem = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        problem = {}
    if not isinstance(problem, dict):
        problem = {}
    error = problem.get("error") or ""
    detail = problem.get("detail") or ""
    if status == 409 and error == "duplicate_event":
        return 0, ""
    if status == 422 and error == "no_route":
        return EX_NOUSER, "no Odoo alias accepts this message: %s\n" % detail
    if status == 413:
        return EX_UNAVAILABLE, "the message is larger than Odoo accepts\n"
    # Anything else -- a wrong token or URL, a restart, a bug -- is a reason
    # to keep the message in the queue while someone fixes it, never to
    # bounce mail a sender has no way to resend.
    return EX_TEMPFAIL, "odoo answered %d %s %s\n" % (status, error, detail)


def main() -> None:
    options = prepare_mailgate_parser().parse_args()
    token = read_token(options)
    message = sys.stdin.buffer.read()
    if not message.strip():
        postfix_exit(EX_USAGE, "no message on stdin\n", options.debug)
    if not options.url.startswith(("https://", "http://")):
        postfix_exit(EX_TEMPFAIL, "--url must be an http(s) URL\n", options.debug)
    request = urllib.request.Request(  # noqa: S310 - the scheme is checked just above
        options.url,
        data=prepare_envelope(options, message),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % token,
            "User-Agent": "odoo-mailgate/3.0",
        },
    )
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=options.timeout) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as err:
        status, body = err.code, err.read()
    except OSError as err:
        postfix_exit(
            EX_TEMPFAIL,
            "connection error: %s: %s (%s)\n"
            % (err.__class__.__name__, err, options.url),
            options.debug,
        )
    exit_code, reason = get_exit_status(status, body)
    if exit_code:
        postfix_exit(exit_code, reason, options.debug)


try:
    if __name__ == "__main__":
        main()
except SystemExit:
    raise
except Exception:
    postfix_exit(EX_TEMPFAIL, "", True)
