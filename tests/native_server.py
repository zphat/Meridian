"""Offline native-window fixture using the INSTALLED application's files.

Only this disposable server returns blank pages, to exercise actual startup
recovery. No fault-injection switches are added to the shipped application.
"""
import sys
import tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, sys.argv[1])
from meridian import Meridian, Handler

blank_count = int(sys.argv[2])


class NativeHandler(Handler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/' and self.server.blank_left:
            self.server.blank_left -= 1
            raw = b'<!doctype html><html><body></body></html>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)
            print('Simulated blank document', flush=True)
            return
        if self.path == '/':
            print('Serving installed interface', flush=True)
        super().do_GET()


with tempfile.TemporaryDirectory() as data:
    app = Meridian(data, start_worker=False)
    app.auth._send_resend = lambda cfg, url: 'native-fixture-email'
    server = ThreadingHTTPServer(('127.0.0.1', 8765), NativeHandler)
    server.meridian = app
    server.blank_left = blank_count
    print('Ready', flush=True)
    try:
        with patch('auth.secrets.randbelow', return_value=13572468):
            server.serve_forever()
    finally:
        server.server_close()
        app.close()
