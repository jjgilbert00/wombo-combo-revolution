import os

from controller import ControllerReader
os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
import pygame
import sys
from pygame.locals import *
import ctypes

pygame.init()

FPS = pygame.time.Clock()
FPS.tick(60)

WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
TRANSPARENT = (255,0,255, 0)
DISPLAYSURF = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA, 32) # (0,0) is top left
DISPLAYSURF.convert_alpha()
# DISPLAYSURF.set_colorkey(TRANSPARENT)
DISPLAYSURF.fill(TRANSPARENT)
pygame.display.set_caption('Wombo Combo Revolution')

# Set the window transparency using SDL2
# hwnd = pygame.display.get_wm_info()["window"]
# ctypes.windll.user32.SetWindowLongW(hwnd, -20, ctypes.windll.user32.GetWindowLongW(hwnd, -20) | 0x80000)
# ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 255, 0x2)

class Stick(pygame.sprite.Sprite):
    def __init__(self, x: int, y: int):
        super().__init__()
        self.direction_icons = {
            i: pygame.image.load(f"images/{i}.png") for i in range(1, 10)
        }
        self.direction = 5
        self.image = self.direction_icons[self.direction]
        self.rect = self.image.get_rect()
        self.rect.center = (x, y)
    
    def update_direction(self, direction: int):
        self.direction = direction

    def draw(self, surface: pygame.Surface):
        self.image = self.direction_icons[self.direction]
        self.image.set_alpha(128)
        surface.blit(self.image, self.rect)

class Button(pygame.sprite.Sprite):
    def __init__(self, x: int, y: int, icon: str ="images/button_up.png"):
        super().__init__()
        self.image = pygame.image.load(icon)
        self.rect = self.image.get_rect()
        self.rect.center = (x, y)
        self.pressed = False
    
    def set_pressed(self, pressed: bool):
        self.pressed = pressed

    def draw(self, surface: pygame.Surface):
        if self.pressed:
            self.image.set_alpha(255)
        else:
            self.image.set_alpha(128)
        surface.blit(self.image, self.rect)

btn_left = WINDOW_WIDTH * 4 // 10
btn_offset = 140

# Buttons
BUTTON_SPRITES = {
    "direction": Stick((WINDOW_WIDTH // 10), WINDOW_HEIGHT // 2),   
    "X": Button(btn_left + 1 * btn_offset, btn_offset),
    "Y": Button(btn_left + 3 * btn_offset, btn_offset ),
    "A": Button(btn_left + 0 * btn_offset, 2 * btn_offset),
    "B": Button(btn_left + 2 * btn_offset, 2 * btn_offset),
    "LB": Button(btn_left + 7 * btn_offset, btn_offset),
    "RB": Button(btn_left + 5 * btn_offset, btn_offset),
    "LT": Button(btn_left + 6 * btn_offset, 2 * btn_offset),
    "RT": Button(btn_left + 4 * btn_offset, 2 * btn_offset),
}


# Initialize game controller reader
pygame.joystick.init()
controller_reader = None
if pygame.joystick.get_count() > 0:
    controller_reader = ControllerReader(
        pygame.joystick.Joystick(0)
    )


# The Event loop
while True:
    for event in pygame.event.get():
        if event.type == QUIT:
            pygame.quit()
            sys.exit() 

    
    controller_reader.update_state({})
    controller_state = controller_reader.get_controller_state()
    for button in controller_state:
        if button == "direction":
            BUTTON_SPRITES[button].update_direction(controller_state[button])
        else:
            BUTTON_SPRITES[button].set_pressed(bool(controller_state[button]))
    DISPLAYSURF.fill(TRANSPARENT)
    for button in BUTTON_SPRITES:
        BUTTON_SPRITES[button].draw(DISPLAYSURF)
        

    pygame.display.update()
    FPS.tick(60)
    