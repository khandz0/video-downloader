import errno
import json
import re
import shutil
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
HOST = "127.0.0.1"
PORT = 8765

_TIME_MS = re.compile(r"^(\d+):(\d{2})$")
_TIME_HMS = re.compile(r"^(\d+):(\d{2}):(\d{2})$")
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}

_lock = threading.Lock()
_status = {
    "state": "idle",
    "current": 0,
    "total": 0,
    "message": "",
    "files": [],
}


def parse_timestamp(text):
    value = text.strip()
    hours_match = _TIME_HMS.fullmatch(value)
    if hours_match:
        hours, minutes, seconds = (int(part) for part in hours_match.groups())
        if minutes > 59 or seconds > 59:
            raise ValueError(f"Invalid time: {text}")
        return hours * 3600 + minutes * 60 + seconds
    minutes_match = _TIME_MS.fullmatch(value)
    if minutes_match:
        minutes, seconds = (int(part) for part in minutes_match.groups())
        if seconds > 59:
            raise ValueError(f"Invalid time: {text}")
        return minutes * 60 + seconds
    raise ValueError(f"Invalid time: {text}")


def validate_part(start, end):
    if parse_timestamp(start) >= parse_timestamp(end):
        raise ValueError("Start must be before end.")


def sanitize_prefix(prefix):
    cleaned = prefix.strip()
    if cleaned == "":
        return ""
    if "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise ValueError("Prefix cannot contain /, \\, or ..")
    return cleaned


def clip_filename(prefix, part_number, start, end):
    return f"{prefix} - part {part_number} [{start.strip()} - {end.strip()}].mp4"


def full_filename(prefix):
    return f"{prefix}.mp4"


def validate_youtube_url(url):
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or host not in _YOUTUBE_HOSTS:
        raise ValueError("URL must be a YouTube link.")


def parse_request(data):
    if not isinstance(data, dict):
        raise ValueError("Request must be a JSON object.")
    url = data.get("url", "")
    prefix = data.get("prefix", "")
    parts = data.get("parts")
    if not isinstance(url, str):
        raise ValueError("URL must be a YouTube link.")
    validate_youtube_url(url)
    if not isinstance(prefix, str):
        raise ValueError("Prefix must be text.")
    prefix = sanitize_prefix(prefix)
    whole = data.get("whole", False)
    if not isinstance(whole, bool):
        raise ValueError("Whole video must be yes or no.")
    if not isinstance(parts, list):
        raise ValueError("Add at least one clip.")
    cleaned_parts = []
    for part in parts:
        if not isinstance(part, dict):
            raise ValueError("Each clip needs a start and an end.")
        start = part.get("start", "")
        end = part.get("end", "")
        if not isinstance(start, str) or not isinstance(end, str):
            raise ValueError("Each clip needs a start and an end.")
        start = start.strip()
        end = end.strip()
        if start == "" and end == "":
            continue
        validate_part(start, end)
        cleaned_parts.append({"start": start, "end": end})
    if not whole and len(cleaned_parts) == 0:
        raise ValueError("Add at least one clip.")
    return url.strip(), prefix, cleaned_parts, whole


def require_tools():
    missing = [name for name in ("yt-dlp", "ffmpeg") if shutil.which(name) is None]
    if missing:
        raise RuntimeError(f"Missing {' and '.join(missing)} on PATH.")


