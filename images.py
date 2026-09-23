import os

# Resolve against this file so the app works no matter which directory it's launched from.
IMAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")

IMAGE_SOURCE_DIRECTION = {
    i: os.path.join(IMAGE_DIR, f"{i}.png") for i in range(1, 10)
}
IMAGE_SOURCE_BUTTON_DOWN = os.path.join(IMAGE_DIR, "button_down.png")
IMAGE_SOURCE_BUTTON_UP = os.path.join(IMAGE_DIR, "button_up.png")


'''
This function returns the path to the parameterized standard controller button icon.
'''
def get_standard_button_icon(controller_type: str, icon_style: str, button_name: str):
    return os.path.join(
        IMAGE_DIR, controller_type, icon_style,
        f"T_X_{button_name}{'_Color' if button_name in ['A','B','X','Y'] else ''}_{icon_style}.png",
    )
