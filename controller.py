import threading
import time
import math
import random


def get_neutral_controller_state():
    return {
        "direction": 5,
        "A": 0,
        "B": 0,
        "X": 0,
        "Y": 0,
        "RT": 0,
        "RB": 0,
        "LT": 0,
        "LB": 0,
    }


def get_random_controller_state():
    return {
        "direction": math.floor(random.random() * 9) + 1,
        "A": round(0.51*random.random()),
        "B": round(0.51*random.random()),
        "X": round(0.51*random.random()),
        "Y": round(0.51*random.random()),
        "RT": round(0.51*random.random()),
        "RB": round(0.51*random.random()),
        "LT": round(0.51*random.random()),
        "LB": round(0.51*random.random())
    }


def get_cool_controller_pattern(frames = 180):
    circles = [1,2,3,6,9,8,7,4]
    inputs = [get_random_controller_state() for _ in range(frames)]
    for i, input in enumerate(inputs[0:len(inputs)//2]):
        if i % 10 != 1:
            input["direction"] = inputs[i-1]["direction"]
            continue
        curdir = circles.pop()
        circles.insert(0, curdir)
        input["direction"] = curdir

    for i, input in enumerate(inputs[len(inputs)//2 :]):
        if i % 10 != 1:
            input["direction"] = inputs[len(inputs)//2 + i-1]["direction"]
            continue
        curdir = circles.pop(0)
        circles.append(curdir)
        input["direction"] = curdir
    return inputs


class ControllerReader:
    def __init__(self, joystick):
        # Initialize game controller
        self.joystick = joystick
        self.joystick.init()
        self.state = {}

    def get_direction(self, hat_state):
        dirmap = [[1, 4, 7], [2, 5, 8], [3, 6, 9]]
        # hat values range from -1 to 1 so we add 1 to get array indices 0 to 2
        return dirmap[hat_state[0] + 1][hat_state[1] + 1]

    def update_state(self):
        if self.joystick:
            self.state = {
                "direction": self.get_direction(self.joystick.get_hat(0)),
                "X": self.joystick.get_button(2),
                "Y": self.joystick.get_button(3),
                "A": self.joystick.get_button(0),
                "B": self.joystick.get_button(1),
                "LB": self.joystick.get_button(4),
                "RB": self.joystick.get_button(5),
                "LT": int((round(self.joystick.get_axis(4)) + 1) / 2),
                "RT": int((round(self.joystick.get_axis(5)) + 1) / 2),
            }
        return self.state

    def get_controller_state(self):
        return self.state


class ControllerRecorder:

    def __init__(self, controller_reader):
        self.controller_reader = controller_reader
        self.recorded_inputs = []
        self.recording = False

    def start_recording(self):
        self.recording = True
        self.recorded_inputs = []
        self.recording_thread = threading.Thread(target=self.record_input)
        self.recording_thread.start()

    def stop_recording(self):
        self.recording = False

    def get_recorded_inputs(self):
        return self.recorded_inputs

    def record_input(self):
        while self.recording:
            self.recorded_inputs.append(self.controller_reader.get_controller_state())
            time.sleep(1.0 / 60.0)

    def save_recorded_inputs(self, filename):
        with open(filename, "w") as f:
            f.write(str(self.recorded_inputs))

    def load_recorded_inputs(self, filename):
        with open(filename, "r") as f:
            self.recorded_inputs = eval(f.read())
