"""
Helper scripts used in primary modules

Contains simple functions that are commonly used

"""
from PIL import Image, ImageDraw
from math import sin, cos, radians

def common_start(sa, sb):
    """
    returns the longest common substring from the beginning of sa and sb
    :param sa:
    :param sb:
    :return:
    """

    def _iter():
        for a, b in zip(sa, sb):
            if a == b:
                yield a
            else:
                return
    return ''.join(_iter())


def create_rotated_text(angle, text, font):
    """
    Creates angled text and returns a mask of the text
    :param angle:
    :param text:
    :param font:
    :return:
    """
    # get the size of the text
    x_text, _ = font.getsize(text)
    _, y_text = font.getsize("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz[]@_")
    # want the tallest possible word

    # build a transparency mask large enough to hold the text
    max_dim = 2 * max(x_text, y_text)

    # build a transparency mask large enough to hold the text
    mask_size = (max_dim, max_dim)
    mask = Image.new('L', mask_size, 0)

    # add text to mask at center of box
    draw = ImageDraw.Draw(mask)
    draw.text((max_dim / 2 - x_text / 2, max_dim / 2 - y_text / 2), text, 255, font=font)

    if angle % 90 == 0:
        # rotate by multiple of 90 deg is easier
        rotated_mask = mask.rotate(angle)
    else:
        # rotate an an enlarged mask to minimize jaggies
        bigger_mask = mask.resize((max_dim * 8, max_dim * 8), resample=Image.BICUBIC)
        rotated_mask = bigger_mask.rotate(angle).resize(mask_size, resample=Image.LANCZOS)
    # Trim mask to fit text space
    # determine the length of the space of interest
    x_rotate = abs(int(x_text * cos(radians(angle)) + y_text * sin(radians(angle))))
    y_rotate = abs(int(y_text * cos(radians(angle)) + x_text * sin(radians(angle))))
    x_center, y_center = calculateCenter(rotated_mask.size)
    # crop from center of mask (half of rotated distance)
    box = (x_center - x_rotate/2, y_center - y_rotate/2, x_center + x_rotate/2, y_center + y_rotate/2)
    crop_rotated_mask = rotated_mask.crop(box)
    # return text transparency mask
    return crop_rotated_mask


def create_rotated_text_back(angle, text, font, color):
    """
    Creates background for angled text and returns an image with desired color
    :param angle:
    :param text:
    :param font:
    :param color:
    :return:
    """
    # get the size of the text
    x_text, _ = font.getsize(text)
    _, y_text = font.getsize("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz[]@_")
    # want the tallest possible word

    # Create a new image with the size of the text
    back_image = Image.new('RGBA', (x_text, y_text), color=color)
    back_image = back_image.rotate(angle)
    return back_image

def hex_to_rgb(hex_input):
    """
    converts a single hex input into RGB tuple
    :param hex_input:
    :return:
    """
    hex_input = hex_input.lstrip('#')
    hlen = len(hex_input)
    return tuple(int(hex_input[i:i + hlen // 3], 16) for i in range(0, hlen, hlen // 3))


def calculateCenter(xy_image):
    """
    Function to calculate the center location of a xy size
    Returns an integer value
    :param xy_image:
    :return:
    """
    x_image, y_image = xy_image
    return int(x_image / 2), int(y_image / 2)


def calculateOffsetFromCenter(xy_center, xy_image):
    """
    Function to calculate the offset needed to fit image at the center of a window
    :param xy_center:
    :param xy_image:
    :return:
    """
    x_center, y_center = xy_center
    x_image, y_image = xy_image
    x_off = int(x_center - (x_image / 2))
    y_off = int(y_center - (y_image / 2))
    return x_off, y_off


def fitToWindowResize(char_image, x_limit, y_limit):
    """
    Function to resize a character image to maximize its fit to the window
    This resizes and keeps the aspect ration such that the width or the height is equal to the limit
    :param char_image:
    :param x_limit:
    :param y_limit:
    :return:
    """
    x_char, y_char = char_image.size
    # Identify ratio for scaling
    xy_ratio = x_limit / y_limit
    if y_char * xy_ratio > x_char:
        # character image is taller than it is wide
        scaler_ratio = y_limit / y_char
        y_resize = y_limit  # = ratio*input_y
        x_resize = scaler_ratio * x_char
    else:
        # character image is wider than it is tall
        scaler_ratio = x_limit / x_char
        x_resize = x_limit  # = ratio*input_x
        y_resize = scaler_ratio * y_char
    # Resize the character image. No need to worry about offsets
    xy_resize = (int(x_resize), int(y_resize))
    char_image = char_image.resize(xy_resize)
    return char_image


def resizeCharacterList(char_list, resize_list):
    """
    Function to resize the characters in char list
    Returns a list of images with each resize as an element in the list.
    The order is the same as the char_list
    Resize list contains the information on how to resize
    Ex. char_list = [A, B, C]   resize_list = [(0.5,0.5), (0.25,0.25)]
        return_list = [ [0.5A, 0.25A], [0.5B, 0.25B], [0.5C, 0.25C] ]
    This function will only go up to a maximum 3 character resizes
    :param char_list:
    :param resize_list:
    :return:
    """
    return_list = []
    # Loop through the characters
    for a_char in char_list:
        return_list.append([])
        # Resize are global variables that scale the renders
        for a_resize in resize_list:
            x_resize, y_resize = a_char.size
            x_resize = int(x_resize * a_resize)
            y_resize = int(y_resize * a_resize)
            new_char = a_char.resize((x_resize, y_resize))
            return_list[-1].append(new_char)
    # end of loop
    return return_list
