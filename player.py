"""
Terminal audio player
"""

import ctypes
import os
import random
import sys
import time
from pathlib import Path
from typing import List

import msvcrt

import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
from pygame import mixer


class PlayerConfig:
    SAMPLE_RATE = 44100
    CHANNELS = 2
    BUFFER = 512
    STARTING_VOLUME = 0.5
    VOLUME_STEP = 0.05
    UI_REFRESH_RATE = 0.05  # seconds
    BAR_WIDTH = 20


class TerminalUI:
    """Handles all terminal manipulation and formatting."""
    
    @staticmethod
    def enable_ansi_escape_sequences() -> None:
        """Enables ANSI escape sequences in the Windows console."""
        if os.name == "nt":
            try:
                kernel32 = ctypes.windll.kernel32
                console_handle = kernel32.GetStdHandle(-11)
                mode = ctypes.c_ulong()
                kernel32.GetConsoleMode(console_handle, ctypes.byref(mode))
                mode.value |= 0x0004
                kernel32.SetConsoleMode(console_handle, mode)
            except Exception:
                pass

    @staticmethod
    def clear_line() -> None:
        """Clears the current line on the console."""
        sys.stdout.write("\033[2K\r")
        sys.stdout.flush()

    @staticmethod
    def format_time(ms: int) -> str:
        """Formats milliseconds into MM:SS. Handle negative/zero gracefully."""
        if ms < 0:
            ms = 0
        s = ms // 1000
        m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}"

    @staticmethod
    def truncate_string(text: str, max_length: int) -> str:
        """Truncates a string with an ellipsis if it exceeds max_length."""
        if max_length <= 0:
            return ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."


class Track:
    """Represents a playable audio track with metadata."""
    
    def __init__(self, filepath: Path):
        self.path = filepath
        self.title = self.path.stem
        self.artist = "Unknown Artist"
        self.duration_ms = 0

        self._load_metadata()

    def _load_metadata(self) -> None:
        try:
            # First get duration
            audio_info = MP3(self.path)
            self.duration_ms = int(audio_info.info.length * 1000)

            # Then try to get tags
            tags = EasyID3(self.path)
            if "title" in tags:
                self.title = tags["title"][0]
            if "artist" in tags:
                self.artist = tags["artist"][0]
        except mutagen.MutagenError:
            # Fallback to filename if tags are reasonably unreadable
            pass
        except Exception:
            # Catch any other exceptions (e.g., MP3 parsing error)
            pass


