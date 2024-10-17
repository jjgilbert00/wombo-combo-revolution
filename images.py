

# images.py

IMAGE_SOURCE_DIRECTION = {
    i: f"./images/{i}.png" for i in range(1, 10)
}
IMAGE_SOURCE_BUTTON_DOWN = "./images/button_down.png"
IMAGE_SOURCE_BUTTON_UP = "./images/button_up.png"


'''
This function returns the path to the parameterized standard controller button icon. 
'''
def get_standard_button_icon(controller_type: str, icon_style: str, button_name: str):
    return f"./images/{controller_type}/{icon_style}/T_X_{button_name}{'_Color' if button_name in ['A','B','X','Y'] else ''}_{icon_style}.png"