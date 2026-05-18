#!/usr/bin/env python3
"""server.py — HTTP server for Shop Schedule.

Serves public/ as static files and provides a small upload API:
  POST /api/upload/schedule  — receive Foreman's Report PDF, trigger process_drop.py
  POST /api/upload/raw       — receive display PDF, save to public/raw/, update pages.json
  DELETE /api/raw/<name>     — remove a display PDF and its pages.json entry
"""

import json
import os
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

BASE_DIR   = Path(__file__).parent
PUBLIC_DIR = BASE_DIR / 'public'
RAW_DIR    = PUBLIC_DIR / 'raw'
PAGES_JSON = PUBLIC_DIR / 'pages.json'
DROP_DIR   = BASE_DIR / 'incoming'
MAX_UPLOAD = 50 * 1024 * 1024  # 50 MB

_pages_lock = threading.Lock()


def _read_pages():
    if PAGES_JSON.exists():
        with open(PAGES_JSON) as f:
            return json.load(f)
    return {'scroll_cycles': 2, 'page_duration': 60, 'transition_ms': 1500, 'pages': []}


def _write_pages(cfg):
    with open(PAGES_JSON, 'w') as f:
        json.dump(cfg, f, indent=2)


def _page_url(p):
    return p if isinstance(p, str) else p.get('url', '')


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    # ── Routing ──────────────────────────────────────────────────────────────

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/upload/schedule':
            self._upload_schedule()
        elif path == '/api/upload/raw':
            self._upload_raw()
        else:
            self.send_error(404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith('/api/raw/'):
            name = os.path.basename(unquote(path[len('/api/raw/'):]))
            self._delete_raw(name)
        else:
            self.send_error(404)

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _upload_schedule(self):
        name, data = self._parse_upload()
        if not name:
            return
        DROP_DIR.mkdir(exist_ok=True)
        (DROP_DIR / name).write_bytes(data)
        script = BASE_DIR / 'process_drop.py'
        env = {**os.environ, 'GMAIL_USER': ''}
        threading.Thread(
            target=subprocess.run,
            args=([sys.executable, str(script)],),
            kwargs={'env': env, 'check': False},
            daemon=True,
        ).start()
        self._json(200, {'ok': True, 'file': name})

    def _upload_raw(self):
        name, data = self._parse_upload()
        if not name:
            return
        RAW_DIR.mkdir(exist_ok=True)
        (RAW_DIR / name).write_bytes(data)
        url = f'raw/{name}'
        with _pages_lock:
            cfg = _read_pages()
            if not any(_page_url(p) == url for p in cfg.get('pages', [])):
                cfg.setdefault('pages', []).append(
                    {'url': url, 'seconds': cfg.get('page_duration', 60)}
                )
                _write_pages(cfg)
        self._json(200, {'ok': True, 'file': name})

    def _delete_raw(self, name):
        target = RAW_DIR / name
        if not target.exists():
            self.send_error(404, 'Not found')
            return
        target.unlink()
        url = f'raw/{name}'
        with _pages_lock:
            cfg = _read_pages()
            cfg['pages'] = [p for p in cfg.get('pages', []) if _page_url(p) != url]
            _write_pages(cfg)
        self._json(200, {'ok': True})

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _parse_upload(self):
        """Return (safe_filename, bytes) from a multipart/form-data POST, or (None, None)."""
        ct = self.headers.get('Content-Type', '')
        if 'multipart/form-data' not in ct:
            self.send_error(400, 'Expected multipart/form-data')
            return None, None

        boundary = None
        for seg in ct.split(';'):
            seg = seg.strip()
            if seg.startswith('boundary='):
                boundary = seg[9:].strip('"')
                break
        if not boundary:
            self.send_error(400, 'Missing boundary')
            return None, None

        length = int(self.headers.get('Content-Length', 0))
        if length > MAX_UPLOAD:
            self.send_error(413, 'File too large')
            return None, None

        body = self.rfile.read(length)
        delim = ('--' + boundary).encode()

        for chunk in body.split(delim):
            if b'filename=' not in chunk:
                continue
            sep = chunk.find(b'\r\n\r\n')
            if sep == -1:
                continue
            headers = chunk[:sep].decode('utf-8', errors='replace')
            payload = chunk[sep + 4:]
            if payload.endswith(b'\r\n'):
                payload = payload[:-2]

            for line in headers.splitlines():
                if 'filename=' not in line:
                    continue
                for attr in line.split(';'):
                    attr = attr.strip()
                    if attr.startswith('filename='):
                        raw_name = attr[9:].strip('"')
                        # Sanitise: keep only safe characters, prevent path traversal
                        safe = ''.join(
                            c if c.isalnum() or c in '-_.' else '_'
                            for c in os.path.basename(raw_name)
                        )
                        if not safe.lower().endswith('.pdf'):
                            self.send_error(400, 'Only PDF files accepted')
                            return None, None
                        return safe, payload

        self.send_error(400, 'No file part found')
        return None, None

    def _json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f'[{self.log_date_time_string()}] {fmt % args}', flush=True)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    PUBLIC_DIR.mkdir(exist_ok=True)
    httpd = HTTPServer(('', port), Handler)
    print(f'Shop Schedule server on :{port}  (public/ → /)', flush=True)
    httpd.serve_forever()
