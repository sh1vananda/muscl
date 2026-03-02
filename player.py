"""
A flawless, minimalist terminal-based MP3 player for Windows.
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

            # Then try to get tags securely
            tags = EasyID3(self.path)
            title_tag = tags.get("title", [])
            artist_tag = tags.get("artist", [])

            if title_tag and str(title_tag[0]).strip():
                self.title = str(title_tag[0]).strip()
            if artist_tag and str(artist_tag[0]).strip():
                self.artist = str(artist_tag[0]).strip()
        except Exception:
            # Fallback seamlessly to filename if tags are unreadable/missing
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
        if not self.tracks:
            return
        current_track = self.current_track
        random.shuffle(self.tracks)
        # Move current track to the front to prevent skipping it immediately
        self.tracks.remove(current_track)
        self.tracks.insert(0, current_track)
        self.current_idx = 0

    def _unshuffle_playlist(self) -> None:
        """Restores the original playlist order, updating current index."""
        if not self.tracks:
            return
        current_track = self.current_track
        self.tracks = list(self.original_playlist)
        self.current_idx = self.tracks.index(current_track)

    @property
    def current_track(self) -> Track:
        return self.tracks[self.current_idx]

    def load_and_play(self) -> None:
        """Loads and starts the current track. Dynamically ejects broken files."""
        if not self.tracks:
            self.running = False
            return

        try:
            mixer.music.load(str(self.current_track.path))
            mixer.music.play()
            self.is_paused = False
            self.is_track_loaded = True
        except Exception:
            # If a file is completely corrupted, fail gracefully and eject it
            self.is_track_loaded = False
            broken_track = self.current_track
            
            self.tracks.remove(broken_track)
            if broken_track in self.original_playlist:
                self.original_playlist.remove(broken_track)

            # Auto-skip to the next available track
            if len(self.tracks) > 0:
                self.current_idx = self.current_idx % len(self.tracks)
                self.load_and_play()
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
        if not self.tracks:
            return
        self.current_idx = (self.current_idx + 1) % len(self.tracks)
        self.load_and_play()

    def previous_track(self) -> None:
        if not self.tracks:
            return
        # If we are more than 2 seconds in, restart track
        if mixer.music.get_pos() > 2000:
            self.load_and_play()
        else:
            # Go back, handling underflow
            self.current_idx = (self.current_idx - 1) % len(self.tracks)
            self.load_and_play()

    def change_volume(self, delta: float) -> None:
        # High precision rounding ensures clean values (no float trailing point errors)
        self.volume = round(max(0.0, min(1.0, self.volume + delta)), 2)
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
        """Draws the player interface to the terminal with crisp formatting."""
        if not self.tracks:
            return

        track = self.current_track
        
        # Elapsed time
        elapsed_ms = mixer.music.get_pos()
        if elapsed_ms < 0:
            elapsed_ms = track.duration_ms if not self.is_paused and self.is_track_loaded else 0

        # Calculate progress
        progress = elapsed_ms / track.duration_ms if track.duration_ms > 0 else 0
        progress = max(0.0, min(1.0, progress))

        # Build progress bar (Cyan filled, Dark Gray empty)
        filled = int(PlayerConfig.BAR_WIDTH * progress)
        filled_str = "█" * filled
        empty_str = "░" * (PlayerConfig.BAR_WIDTH - filled)
        bar_visual = f"\033[36m{filled_str}\033[90m{empty_str}\033[0m"

        # Status text colors (Green = Play, Yellow = Paused)
        status_text = "PAUSED " if self.is_paused else "PLAYING"
        status_color = "\033[93m" if self.is_paused else "\033[92m"
        status_visual = f"{status_color}[{status_text}]\033[0m"
        
        shuffle_visual = " \033[95m[SHUFFLE]\033[0m" if self.is_shuffle else ""
        vol_pct = round(self.volume * 100)
        
        # Formatting components
        time_str = f"{TerminalUI.format_time(elapsed_ms)}/{TerminalUI.format_time(track.duration_ms)}"
        
        # Get console width dynamically to calculate clean text truncation mapping
        try:
            term_cols = os.get_terminal_size().columns
        except OSError:
            term_cols = 120  # Safe fallback
            
        # Hard visual space calculation of UI components to truncate metadata without ripping ANSI codes.
        # Fixed chars approx: " [PLAYING] [SHUFFLE] ██████... 00:00/00:00 | VOL: 100% | "
        ui_logic_len = 59 + (10 if self.is_shuffle else 0)
        max_meta_len = max(5, term_cols - ui_logic_len)
        
        raw_meta = f"{track.artist} - {track.title}"
        truncated_meta = TerminalUI.truncate_string(raw_meta, max_meta_len)
        meta_visual = f"\033[1m{truncated_meta}\033[0m"
        
        # Primary rendering line
        line = f" {status_visual}{shuffle_visual} {bar_visual} {time_str} \033[90m|\033[0m VOL: \033[33m{vol_pct}%\033[0m \033[90m|\033[0m {meta_visual} "

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
        
    if not target.is_dir():
        print(f"Error: Target '{target}' is not a directory.")
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
