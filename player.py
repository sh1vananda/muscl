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
