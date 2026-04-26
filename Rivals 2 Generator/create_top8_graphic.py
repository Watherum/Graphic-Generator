"""
Script to create Top 8 Graphic  for Smash Ultimate

1. Read in the names file to event information and player placements

2. Have a blank graphic ready to populate the information

3. Have the script read in the character and add them to the graphic

4. Have the script open the graphic and add the information

7. Have the script output the images in a specified File location
"""

import io
import os

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import populate_globals
import create_thumbnail
from helper import *

import sys
import getopt

'''Global Variables used in script'''
# Dictionaries for lookups
_character_database = {}
_player_database = {}
# Dictionary for global properties
_properties = dict()


class GraphicPlacement:
    def __init__(self, _place, _player, _sponsor, _char_list):
        self.p = _place
        self.tw = _sponsor
        self.p1 = _player
        self.c1 = _char_list
        self.c1_renders = []
        self.c1_offset = (0, 0)
        self.c1_scale = None
        self.Images = []


def setGlobalsTop8(weekly, property_settings=None):
    """
    Set all globals based off the type of event. Weekly is the series.
    These globals are set to then create the associated thumbnails
    :param weekly:
    :param property_settings:
    :return:
    """
    # Set globals based off of type of weekly
    if weekly == 'Quarantainment':
        global_properties = populate_globals.setGlobalsQuarantainment_Top8()
    elif weekly == 'Students x Treehouse':
        global_properties = populate_globals.setGlobalsSxT_Top8()
    elif weekly == 'Straight Into The Abyss':
        global_properties = populate_globals.setGlobalsAbyss_Top8()
    elif weekly == 'Immortal Fight Night':
        global_properties = populate_globals.setGlobalsIFN()
    else:
        global_properties = {}
        # global_properties = populate_globals.set_default_properties_Top8()
    # All Top 8 graphics save to Top_8_Results, not Youtube_Thumbnails
    global_properties['save_location'] = os.path.join('Top_8_Results')
    return global_properties


def readGrpahicLines(filename):
    """
    Open file and read it line by line
    return two items
        Dictionary of info - used for populating global information
        List of placements - used for creating individual graphic windows

    :param filename:
    :return:
    """
    # Open File
    file = io.open(filename, "r", encoding='utf8')
    file_text = file.readlines()
    # Filter through lines that matter:
    info_dict = {}
    placement_list = []
    print("--- Reading Top 8 Lines ---")
    for line in file_text:
        # check for format
        # {event_1} {round_1} - {player_1} ({char_1}) Vs {player_2} ({char_2}) - SSBU
        if line.startswith('#'):
            # Comment case
            continue
        # Strip new lines
        line = line.strip('\n')
        # Split line up by tabs
        line = line.split('\t')
        # Placements case - 1:, 2:, ..., 8:
        if len(line[0]) == 2 and line[0][1] == ':' and line[0][0] in '12345678':
            # Create placement from this information
            # place, name, twitter, characters
            a_placement = GraphicPlacement(_place=line[0][0], _player=line[1], _sponsor=line[2], _char_list=line[3:])
            placement_list.append(a_placement)
        else:
            # Info cases
            # bring to lowercase to be easier to search later
            line[0] = line[0].lower()
            # Standard information
            if line[0] == 'event name:' or line[0] == 'event date:' or line[0] == 'event entrants:':
                info_dict[line[0]] = line[1]
            # Media information
            elif line[0] == 'twitter:' or line[0] == 'youtube:' or line[0] == 'twitch:' or line[0] == 'bracket link:':
                info_dict[line[0]] = line[1]
            # Cases with more than one /t in the line
            # Set to watch information
            # elif line[0] == 'set to watch:':
                # "Set to Watch:" : [set, player1, player2]
                # info_dict[line[0]] = [line[1], line[2], line[3]]
    # end loop
    if len(placement_list) == 0 or len(info_dict.keys()) == 0:
        raise NameError("Filename " + filename + " was not properly read in")
    return info_dict, placement_list


