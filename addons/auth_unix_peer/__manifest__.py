{
    "name": "Unix Peer Authentication",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "summary": "Bearer routes called from the same host run as the caller's own Odoo user, with no API key",
    "description": "A process on the Odoo host that calls a bearer route (JSON-2, model docs) over the loopback interface without an Authorization header is identified by the kernel: Odoo asks which Unix user owns the client end of that TCP connection. If that user is in the configured group, the comment of every key in its root-owned authorized_keys file names an internal Odoo login, and the request runs as that user. Set the group in the system parameter auth_unix_peer.group; without it the module does nothing.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "rpc",
    ],
}
