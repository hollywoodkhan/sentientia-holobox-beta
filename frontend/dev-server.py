"""Local frontend server with a same-origin proxy to the deployed avatar API."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
API = "https://avatar-api-82762694345.asia-south1.run.app"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _proxy(self):
        target = API + self.path.removeprefix("/api")
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() in {"content-type", "accept", "authorization", "x-admin-secret"}
        }
        request = Request(target, data=body, headers=headers, method=self.command)
        try:
            response = urlopen(request, timeout=120)
        except HTTPError as error:
            response = error
        payload = response.read()
        self.send_response(response.status)
        self.send_header("Content-Type", response.headers.get("Content-Type", "application/octet-stream"))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self._proxy() if self.path.startswith("/api/") else super().do_GET()

    def do_POST(self):
        self._proxy() if self.path.startswith("/api/") else self.send_error(405)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 4173), Handler).serve_forever()
