# YouTube clip tool

## Purpose

A local web page that downloads only the time ranges you choose from one YouTube video and saves each range as its own MP4. The full video is never downloaded or saved.

## How to run

From the project folder:

```bash
python3 clip.py
```

`clip.py` starts a server on `127.0.0.1:8765` and opens that page in the browser. The server accepts connections only from this Mac. If port 8765 is already in use, the process exits and prints that the port is taken.

The page and server live in `clip.py`. The HTML is embedded in that file. Tests live in `test_clip.py` and import the pure functions from `clip.py`.

Requires `yt-dlp` and `ffmpeg` on `PATH`. If either is missing, the page reports that and does not start a download.

## Form

- YouTube URL
- Filename prefix. Blank means use the video title.
- One row per clip, each with a start and an end. Rows can be added and removed.
- A line stating that files are written to `output/` next to `clip.py`.
- A submit button.

While a job is running, the page shows which part is in progress (`Part 2 of 3`). When the job finishes, the page lists the saved file paths. The button stays disabled until the job finishes or fails.

## Files

`output/` is created next to `clip.py` if it does not exist.

Part numbers start at 1 and follow row order. The filename is:

```text
{prefix} - part {n} [{start} - {end}].mp4
```

`start` and `end` in the filename are the trimmed text from the form, so `2:02` stays `2:02`.

Example:

```text
output/TNTT Doan VSL LBM 2014 - Nghia Si Modern Dance - part 1 [2:02 - 2:15].mp4
```

## What happens on submit

1. The server checks the form. Invalid input returns an error and does not call yt-dlp.
2. If the prefix is blank, the server reads the video title with `yt-dlp --print`. That call does not download media.
3. The server downloads the rows one at a time. Each row is its own yt-dlp invocation with `--download-sections` set to that row's start and end, `--force-keyframes-at-cuts`, and an MP4 merge. The output path is the final file in `output/`.
4. Nothing in this flow downloads or writes the rest of the video.

Only one job runs at a time. A second submit while a job is running gets the message `A download is already running.`

yt-dlp and ffmpeg are started with an argument list. The form text is never joined into a shell command.

## Validation

Checked before any download:

- The URL host is `youtube.com`, `www.youtube.com`, `m.youtube.com`, or `youtu.be`.
- There is at least one row.
- Each start and end matches `M:SS` or `H:MM:SS`. `M` and `H` are one or more digits. `SS` is exactly two digits from `00` to `59`. In `H:MM:SS`, `MM` is exactly two digits from `00` to `59`. `2:02` and `02:02` are both valid `M:SS` values.
- The start is strictly before the end, compared as seconds.
- After trimming, the prefix does not contain `/`, `\`, or `..`. Other characters are kept, including spaces.

A blank prefix is valid. It is replaced by the video title after validation. The title is passed through the same prefix rules. If the title is empty or fails those rules, the job stops with an error and downloads nothing.

## Errors

- Validation errors and missing `yt-dlp` or `ffmpeg` are shown on the page. No part file is created.
- If a later part fails, earlier parts that finished stay in `output/`. The page lists those paths and shows the yt-dlp or ffmpeg error.
- On failure, the server deletes that part's incomplete `.mp4` and any `.part` file for it. It does not delete parts that already finished.
- The status of a failed job stays visible until the next submit.

## Status

`POST /clip` accepts JSON:

```json
{"url": "https://youtu.be/...", "prefix": "", "parts": [{"start": "2:02", "end": "2:15"}]}
```

Validation and the check for `yt-dlp` and `ffmpeg` happen inside that request, before a job starts. Invalid input returns the error in the response and leaves status `idle`. A valid request starts the job in a background thread, sets status to `running`, and returns immediately. A request that arrives while status is `running` returns `A download is already running.` and does not start a second job.

`GET /status` returns the current state: `idle`, `running`, `done`, or `error`, plus the current part number, the part total, the message, and any saved paths. `done` and `error` stay as they are until the next submit. The page polls `GET /status` about once a second while a job is running.

The server uses a threading HTTP server so status polls are answered while a download runs.

## Testing

Automated tests do not call YouTube, yt-dlp, or ffmpeg. They cover:

- `2:02` parses to 122 seconds, and `1:02:03` parses to 3723 seconds.
- `2:60`, `1:60:00`, and non-matching text are rejected.
- A start that is not before the end is rejected.
- A prefix containing `/`, `\`, or `..` is rejected. A blank prefix is allowed.
- The filename for part 1 with start `2:02` and end `2:15` matches the pattern above.

Manual check: run `python3 clip.py`, submit `https://youtu.be/-BNGtv0R7ho` with ranges `2:02`–`2:15` and `4:30`–`4:45`, and confirm the two files are about 13 and 15 seconds long rather than the full video.

## Out of scope

Playlists, login, a quality picker, choosing another output folder, browser file downloads, a queue of jobs, and sites other than YouTube.