class MusclPlayer:
    """Main player application encapsulating state and playback logic."""

    def __init__(self, target_dir: Path, shuffle_start: bool = False):
        self.target_dir = target_dir
        
        # Discover tracks
        self.tracks: List[Track] = self._discover_tracks()
        if not self.tracks:
            print(f"Error: No MP3 files found in '{self.target_dir}'.")
            sys.exit(1)

        # State
        self.original_playlist = list(self.tracks)
        self.is_shuffle = shuffle_start
        self.is_paused = False
        self.volume = PlayerConfig.STARTING_VOLUME
        self.current_idx = 0
        self.running = True
        self.is_track_loaded = False

        if self.is_shuffle:
            self._shuffle_playlist()

        # Hardware initialization
        self._init_hardware()

    def _discover_tracks(self) -> List[Track]:
        tracks = []
        for file in self.target_dir.iterdir():
            if file.is_file() and file.suffix.lower() == ".mp3":
                tracks.append(Track(file))
        # Ensure consistent order before any shuffling
        tracks.sort(key=lambda t: t.path.name.lower())
        return tracks

    def _init_hardware(self) -> None:
        # Pre-init helps reduce audio latency/stuttering in pygame
        mixer.pre_init(
            PlayerConfig.SAMPLE_RATE,
            -16,
            PlayerConfig.CHANNELS,
            PlayerConfig.BUFFER
        )
        mixer.init()
        mixer.music.set_volume(self.volume)
        TerminalUI.enable_ansi_escape_sequences()

    def _shuffle_playlist(self) -> None:
        """Shuffles the playlist, keeping the current track (if any) at index 0."""
        current_track = self.current_track
        random.shuffle(self.tracks)
        # Move current track to the front to prevent skipping it immediately
        self.tracks.remove(current_track)
        self.tracks.insert(0, current_track)
        self.current_idx = 0

    def _unshuffle_playlist(self) -> None:
        """Restores the original playlist order, updating current index."""
        current_track = self.current_track
        self.tracks = list(self.original_playlist)
        self.current_idx = self.tracks.index(current_track)

    @property
    def current_track(self) -> Track:
        return self.tracks[self.current_idx]

    def load_and_play(self) -> None:
        """Loads and starts the current track."""
        try:
            mixer.music.load(str(self.current_track.path))
            mixer.music.play()
            self.is_paused = False
            self.is_track_loaded = True
        except Exception:
            # If a file fails to load, skip to next or stop if it's the only one
            self.is_track_loaded = False
            if len(self.tracks) > 1:
                self.next_track()
            else:
                self.running = False

    def toggle_pause(self) -> None:
        if not self.is_track_loaded:
            return
            
        if self.is_paused:
            mixer.music.unpause()
        else:
            mixer.music.pause()
        self.is_paused = not self.is_paused

    def toggle_shuffle(self) -> None:
        self.is_shuffle = not self.is_shuffle
        if self.is_shuffle:
            self._shuffle_playlist()
        else:
            self._unshuffle_playlist()

    def next_track(self) -> None:
        self.current_idx = (self.current_idx + 1) % len(self.tracks)
        self.load_and_play()

    def previous_track(self) -> None:
        # If we are more than 2 seconds in, restart track
        if mixer.music.get_pos() > 2000:
            self.load_and_play()
        else:
            # Go back, handling underflow
            self.current_idx = (self.current_idx - 1) % len(self.tracks)
            self.load_and_play()

    def change_volume(self, delta: float) -> None:
        self.volume = max(0.0, min(1.0, self.volume + delta))
        mixer.music.set_volume(self.volume)

    def handle_input(self) -> None:
        """Processes keyboard input smoothly."""
        while msvcrt.kbhit():
            key_bytes = msvcrt.getch()
            
            # Handle special keys (e.g. arrows) which send two bytes
            if key_bytes in (b"\x00", b"\xe0"):
                if msvcrt.kbhit():
                    _ = msvcrt.getch()
                continue

            try:
                key = key_bytes.decode("utf-8").lower()
            except UnicodeDecodeError:
                continue

            if key == "q":
                self.running = False
                TerminalUI.clear_line()
                print("Playback stopped.")
                break
            elif key in ("p", " "):
                self.toggle_pause()
            elif key == "n":
                self.next_track()
            elif key == "b":
                self.previous_track()
            elif key == "s":
                self.toggle_shuffle()
            elif key in ("=", "+"):
                self.change_volume(PlayerConfig.VOLUME_STEP)
            elif key == "-":
                self.change_volume(-PlayerConfig.VOLUME_STEP)

    def render(self) -> None:
        """Draws the player interface to the terminal."""
        track = self.current_track
        
        # Elapsed time
        # get_pos returns time played in ms (stops increasing when paused).
        # It returns -1 if play fails or track finishes.
        elapsed_ms = mixer.music.get_pos()
        if elapsed_ms < 0:
            elapsed_ms = track.duration_ms if not self.is_paused and self.is_track_loaded else 0

        # Calculate progress
        progress = elapsed_ms / track.duration_ms if track.duration_ms > 0 else 0
        progress = max(0.0, min(1.0, progress))

        # Build progress bar
        bar_width = PlayerConfig.BAR_WIDTH
        filled = int(bar_width * progress)
        bar = "█" * filled + "░" * (bar_width - filled)

        # Status text
        status = "PAUSED " if self.is_paused else "PLAYING"
        shuffle_str = " [SHUFFLE]" if self.is_shuffle else ""
        vol_pct = round(self.volume * 100)
        
        # Formatting components
        time_str = f"{TerminalUI.format_time(elapsed_ms)}/{TerminalUI.format_time(track.duration_ms)}"
        meta_str = f"{track.artist} - {track.title}"
        
        # Primary rendering line
        line = f" [{status}]{shuffle_str} {bar} {time_str} | VOL: {vol_pct}% | {meta_str} "
        
        # Get console width dynamically to avoid layout wrap-around bugs
        try:
            term_cols = os.get_terminal_size().columns
        except OSError:
            term_cols = 120  # Safe fallback
            
        line = TerminalUI.truncate_string(line, term_cols - 1)

        # Print with carriage return seamlessly
        sys.stdout.write(f"\r{line}\033[K")
        sys.stdout.flush()

    def run(self) -> None:
        """Main player loop."""
        self.load_and_play()

        try:
            while self.running:
                self.handle_input()

                # If music isn't busy and we aren't paused, track naturally finished
                if self.running and not self.is_paused and not mixer.music.get_busy():
                    self.next_track()

                if self.running:
                    self.render()
                    
                time.sleep(PlayerConfig.UI_REFRESH_RATE)
        except KeyboardInterrupt:
            self.running = False
            TerminalUI.clear_line()
            print("Exiting...")
        finally:
            mixer.quit()


def get_target_directory(args: List[str]) -> Path:
    """Determine the music directory from arguments or default."""
    if args:
        target = Path(args[0])
    else:
        # Default to "music" directory alongside the script
        script_dir = Path(os.path.abspath(__file__)).parent
        target = script_dir / "music"
        
    if not target.exists():
        print(f"Error: Directory '{target}' does not exist.")
        sys.exit(1)
        
    return target


def main() -> None:
    args = sys.argv[1:]
    
    # Parse options
    do_shuffle = False
    if "--shuffle" in args:
        do_shuffle = True
        args.remove("--shuffle")

    target_dir = get_target_directory(args)

    print("\n  \033[1mControls\033[0m: [P/Space] Play/Pause | [N] Next | [B] Prev/Restart | [S] Shuffle")
    print("            [+/-] Volume Control | [Q] Quit\n")

    player = MusclPlayer(target_dir=target_dir, shuffle_start=do_shuffle)
    player.run()


if __name__ == "__main__":
    main()