def createPlacements(placements_list):
    """
    Take in a list of placements, and add character render file locations.
    Also adds in the offset locations for the placement
    Writes out information to log file if present
    :param placements_list:
    :return:
    """
    # Read each line and grab information
    return_list = []

    # Loop through all matches and find character render file locations
    #  This involves looking at the Character and Player Databases to successfully grab the alts
    # Dictionaries for players and characters not found
    player_not_found = {}
    char_not_found = {}
    for a_placement in placements_list:
        # Add in offset based on placement
        #  All offsets are in _properties['char_offset#'], where # is 1-8
        char_offset = 'char_offset' + a_placement.p
        a_placement.c1_offset = _properties[char_offset]
        # Per-placement scale; falls back to global char_window if not set
        char_scale_key = 'char_scale' + a_placement.p
        a_placement.c1_scale = _properties.get(char_scale_key, _properties['char_window'])
        # Loop through character lists and grab character render
        #  Add them to the new lists
        player_char_files = []
        for a_char in a_placement.c1:
            # Case for handling alts in the char name
            #  {event_1} {round_1} - {player_1} ({char_1}) Vs. {player_2} ({char_2}) - SSBU
            #  where {char_1[2]} = ["a_char a_alt", "a_char2 a_alt2", ...]
            alt_num_in_name = False
            if a_char[-2] == ' ' and a_char[-1] in "12345678":
                alt_num_in_name = True
                alt_num = '(' + a_char[-1] + ')'
                a_char = a_char[:-2]
            else:
                alt_num = '(1)'
            # Search for character in char database
            if a_char.upper() in _character_database.keys():
                a_char = _character_database[a_char.upper()]
            # Create char image file name
            char_file = a_char + ' ' + alt_num
            # Lookup character in player database for alt costume (if it exists) if alt not specified
            if not alt_num_in_name:
                player_name = a_placement.p1
                # Player not found case (to uppercase)
                if player_name.upper() not in _player_database.keys():
                    # add player to not found dictionary
                    if player_name not in player_not_found.keys():
                        player_not_found[player_name] = []
                    if a_char not in player_not_found[player_name]:
                        player_not_found[player_name].append(a_char)
                else:  # Player found, now look for characters
                    # Lookup character (to uppercase)
                    player_chars_lookup = _player_database[player_name.upper()]
                    char_found = False
                    # Search existing characters in player database
                    for p_char in player_chars_lookup:
                        if a_char.upper() in p_char.upper():
                            # Char found, set char file
                            char_file = p_char
                            char_found = True
                            break
                    # Char not found case and character is not random
                    if not char_found and a_char.upper() != 'RANDOM':
                        # add player to not found dictionary (to uppercase)
                        if player_name not in char_not_found.keys():
                            char_not_found[player_name] = []
                        if a_char not in char_not_found[player_name]:
                            char_not_found[player_name].append(a_char)
            # Check if char file exists at render location
            #  Render type must be specified, Render type 2 & 3 need not be
            if _properties['render_type'] is None:
                raise NameError("Error: 'render_type' is set to None")
            for rend_dir in [_properties['render_type'], _properties['render_type2'], _properties['render_type3']]:
                if rend_dir is None:
                    continue
                char_location = os.path.join(_properties['char_renders'], rend_dir, char_file + '.png')
                if not os.path.exists(char_location):
                    raise NameError("Character not found in " + a_placement.p + ": " + rend_dir + "/" + char_file)
            # Add to render files
            player_char_files.append(char_file)
        # end of placement loop

        # Add character renders to match
        a_placement.c1_renders = player_char_files
        # Add match to return list
        return_list.append(a_placement)
    # end of match loop

    # Write output information to log file - player and character not found information
    out_text = ""
    out_text += "** List of players not found **\n"
    for a_player in player_not_found.keys():
        out_text += "{s}".format(s=a_player)
        for a_char in player_not_found[a_player]:
            out_text += "\t{s}\t1".format(s=a_char)
        out_text += "\n"
    out_text += "** List of characters not found for players **\n"
    for a_player in char_not_found.keys():
        out_text += "{s}".format(s=a_player)
        for a_char in char_not_found[a_player]:
            out_text += "\t{s}\t1".format(s=a_char)
        out_text += "\n"
    # Print information to screen or to file
    if char_not_found != {} or player_not_found != {}:
        print(out_text)
    # Return
    return return_list


