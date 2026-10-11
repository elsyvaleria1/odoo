from odoo.http import root as application

application.initialize()

bind = "127.0.0.1:8069"
pidfile = ".gunicorn.pid"
workers = 4
timeout = 240
max_requests = 2000
