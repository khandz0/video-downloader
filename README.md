# Video Downloader

A local page that saves chosen time ranges from one YouTube video as separate MP4 files. Each range is downloaded on its own. The rest of the video is not saved.

## Requirements

- Python 3
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) and [`ffmpeg`](https://ffmpeg.org/) on your `PATH`

On macOS with Homebrew:

```bash
brew install yt-dlp ffmpeg
```

## Run

```bash
python3 clip.py
```

This starts a server at http://127.0.0.1:8765 and opens that page. The server only accepts connections from this machine. If port 8765 is already in use, the process exits.

On the page:

1. Paste a YouTube URL (`youtube.com` or `youtu.be`).
2. Enter a filename prefix, or leave it blank to use the video title.
3. Add one row per clip, with a start and end such as `2:02` and `2:15`. Times can also be `H:MM:SS`.
4. Choose **Save clips**.

Files are written to `output/` next to `clip.py`:

```text
{prefix} - part {n} [{start} - {end}].mp4
```

Example:

```text
output/TNTT Doan VSL LBM 2014 - Nghia Si Modern Dance - part 1 [2:02 - 2:15].mp4
```

Only one download runs at a time. If a later part fails, earlier parts stay in `output/`.

## Tests

```bash
python3 -m unittest test_clip.py
```

The tests check timestamps, ranges, prefixes, and filenames. They do not call YouTube, yt-dlp, or ffmpeg.