def video_title(url):
    result = subprocess.run(
        ["yt-dlp", "--no-update", "--no-playlist", "--print", "%(title)s", url],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Could not read the video title.").strip()
        raise RuntimeError(detail.splitlines()[-1])
    title = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    cleaned = sanitize_prefix(title)
    if cleaned == "":
        raise ValueError("Video title cannot be used as a filename.")
    return cleaned


def _cleanup_failed_part(destination, before):
    if destination not in before:
        destination.unlink(missing_ok=True)
    if not destination.parent.exists():
        return
    for path in destination.parent.iterdir():
        if path not in before and path != destination:
            path.unlink(missing_ok=True)


def download_command(url, destination, start=None, end=None):
    command = [
        "yt-dlp",
        "--no-update",
        "--no-playlist",
        "--force-overwrites",
        "-f",
        "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "--merge-output-format",
        "mp4",
    ]
    if start is not None:
        command.extend(
            [
                "--download-sections",
                f"*{start}-{end}",
                "--force-keyframes-at-cuts",
            ]
        )
    command.extend(["-o", str(destination), url])
    return command


def download_section(url, start, end, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    before = set(destination.parent.iterdir())
    command = download_command(url, destination, start=start, end=end)
    result = subprocess.run(command, check=False, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        _cleanup_failed_part(destination, before)
        detail = (result.stderr or "Download failed.").strip()
        raise RuntimeError("\n".join(detail.splitlines()[-20:]) or "Download failed.")


def _set_status(**kwargs):
    with _lock:
        for key, value in kwargs.items():
            _status[key] = list(value) if key == "files" else value


def public_status():
    with _lock:
        return {
            "state": _status["state"],
            "current": _status["current"],
            "total": _status["total"],
            "message": _status["message"],
            "files": list(_status["files"]),
        }


def _run_job(url, prefix, parts, whole):
    files = []
    steps = len(parts) + (1 if whole else 0)
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        chosen = prefix
        if chosen == "":
            _set_status(
                state="running",
                current=0,
                total=steps,
                message="Reading video title",
                files=[],
            )
            chosen = video_title(url)
        step = 0
        if whole:
            step += 1
            _set_status(
                state="running",
                current=step,
                total=steps,
                message="Downloading full video",
                files=files,
            )
            destination = OUTPUT_DIR / full_filename(chosen)
            download_section(url, None, None, destination)
            files.append(str(destination))
        for index, part in enumerate(parts, start=1):
            step += 1
            _set_status(
                state="running",
                current=step,
                total=steps,
                message=f"Part {index} of {len(parts)}",
                files=files,
            )
            destination = OUTPUT_DIR / clip_filename(
                chosen, index, part["start"], part["end"]
            )
            download_section(url, part["start"], part["end"], destination)
            files.append(str(destination))
        _set_status(
            state="done",
            current=steps,
            total=steps,
            message="Saved.",
            files=files,
        )
    except Exception as exc:
        _set_status(state="error", message=str(exc), files=files)


def start_job(url, prefix, parts, whole):
    steps = len(parts) + (1 if whole else 0)
    with _lock:
        if _status["state"] == "running":
            raise RuntimeError("A download is already running.")
        _status.update(
            state="running",
            current=0,
            total=steps,
            message="Starting",
            files=[],
        )
    threading.Thread(
        target=_run_job, args=(url, prefix, parts, whole), daemon=True
    ).start()


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Video clips</title>
  <style>
    :root { color-scheme: light; }
    body { margin: 0; font: 16px/1.45 "Iowan Old Style", Palatino, Georgia, serif; background: #f4f1ea; color: #1c1915; }
    main { max-width: 40rem; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
    h1 { font-size: 1.8rem; font-weight: 600; margin: 0 0 0.4rem; }
    p.note { margin: 0 0 1.5rem; color: #5c564c; }
    label { display: block; font: 600 0.85rem/1.2 ui-sans-serif, system-ui, sans-serif; margin-bottom: 0.35rem; }
    input { display: block; width: 100%; box-sizing: border-box; margin-top: 0.35rem; font: 1rem/1.3 ui-sans-serif, system-ui, sans-serif; padding: 0.55rem 0.65rem; border: 1px solid #c9c1b4; border-radius: 6px; background: #fff; }
    .field { margin-bottom: 1rem; }
    .row { display: grid; grid-template-columns: 1fr 1fr auto; gap: 0.6rem; align-items: end; margin-bottom: 0.6rem; }
    button { font: 600 0.95rem/1 ui-sans-serif, system-ui, sans-serif; border: 0; border-radius: 6px; padding: 0.7rem 1rem; background: #1c1915; color: #f4f1ea; cursor: pointer; }
    button.secondary, button.remove { background: transparent; color: #1c1915; border: 1px solid #c9c1b4; }
    button.remove { padding: 0.55rem 0.7rem; }
    button:disabled { opacity: 0.45; cursor: default; }
    label.check { display: flex; align-items: center; gap: 0.55rem; margin: 0.2rem 0 1rem; font: 1rem/1.3 ui-sans-serif, system-ui, sans-serif; }
    label.check input { width: 1rem; height: 1rem; margin: 0; }
    .actions { display: flex; gap: 0.6rem; margin-top: 0.4rem; }
    #status { margin-top: 1.4rem; white-space: pre-wrap; }
    #files { padding-left: 1.1rem; }
    #files li { margin: 0.25rem 0; word-break: break-all; }
  </style>
</head>
<body>
  <main>
    <h1>Video clips</h1>
    <p class="note">Each row downloads only that time range into <code>output/</code>. Check the box to also save the full video as <code>prefix.mp4</code>.</p>
    <form id="form">
      <div class="field">
        <label for="url">YouTube URL</label>
        <input id="url" name="url" type="url" required placeholder="https://youtu.be/...">
      </div>
      <div class="field">
        <label for="prefix">Filename prefix</label>
        <input id="prefix" name="prefix" type="text" placeholder="Leave blank to use the video title">
      </div>
      <label class="check" for="whole"><input id="whole" name="whole" type="checkbox">Download the whole video</label>
      <div id="rows"></div>
      <div class="actions">
        <button type="button" class="secondary" id="add">Add part</button>
        <button type="submit" id="save">Save clips</button>
      </div>
    </form>
    <div id="status"></div>
    <ul id="files"></ul>
  </main>
  <script>
    const rows = document.querySelector("#rows");
    const status = document.querySelector("#status");
    const files = document.querySelector("#files");
    const save = document.querySelector("#save");
    const whole = document.querySelector("#whole");

    function syncRequired() {
      const needed = !whole.checked;
      for (const input of rows.querySelectorAll("input")) input.required = needed;
    }

    function addRow(start, end) {
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `
        <label>Start<input class="start" required placeholder="2:02" value="${start || ""}"></label>
        <label>End<input class="end" required placeholder="2:15" value="${end || ""}"></label>
        <button type="button" class="remove">Remove</button>`;
      row.querySelector(".remove").addEventListener("click", () => {
        if (rows.children.length === 1) return;
        row.remove();
      });
      rows.appendChild(row);
      syncRequired();
    }

    addRow();
    whole.addEventListener("change", syncRequired);
    document.querySelector("#add").addEventListener("click", () => addRow());

    function show(data) {
      status.textContent = data.message || "";
      files.replaceChildren();
      for (const path of data.files || []) {
        const item = document.createElement("li");
        item.textContent = path;
        files.appendChild(item);
      }
    }

    async function poll() {
      const response = await fetch("/status");
      const data = await response.json();
      show(data);
      if (data.state === "running") {
        setTimeout(poll, 1000);
      } else {
        save.disabled = false;
      }
    }

    document.querySelector("#form").addEventListener("submit", async (event) => {
      event.preventDefault();
      save.disabled = true;
      files.replaceChildren();
      status.textContent = "Starting";
      const parts = [...rows.children].map((row) => ({
        start: row.querySelector(".start").value.trim(),
        end: row.querySelector(".end").value.trim(),
      }));
      const response = await fetch("/clip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: document.querySelector("#url").value.trim(),
          prefix: document.querySelector("#prefix").value,
          whole: whole.checked,
          parts,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        status.textContent = data.error || "Could not start.";
        save.disabled = false;
        return;
      }
      poll();
    });
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/status":
            self._json(200, public_status())
            return
        self._json(404, {"error": "Not found."})

    def do_POST(self):
        if self.path != "/clip":
            self._json(404, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                raise ValueError("Request is too large.")
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("Request must be JSON.") from exc
            url, prefix, parts, whole = parse_request(data)
            require_tools()
            start_job(url, prefix, parts, whole)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except RuntimeError as exc:
            code = 409 if str(exc) == "A download is already running." else 400
            self._json(code, {"error": str(exc)})
        else:
            self._json(200, {"ok": True})

    def _json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


def main():
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print(f"Port {PORT} is already in use.", flush=True)
        else:
            print(exc, flush=True)
        raise SystemExit(1) from exc
    url = f"http://{HOST}:{PORT}"
    print(url, flush=True)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)


if __name__ == "__main__":
    main()
