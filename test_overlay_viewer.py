"""
Simple viewer for test_overlay_output/ PNGs.
Navigate with Previous / Next buttons.
Open http://127.0.0.1:8001
"""

import io
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

OUTPUT_DIR = Path(__file__).parent / "template_setup" / "batch_setup" / "test_overlay_output"
HOST = "127.0.0.1"
PORT = 8001


def list_images():
    return sorted(OUTPUT_DIR.glob("*.png"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # silence access log

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        images = list_images()

        if not images:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"No images found. Run test_bulk_overlay.py first.")
            return

        idx = int(params.get("i", ["0"])[0])
        idx = max(0, min(idx, len(images) - 1))

        if parsed.path == "/img.png":
            img = Image.open(images[idx]).convert("RGB")
            # scale down for browser display
            max_w = 1400
            if img.width > max_w:
                ratio = max_w / img.width
                img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        name = images[idx].stem
        prev = f"/?i={idx - 1}" if idx > 0 else None
        nxt = f"/?i={idx + 1}" if idx < len(images) - 1 else None

        prev_btn = f'<a class="btn" href="{prev}">← Previous</a>' if prev else '<span class="btn disabled">← Previous</span>'
        next_btn = f'<a class="btn" href="{nxt}">Next →</a>' if nxt else '<span class="btn disabled">Next →</span>'

        html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Overlay Test Viewer</title>
  <style>
    body {{ margin: 0; background: #1a1a1a; color: white; font-family: Helvetica, sans-serif; }}
    .bar {{ display: flex; align-items: center; gap: 16px; padding: 14px 20px; background: #111; }}
    .name {{ font-size: 18px; font-weight: bold; flex: 1; }}
    .counter {{ font-size: 14px; color: #aaa; }}
    .btn {{ padding: 10px 20px; background: #444; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; }}
    .btn.disabled {{ opacity: 0.3; pointer-events: none; }}
    img {{ display: block; max-width: 100%; margin: 0 auto; }}
  </style>
</head>
<body>
  <div class="bar">
    {prev_btn}
    <div class="name">{name}</div>
    <div class="counter">{idx + 1} / {len(images)}</div>
    {next_btn}
  </div>
  <img src="/img.png?i={idx}" alt="{name}">
  <script>
    document.addEventListener('keydown', e => {{
      if (e.key === 'ArrowLeft' && {str(idx > 0).lower()}) location.href = '/?i={idx - 1}';
      if (e.key === 'ArrowRight' && {str(idx < len(images) - 1).lower()}) location.href = '/?i={idx + 1}';
    }});
  </script>
</body>
</html>"""

        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Open http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