def pasteInfoOnGraphic(image_in, info_text, info_font, info_type1, info_type2):
    """
    Paste text onto image. Uses info_font, typ1 and type2 to grab correct globals from _properties dict
    type1 and type2  handles for different cases such as generalized of specific font sizes and colors
    :param image_in:
    :param info_text:
    :param info_font:
    :param info_type1:
    :param info_type2:
    :return:
    """
    # Grab font info
    font_event = ImageFont.truetype(info_font, size=_properties['font_{e}_size'.format(e=info_type1)])
    # Event Name
    text_mask = create_rotated_text(_properties['text_angle'], info_text, font_event)
    # determine offset by scaling with the foreground
    text_offset = _properties['font_{e}_offset'.format(e=info_type2)]
    text_offset = (int(image_in.size[0] * text_offset[0]), int(image_in.size[1] * text_offset[1]))
    # create mask
    font_event_color = _properties['font_{e}_color'.format(e=info_type1)]
    e_im = Image.new('RGBA', text_mask.size, color=font_event_color)
    text_offset = calculateOffsetFromCenter(text_offset, text_mask.size)
    # Shift based offsets on alignment
    if _properties['font_{e}_align'.format(e=info_type1)] == 'right':
        # shift by a quarter of mask width to line up right justified
        text_offset = int(text_offset[0] - (text_mask.size[0] / 4)), text_offset[1]
    elif _properties['font_{e}_align'.format(e=info_type1)] == 'center':
        pass
    else:  # default to left
        # shift by a quarter of mask width to line up left justified
        text_offset = int(text_offset[0] + (text_mask.size[0] / 4)), text_offset[1]
    # Paste to Foreground
    image_in.paste(e_im, text_offset, mask=text_mask)
    return image_in


