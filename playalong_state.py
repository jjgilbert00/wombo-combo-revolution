"""Small types shared by the playalong controller and its views."""
from collections import namedtuple
from enum import Enum


class RunningState(Enum):
    STOPPED = 0
    PLAYING = 1
    RECORDING = 2


# A consistent view of the controller (see PlayalongController.status): whether it's recording or
# playing, practice and loop on, the demo playing ("recording", "key inputs" or None), lead-in frames
# left, the frame at the line and the track's length, key inputs hit and how many there are, how
# many notes, frames played and matched, frames filled in while recording late, whether buttons are
# remapped, the recording's game and whether actions are shown.
PlayalongStatus = namedtuple(
    "PlayalongStatus",
    "recording playing practice loop demo lead frame length hits key_inputs notes attempted matched filled remapped "
    "game show_actions")
