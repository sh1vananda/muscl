"""
Terminal audio player
"""

import os
import sys
import time
from dataclasses import dataclass

import readchar
from pygame import mixer

KEY_QUIT = "q"
KEY_PAUSE = "p"
KEY_NEXT = "n"


@dataclass
class PlayerState:
    playlist: list[str]
    current_index: int = 0
    is_playing: bool = False
    is_paused: bool = False

    @property
    def current_song(self) -> str:
        return self.playlist[self.current_index] if self.playlist else "No Media"


def init_audio():
    try:
        mixer.init()
    except Exception as e:
        print(f"CRITICAL: Could not initialize audio hardware: {e}")
        sys.exit(1)


def get_playlist(directory: str = "./music") -> list[str]:
    if not os.path.exists(directory):
        os.makedirs(directory)
        return []
    return [f for f in os.listdir(directory) if f.endswith(".mp3")]