def createGraphic(graphic_info, graphic_placements, background, foreground):
    """
    Create top 8 graphic image with available information.
    Take background, paste placement info, apply foreground, add event info
    :param graphic_info:
    :param graphic_placements:
    :param background:
    :param foreground:
    :return:
    """
    # Loop through the placements and add the images
    print("--- Creating Top 8 Image ---")
    show_first = _properties['show_first_image']
    # # # Create background and foreground images and combine
    # # Background:
    # Grab all the character images to prepare them to add to the background
    # Create a copy of the background
    g_back = background.copy()
    # create_thumbnail function is used here, so must set its global properties
    create_thumbnail._properties = _properties
    # Loop through placements and add each of the top 8 windows
    for a_placement in graphic_placements:
        # Grab all the character images to prepare them to add to the background
        char_list = a_placement.c1_renders
        # Call Function to create the combined character images for a single placement
        char_window = a_placement.c1_scale
        char_canvas = (int(background.size[0] * char_window[0]), int(background.size[1] * char_window[1]))
        c1_image_list = create_thumbnail.createCharacterWindow(char_list, char_canvas, single_bool=False, only_one=True)
        # Only care about the first image from this function
        c1_image = c1_image_list[0]
        # Grab offsets for placing the character windows
        char_offset1 = a_placement.c1_offset
        offset1 = (int(background.size[0] * char_offset1[0]), int(background.size[1] * char_offset1[1]))
        # Add characters to canvas
        if not _properties['char_glow_bool']:
            # Paste character models to transparent canvas
            blank_back = Image.new("RGBA", background.size)
            blank_back.paste(c1_image, offset1, mask=c1_image)
            # Make new composite image of background and new characters
            g_back = Image.alpha_composite(g_back.copy(), blank_back)
        else:  # apply with transparency glow
            # Apply the characters to the image
            g_back.paste(c1_image, offset1, mask=c1_image)
    # end of placements loop

    # # Foreground:
    # Take match information and populate the foreground. Players, Twitter, Event, Date, Set to Watch, Media
    # Apply this foreground to the background
    g_fore = foreground.copy()
    # Apply Player Text information to the desired locations on the foreground
    # Grab Font information
    font_player_color = _properties['font_player_color']
    font_twitter_color = _properties['font_twitter_color']
    font_twitter_back_color = _properties['font_twitter_back_color']
    # Loop through the players and paste the player and twitter information
    #  These are saved in _properties['font_player#_offset'] and _properties['font_twitter#_offset'] where # is 1-8
    for a_placement in graphic_placements:
        # Per-placement font sizes fall back to the global size if no override is set
        player_size = _properties.get('font_player_size' + a_placement.p, _properties['font_player_size'])
        font_player = ImageFont.truetype(_properties['font_player_location'], size=player_size)
        twitter_size = _properties.get('font_twitter_size' + a_placement.p, _properties['font_twitter_size'])
        font_twitter = ImageFont.truetype(_properties['font_twitter_location'], size=twitter_size)
        # # Player text
        p_text = a_placement.p1
        p_mask = create_rotated_text(_properties['text_angle'], p_text, font_player)
        # determine offset by scaling with the foreground
        p_offset = _properties['font_player{s}_offset'.format(s=a_placement.p)]
        p_offset = (int(foreground.size[0] * p_offset[0]), int(foreground.size[1] * p_offset[1]))
        # create mask
        p_im = Image.new('RGBA', p_mask.size, color=font_player_color)
        p_offset = calculateOffsetFromCenter(p_offset, p_mask.size)
        # Shift based offsets on alignment
        if _properties['font_player_align'] == 'right':
            # shift by a quarter of mask width to line up right justified
            p_offset = int(p_offset[0] - (p_mask.size[0] / 2)), p_offset[1]
        elif _properties['font_player_align'] == 'center':
            pass
        else:  # default to left
            # shift by a quarter of mask width to line up left justified
            p_offset = int(p_offset[0] + (p_mask.size[0] / 2)), p_offset[1]
        # Paste to Foreground
        g_fore.paste(p_im, p_offset, mask=p_mask)
        # #Twitter text
        t_text = a_placement.tw
        t_mask = create_rotated_text(_properties['text_angle'], t_text, font_twitter)
        # determine offset by scaling with the foreground
        t_offset = _properties['font_twitter{s}_offset'.format(s=a_placement.p)]
        t_offset = (int(foreground.size[0] * t_offset[0]), int(foreground.size[1] * t_offset[1]))
        # create mask
        t_im = Image.new('RGBA', t_mask.size, color=font_twitter_color)
        t_text_offset = calculateOffsetFromCenter(t_offset, t_mask.size)
        # twitter text background image
        #  pad text by 2 spaces, and grab max height possible from the text
        t_back_im = create_rotated_text_back(_properties['text_angle'], " " + t_text + " ", font_twitter,
                                             font_twitter_back_color)
        t_back_offset = calculateOffsetFromCenter(t_offset, t_back_im.size)
        # Shift based offsets on alignment
        if _properties['font_twitter_align'] == 'right':
            # shift by a half of mask width to line up right justified
            t_back_offset = int(t_back_offset[0] - t_mask.size[0] / 2), t_back_offset[1]
            t_text_offset = int(t_text_offset[0] - t_mask.size[0] / 2), t_text_offset[1]
        elif _properties['font_twitter_align'] == 'center':
            pass  # do nothing
        else:  # default to left
            # shift by a half of mask width to line up Left justified
            t_back_offset = int(t_back_offset[0] + t_mask.size[0] / 2), t_back_offset[1]
            t_text_offset = int(t_text_offset[0] + t_mask.size[0] / 2), t_text_offset[1]
        # Paste onto foreground
        g_fore.paste(t_back_im, t_back_offset, mask=t_back_im)
        g_fore.paste(t_im, t_text_offset, mask=t_mask)
    # end of player twitter loop
    # Apply Additional information
    add_info = graphic_info.keys()
    # Event information
    for e_info in ['event name:', 'event date:', 'event entrants:']:
        if e_info not in add_info:
            continue
        e_text = graphic_info[e_info]
        e_global = e_info.strip(':').replace(' ', '_')
        e_font = _properties['font_event_location']
        # Paste info on foreground
        g_fore = pasteInfoOnGraphic(g_fore, e_text, e_font, e_global, e_global)
    # Media Information
    for m_info in ['twitter:', 'youtube:', 'twitch:', 'bracket link:']:
        if m_info not in add_info:
            continue
        # Grab font info
        m_text = graphic_info[m_info]
        m1_global = 'media'
        m2_global = m1_global + '_' + m_info.strip(':').replace(' ', '_')
        m_font = _properties['font_media_location']
        # Paste info on foreground
        g_fore = pasteInfoOnGraphic(g_fore, m_text, m_font, m1_global, m2_global)
    # Set to Watch
    if 'set to watch:' in add_info:
        # Grab font information
        stw_font = _properties['font_stw_location']
        # Set to watch has structure "set to watch:" : [set, player1, player2]
        stw_list = graphic_info['set to watch:']
        set_match_text = stw_list[0]
        set_player_text = stw_list[1] + ' Vs ' + stw_list[2]
        # Single line case
        if _properties['font_stw_twolines'] is False:
            set_match_text = set_match_text + ' - ' + set_player_text
        stw_global = 'stw'
        # Add line 1
        g_fore = pasteInfoOnGraphic(g_fore, set_match_text, stw_font, stw_global, "stw_line1")
        if _properties['font_stw_twolines'] is True:
            # Add line 2
            g_fore = pasteInfoOnGraphic(g_fore, set_player_text, stw_font, stw_global, "stw_line2")
    # End of information cases

    # All contents are added to Background and Foreground. Merge them
    comb_image = Image.alpha_composite(g_back, g_fore)
    # Show image
    if show_first:
        comb_image.show()
    return comb_image


