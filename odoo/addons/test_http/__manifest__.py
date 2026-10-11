{
    "name": "HTTP Tests",
    "version": "1.0",
    "category": "Hidden/Tests",
    "summary": "Test HTTP behaviour, including captcha, device, echo reply",
    "description": "Run regression tests for HTTP. Loaded test suites include ``TestCaptcha``, ``TestDevice``, ``TestHttpEchoReplyHttpNoDB``, ``TestHttpEchoReplyJsonNoDB``, ``TestHttpEchoReplyHttpWithDB``.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
        "mail",
        "rpc",
    ],
    "data": [
        "data.xml",
        "security/ir.access.csv",
        "views.xml",
    ],
}
