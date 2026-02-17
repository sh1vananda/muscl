"""
Terminal audio player
"""

import msvcrt
import os
import sys
import time
from dataclasses import dataclass

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from pygame import mixer


@dataclass
class PlayerState:
    playlist: list[str]
    idx: int = 0
    is_paused: bool = False
    volume: float = 0.5
    title: str = "Unknown"
    artist: str = "Unknown"

    @property
    def current_file(self):
        return self.playlist[self.idx]


def setup_hardware():
    mixer.pre_init(44100, -16, 2, 512)
    mixer.init()
    mixer.music.set_volume(0.5)


def get_metadata(filepath):
    try:
        audio = EasyID3(filepath)
        title = audio.get("title", [os.path.basename(filepath)])[0]
        artist = audio.get("artist", ["Unknown Artist"])[0]
        return title, artist
    except:
        return os.path.basename(filepath), "Unknown Artist"


def format_time(ms):
    s = max(0, ms // 1000)
    m, s = divmod(s, 60)
    return f"{m:02d}:{s:02d}"


def render_frame(state, elapsed_ms, total_ms):
    progress = min(1.0, elapsed_ms / total_ms) if total_ms > 0 else 0
    bar_width = 30
    filled = int(bar_width * progress)
    bar = "█" * filled + "░" * (bar_width - filled)

    status = "PAUSED" if state.is_paused else "PLAYING"
    vol_pct = int(state.volume * 100)

    meta_text = f"{state.artist} - {state.title}"[:40]

    sys.stdout.write(
        f"\r\033[K[{status}] {bar} {format_time(elapsed_ms)}/{format_time(total_ms)} | Vol: {vol_pct}% | {meta_text}"
    )
    sys.stdout.flush()


def run_player(songs):
    state = PlayerState(playlist=songs)
    setup_hardware()

    def load_track():
        mixer.music.load(state.current_file)
        state.title, state.artist = get_metadata(state.current_file)
        audio_info = MP3(state.current_file)
        duration = audio_info.info.length
        mixer.music.play()
        return int(duration * 1000)

    total_ms = load_track()

    while True:
        if msvcrt.kbhit():
            key = msvcrt.getch()
            try:
                key = key.decode().lower()
            except:
                continue

            if key == "q":
                break
            elif key == "p":
                if state.is_paused:
                    mixer.music.unpause()
                else:
                    mixer.music.pause()
                state.is_paused = not state.is_paused
            elif key == "n":
                state.idx = (state.idx + 1) % len(state.playlist)
                total_ms = load_track()
                state.is_paused = False
            elif key == "b":
                if mixer.music.get_pos() > 2000:
                    total_ms = load_track()
                else:
                    state.idx = (state.idx - 1) % len(state.playlist)
                    total_ms = load_track()
                state.is_paused = False
            elif key in ["=", "+"]:
                state.volume = min(1.0, state.volume + 0.05)
                mixer.music.set_volume(state.volume)
            elif key == "-":
                state.volume = max(0.0, state.volume - 0.05)
                mixer.music.set_volume(state.volume)

        elapsed = mixer.music.get_pos()

        if not mixer.music.get_busy() and not state.is_paused:
            if elapsed == -1 or elapsed >= (total_ms - 500):
                state.idx = (state.idx + 1) % len(state.playlist)
                total_ms = load_track()

        render_frame(state, elapsed, total_ms)
        time.sleep(0.01)

    mixer.quit()


if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "./music"

    if not os.path.exists(target_dir):
        print(f"Error: Directory '{target_dir}' not found.")
        sys.exit(1)

    files = [
        os.path.join(target_dir, f)
        for f in os.listdir(target_dir)
        if f.endswith(".mp3")
    ]

    if not files:
        print(f"No MP3 files found in {target_dir}")
        sys.exit(1)

    try:
        run_player(files)
    except KeyboardInterrupt:
        sys.exit(0)
