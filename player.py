"""
Terminal audio player
"""

import os

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import msvcrt
import random
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
    is_shuffle: bool = False
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
    bar_width = 20
    filled = int(bar_width * progress)
    bar = "█" * filled + "░" * (bar_width - filled)
    status = "PAUSE" if state.is_paused else "PLAY"
    shuff = " [S]" if state.is_shuffle else ""
    vol_pct = int(state.volume * 100)
    meta = f"{state.artist} - {state.title}"
    line = f"\r\033[2K[{status}]{shuff} {bar} {format_time(elapsed_ms)}/{format_time(total_ms)} | V:{vol_pct}% | {meta}"
    sys.stdout.write(line[:79])
    sys.stdout.flush()


def run_player(songs, start_shuffled=False):
    state = PlayerState(playlist=songs, is_shuffle=start_shuffled)

    if start_shuffled:
        random.shuffle(state.playlist)

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
                sys.stdout.write("\nQuit.\n")
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
            elif key == "s":
                state.is_shuffle = not state.is_shuffle
                if state.is_shuffle:
                    current = state.playlist.pop(state.idx)
                    random.shuffle(state.playlist)
                    state.playlist.insert(0, current)
                    state.idx = 0
                else:
                    current_file = state.current_file
                    state.playlist.sort()
                    state.idx = state.playlist.index(current_file)
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
    args = sys.argv[1:]
    do_shuffle = "--shuffle" in args
    if do_shuffle:
        args.remove("--shuffle")

    target_dir = args[0] if len(args) > 0 else "./music"

    if not os.path.exists(target_dir):
        sys.exit(1)

    files = [
        os.path.join(target_dir, f)
        for f in os.listdir(target_dir)
        if f.endswith(".mp3")
    ]
    if not files:
        sys.exit(1)

    try:
        run_player(files, start_shuffled=do_shuffle)
    except KeyboardInterrupt:
        sys.exit(0)
