#!/usr/bin/env python3
"""server.py — HTTP server for Shop Schedule.

Serves public/ as static files and provides a small upload API:
  POST /api/upload/schedule  — receive Foreman's Report PDF, trigger process_drop.py
  POST /api/upload/raw       — receive display PDF, save to public/raw/, update pages.json
  DELETE /api/raw/<name>     — remove a display PDF and its pages.json entry
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

BASE_DIR = Path(__file__).parent
PUBLIC_DIR = BASE_DIR / 'public'
RAW_DIR = PUBLIC_DIR / 'raw'
PAGES_JSON = PUBLIC_DIR / 'pages.json'
DROP_DIR = BASE_DIR / 'incoming'
MAX_UPLOAD = 50 * 1024 * 1024  # 50 MB
PORT = int(os.environ.get('PORT', 8080))

DEPT_COLORS_PATH = PUBLIC_DIR / 'dept_colors.json'

_pages_lock = threading.Lock()
_schedule_lock = threading.Lock()  # prevents concurrent process_drop.py runs
_dept_colors_lock = threading.Lock()


def _read_pages():
    if PAGES_JSON.exists():
        with open(PAGES_JSON) as f:
            return json.load(f)
    return {'scroll_cycles': 2, 'page_duration': 60, 'transition_ms': 1500, 'pages': []}


def _write_pages(cfg):
    fd, tmp = tempfile.mkstemp(dir=PAGES_JSON.parent, suffix='.json.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(cfg, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, PAGES_JSON)
    except Exception:
        os.unlink(tmp)
        raise


def _page_url(p):
    return p if isinstance(p, str) else p.get('url', '')


# Only characters safe to embed in a shell script URL
_HOST_RE = re.compile(r'^(\[[\da-fA-F:]+\]|[A-Za-z0-9.\-]+)(?::(\d{1,5}))?$')


def _sanitize_host(host):
    """Return host if it is safe to embed in a shell script, else None."""
    if not host or len(host) > 255:
        return None
    m = _HOST_RE.fullmatch(host)
    if not m:
        return None
    port = m.group(2)
    if port and not (1 <= int(port) <= 65535):
        return None
    return host


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    # ── Routing ──────────────────────────────────────────────────────────────

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/install':
            self._serve_client_installer()
        elif path == '/api/dept-colors':
            self._get_dept_colors()
        elif path == '/api/pages':
            self._get_pages()
        else:
            super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/upload/schedule':
            self._upload_schedule()
        elif path == '/api/upload/raw':
            self._upload_raw()
        elif path == '/api/dept-colors':
            self._post_dept_colors()
        elif path == '/api/pages':
            self._post_pages()
        else:
            self.send_error(404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith('/api/raw/'):
            name = os.path.basename(unquote(path[len('/api/raw/'):]))
            self._delete_raw(name)
        elif path == '/api/dept-colors':
            self._delete_dept_colors()
        else:
            self.send_error(404)

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _upload_schedule(self):
        name, data = self._parse_upload()
        if not name:
            return
        if not _schedule_lock.acquire(blocking=False):
            self._json(409, {'ok': False, 'error': 'Schedule update already in progress'})
            return
        DROP_DIR.mkdir(exist_ok=True)
        (DROP_DIR / name).write_bytes(data)
        script = BASE_DIR / 'process_drop.py'
        env = {**os.environ, 'GMAIL_USER': ''}

        def _run():
            try:
                r = subprocess.run(
                    [sys.executable, str(script)], env=env,
                    capture_output=True, text=True, check=False,
                )
                if r.stdout:
                    print(r.stdout, end='', flush=True)
                if r.returncode != 0:
                    print(f'[process_drop] exit {r.returncode}: {r.stderr}', flush=True)
            finally:
                _schedule_lock.release()

        threading.Thread(target=_run, daemon=True).start()
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

    def _get_dept_colors(self):
        with _dept_colors_lock:
            data = DEPT_COLORS_PATH.read_bytes() if DEPT_COLORS_PATH.exists() else b'{}'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _post_dept_colors(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            self.send_error(400, 'Bad Request')
            return
        if length < 0 or length > 64 * 1024:
            self.send_error(413 if length > 0 else 400, 'Bad Request')
            return
        body = self.rfile.read(length)
        _hex = re.compile(r'^#[0-9a-fA-F]{6}$')
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError
            for k, v in data.items():
                if not isinstance(k, str) or not isinstance(v, dict):
                    raise ValueError
                if not isinstance(v.get('bg'), str) or not _hex.fullmatch(v['bg']):
                    raise ValueError
                if not isinstance(v.get('accent'), str) or not _hex.fullmatch(v['accent']):
                    raise ValueError
        except (json.JSONDecodeError, ValueError):
            self.send_error(400, 'Invalid payload')
            return
        with _dept_colors_lock:
            tmp = DEPT_COLORS_PATH.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
            tmp.replace(DEPT_COLORS_PATH)
        self._json(200, {'ok': True})

    def _delete_dept_colors(self):
        with _dept_colors_lock:
            if DEPT_COLORS_PATH.exists():
                DEPT_COLORS_PATH.unlink()
        self._json(200, {'ok': True})

    def _get_pages(self):
        with _pages_lock:
            cfg = _read_pages()
        data = json.dumps(cfg, indent=2).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _post_pages(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            self.send_error(400, 'Bad Request')
            return
        if length < 0 or length > 64 * 1024:
            self.send_error(413 if length > 0 else 400, 'Bad Request')
            return
        body = self.rfile.read(length)
        try:
            cfg = json.loads(body)
            if not isinstance(cfg, dict) or not isinstance(cfg.get('pages', []), list):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            self.send_error(400, 'Invalid payload')
            return
        with _pages_lock:
            _write_pages(cfg)
        self._json(200, {'ok': True})

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _serve_client_installer(self):
        script_path = BASE_DIR / 'install-client.sh'
        if not script_path.exists():
            self.send_error(404, 'Client installer not found')
            return
        raw_host = self.headers.get('Host', '')
        host = _sanitize_host(raw_host) or f'localhost:{PORT}'
        script = script_path.read_text().replace('__SERVER_URL__', f'http://{host}')
        body = script.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
    PUBLIC_DIR.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer(('', PORT), Handler)
    print(f'Shop Schedule server on :{PORT}  (public/ → /)', flush=True)
    httpd.serve_forever()