def saveGraphic(graphic, folder_location, event_name=None):
    """
    Saves graphic image to folder location. If event name is populated, then create a folder with the event name
    :param graphic:
    :param folder_location:
    :param event_name:
    :return:
    """
    # Check if event is being used as folder name
    if event_name is not None:
        folder_location = os.path.join(folder_location, event_name)
        event_name = event_name + '_'
    else:
        event_name = ''
    # Create folder if it does not exist
    if not os.path.exists(folder_location):
        os.makedirs(folder_location)
    graphic.save(os.path.join(folder_location, event_name + 'Top8.png'))
    graphic.close()
    return


def main(argv):
    event = 'Straight Into The Abyss'
    input_file = ''
    try:
        opts, args = getopt.getopt(argv, "he", ["event="])
    except getopt.GetoptError:
        print('create_new_top8_graphic.py -e <event>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('create_new_top8_graphic.py -e <event>')
            sys.exit()
        elif opt in ("-e", "--event"):
            event = arg
    # End of Command Line Arguments

    # 0. Setup information
    # Event
    global _properties
    _properties = setGlobalsTop8(event)
    # Read Player Database and Character Database
    global _character_database
    character_database_location = os.path.join('Resources', 'Character_Database.csv')
    _character_database = populate_globals.readCharDatabase(character_database_location)
    global _player_database
    player_database_location = os.path.join('Resources', 'Player_Database.csv')
    _player_database = populate_globals.readPlayerDatabase(player_database_location, char_database=_character_database)
    # 1. Read in the input file to get event info and player placements
    event_info, event_placements = readGrpahicLines(_properties['top8_info'])
    # Update placements and grab character renders
    event_placements = createPlacements(event_placements)
    # Setup
    # 2. Have a blank graphic ready to populate the information
    back_image = Image.open(_properties['background_file']).convert('RGBA')
    # back_image.show()
    front_image = Image.open(_properties['foreground_file']).convert('RGBA')
    # front_image.show()
    # 3. Have the script read in the character and add them to the graphic
    event_graphic = createGraphic(event_info, event_placements, back_image, front_image)
    # 4. Save the images
    saveGraphic(event_graphic, _properties['save_location'], event_info['event name:'])


if __name__ == "__main__":
    # Get command line inputs
    main(sys.argv[1:])
    print("Done")