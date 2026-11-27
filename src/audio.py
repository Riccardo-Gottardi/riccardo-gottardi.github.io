# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "kokoro>=0.9.4,<1",
#   "soundfile>=0.12",
#   "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
# ]
# ///
"""Record the audio version of every post with Kokoro, a local neural text-to-speech model.

    uv run src/audio.py              record the posts that have no up-to-date recording
    uv run src/audio.py --drafts     include drafts (for the local preview)
    uv run src/audio.py --only bias  only posts whose source path contains "bias"
    uv run src/audio.py --prune      also delete recordings no post uses any more

Then rebuild the site: the build copies each recording next to its post as audio.mp3 and shows a player.

How it fits together:
- `build.py --speech` gives the text to read for each post (rules in src/speech.py) and a key,
  a hash of the text, the voice and the speed (set in content/site.yml, `audio:`).
- Recordings are cached in audio/<key>.mp3 and committed, so they are made only once: a post
  is re-recorded only when its spoken text, the voice or the speed change.
- audio/manifest.json keeps each recording's length (the player shows it in minutes).
- Each MP3 carries ID3 tags (title, author, year, license and its URL, the post's address), so a
  downloaded file still says whose it is and under which terms. They come from content/site.yml
  and are rewritten in place, without re-recording, whenever they change.

This is a standalone script with its own environment (the header above): Kokoro does not run on
the site's Python 3.14 yet. The model (hexgrad/Kokoro-82M, Apache-2.0, about 330 MB) downloads
on the first run into the Hugging Face cache. It also needs ffmpeg (`brew install ffmpeg`).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "audio"
MANIFEST = AUDIO / "manifest.json"
RATE = 24_000  # Kokoro's sample rate
PAUSE = 0.5  # seconds of silence between paragraphs
BITRATE = "64k"  # mono MP3: clear speech at about 0.5 MB per minute


def fail(msg: str) -> None:
    raise SystemExit(f"error: {msg}")


def usable_hf_cache() -> None:
    """Fall back to the default model cache when HF_HOME points to a missing drive."""
    hf = os.environ.get("HF_HOME")
    if not hf:
        return
    anchor = Path(hf)
    while not anchor.exists():
        anchor = anchor.parent
    if not os.access(anchor, os.W_OK):  # e.g. /Volumes/<drive>/hf with the drive unplugged
        default = Path.home() / ".cache" / "huggingface"
        print(f"  note: HF_HOME={hf} is not available, using {default}")
        os.environ["HF_HOME"] = str(default)


def jobs_from_build(drafts: bool) -> list[dict]:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}  # let uv pick the site's own env
    cmd = ["uv", "run", "--project", str(ROOT), str(ROOT / "src" / "build.py"), "--speech"]
    r = subprocess.run(cmd + (["--drafts"] if drafts else []), cwd=ROOT, env=env, capture_output=True, text=True)
    if r.stderr.strip():
        print(r.stderr.rstrip())
    if r.returncode:
        raise SystemExit(r.returncode)
    return json.loads(r.stdout)


def record(job: dict, pipelines: dict, dest: Path) -> float:
    """Synthesize the job's text into dest (MP3). Returns the length in seconds."""
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    voice = job["voice"]
    lang = voice[0]  # a = American English, b = British English, ...
    if lang not in pipelines:
        pipelines[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    pipe = pipelines[lang]

    pause = np.zeros(int(RATE * PAUSE), dtype=np.float32)
    parts = []
    for paragraph in job["text"].split("\n"):
        for result in pipe(paragraph, voice=voice, speed=job["speed"], split_pattern=None):
            if result.audio is not None:
                parts.append(result.audio.numpy())
        parts.append(pause)
    audio = np.concatenate(parts)

    with tempfile.TemporaryDirectory() as tmp:
        wav, mp3 = Path(tmp) / "a.wav", Path(tmp) / "a.mp3"
        sf.write(wav, audio, RATE)
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-ac", "1", "-codec:a", "libmp3lame",
             "-b:a", BITRATE, "-map_metadata", "-1", "-id3v2_version", "3", *metadata_args(job["tags"]), str(mp3)],
            check=True,
        )
        shutil.move(mp3, dest)  # only complete files land in audio/
    return len(audio) / RATE


def metadata_args(tags: dict) -> list[str]:
    return [arg for k, v in tags.items() for arg in ("-metadata", f"{k}={v}")]


def current_tags(mp3: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(mp3)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout).get("format", {}).get("tags", {})


def retag(mp3: Path, tags: dict) -> bool:
    """Rewrite the ID3 tags of a recording if they differ from `tags` (no re-encoding). True if changed."""
    have = {k.lower(): v for k, v in current_tags(mp3).items()}
    if all(have.get(k.lower()) == v for k, v in tags.items()):
        return False
    tmp = mp3.with_suffix(".tmp.mp3")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), "-map", "0:a", "-c", "copy",
                    "-map_metadata", "-1", "-id3v2_version", "3", *metadata_args(tags), str(tmp)], check=True)
    tmp.replace(mp3)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Record the audio version of the posts (cached in audio/).")
    parser.add_argument("--drafts", action="store_true", help="also record draft posts")
    parser.add_argument("--only", metavar="TEXT", help="only posts whose source path contains TEXT")
    parser.add_argument("--prune", action="store_true", help="delete recordings that no post uses any more")
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        fail("ffmpeg not found; install it with `brew install ffmpeg`")
    usable_hf_cache()

    jobs = jobs_from_build(args.drafts)
    AUDIO.mkdir(exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.is_file() else {}
    todo = [j for j in jobs if not (AUDIO / f"{j['key']}.mp3").is_file()]
    if args.only:
        todo = [j for j in todo if args.only in j["source"]]

    pipelines: dict = {}
    for i, job in enumerate(todo, 1):
        words = len(job["text"].split())
        print(f"[{i}/{len(todo)}] {job['source']} ({words} words, voice {job['voice']})", flush=True)
        start = time.monotonic()
        seconds = record(job, pipelines, AUDIO / f"{job['key']}.mp3")
        manifest[job["key"]] = {"seconds": round(seconds, 1), "source": job["source"], "voice": job["voice"]}
        MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")  # after each post: safe to interrupt
        print(f"      {seconds / 60:.1f} min of audio in {time.monotonic() - start:.0f} s", flush=True)

    # tags (title, author, license…) can change without the text: update them in place
    retagged = [f"{j['source']} ({j['voice']})" for j in jobs if (AUDIO / f"{j['key']}.mp3").is_file()
                and retag(AUDIO / f"{j['key']}.mp3", j["tags"])]
    for source in retagged:
        print(f"  updated the tags of the recording of {source}")

    if args.prune:
        used = {j["key"] for j in jobs}
        for mp3 in sorted(AUDIO.glob("*.mp3")):
            if mp3.stem not in used:
                print(f"  removed {mp3.relative_to(ROOT)} ({manifest.get(mp3.stem, {}).get('source', 'unknown post')})")
                mp3.unlink()
                manifest.pop(mp3.stem, None)
        MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")

    if not todo and not retagged:
        print("All recordings are up to date.")
    else:
        print("Done. Rebuild the site to publish them: uv run src/build.py")


if __name__ == "__main__":
    sys.exit(main())
