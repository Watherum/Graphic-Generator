"""
Script to set globals needed for create_thumbnail
Also populated player and character databases
"""
import io
import os


def readCharDatabase(filename, deliminator=','):
    """
    Open and read player database from a file.
    By default, it is expected to be a CSV format
    Line: Player,character,alt,character,alt,character,alt,character,alt, ...
    Populate the Player Database dictionary for use
    :param filename:
    :param deliminator:
    :return:
    """
    # Open File
    file = io.open(filename, "r", encoding='utf8')
    file_text = file.readlines()
    # Filter through lines that matter:
    char_database = {}
    for line in file_text:
        # check for format
        if line.startswith('#'):
            continue  # comment line
        # {Char from names},{Char in filename}
        line = line.split(deliminator)
        if len(line) < 2:
            continue
        # Confirm there are two columns
        if len(line) > 2:
            print("Warning: Bad format in character database", line)
            continue
        # grab character name
        char_key = line.pop(0).strip()
        char_value = line.pop(0).strip()
        # Add to character database dictionary (to uppercase)
        char_database[char_key.upper()] = char_value
    # end loop
    return char_database


def readPlayerDatabase(filename, deliminator=',', char_database=None):
    """
    Open and read player database from a file.
    By default, it is expected to be a CSV format
    Requires character database to properly look up characters
    Line: Player,character,alt,character,alt,character,alt,character,alt, ...
    Populate the Player Database dictionary for use
    :param filename:
    :param deliminator:
    :param char_database:
    :return:
    """
    # Open File
    if char_database is None:
        char_database = dict()
    file = io.open(filename, "r", encoding='utf8')
    file_text = file.readlines()
    # Filter through lines that matter:
    play_database = {}
    for line in file_text:
        # check for format
        if line.startswith('#'):
            continue  # comment line
        # {player},{Char_1},{Alt_1},{Char_2},{Alt_2},{Char_3},{Alt_3}, ...
        line = line.split(deliminator)
        # check if at least one char alt combination exists
        if len(line) < 3:
            continue
        # check for odd count (requesting char & alt combinations)
        if len(line) % 2 == 0:
            print("Warning: Bad format in player database", line)
            continue
        # grab player name
        player_name = line.pop(0)
        # loop through character & alts
        char_alt_list = []
        for i in range(0, len(line), 2):
            j = i + 1
            a_char = line[i].strip()
            a_alt = line[j].strip()
            # skip if blank
            if a_char == '' and a_alt == '':
                continue
            # check character mapping (to uppercase)
            if a_char.upper() in char_database.keys():
                a_char = char_database[a_char.upper()]
            # format "{character} ({alt})"
            a_char_alt = '{char} ({alt})'.format(char=a_char, alt=a_alt)
            # add char alt combo to list
            char_alt_list.append(a_char_alt)
        # Add to player database dictionary (to uppercase)
        play_database[player_name.upper()] = char_alt_list
    # end loop
    return play_database


def set_default_properties(event_info=None):
    """
    Function to set default properties for globals needed for create_thumbnail.py
    :return:
    """
    # # Set All property values to a default
    # Dictionary for global properties
    properties = dict()
    # Character renders folder location
    properties['char_renders'] = os.path.join("Resources", "Character_Renders")
    properties['render_type'] = "Body render"
    properties['render_type2'] = None
    properties['render_type3'] = None
    # Event name
    properties['event_name'] = event_info
    # Event shorthand name for what text is on the graphic
    properties['event_short_name'] = event_info
    # Event match file information location
    if event_info is None:
        properties['event_file'] = os.path.join('Vod_Names', 'Sample test names.txt')
    else:
        # Expecting to find file "{event_name} names.txt"
        properties['event_file'] = os.path.join('Vod_Names', '{s} names.txt'.format(s=event_info))
    # Background and Foreground overlay locations
    properties['background_file'] = os.path.join("Resources", 'Overlays', 'Background Sample.png')
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground Sample.png')
    # Output save location
    properties['save_location'] = os.path.join('Youtube_Thumbnails')
    # Canvas variables for character window with respect to whole canvas
    properties['char_glow_bool'] = False
    properties['char_window'] = (0.5, 1)  # canvas for characters
    properties['char_border'] = (0.00, 0.00)  # border for characters
    properties['char_offset1'] = (0, 0.00)  # offset for left player window placement on canvas
    properties['char_offset2'] = (0.5, 0.00)  # offset for right player window placement on canvas
    # Scaler Variables for characters in window
    properties['resize_1'] = 1.58  # resize for character for multiple renders on image
    properties['resize_2'] = 1.00
    properties['resize_3'] = 1.00
    # Center-point shift for canvas for characters
    properties['center_shift_1'] = (-0.00, +0.10)  # Universal character shift
    properties['center_shift_2_1'] = (-0.00, +0.00)  # Two character shift
    properties['center_shift_2_2'] = (-0.00, +0.00)
    properties['center_shift_3_1'] = (-0.00, +0.00)  # Three character shift
    properties['center_shift_3_2'] = (-0.00, +0.00)
    properties['center_shift_3_3'] = (-0.00, +0.00)
    # Center-point for text on canvas with respect to whole canvas
    properties['text_player1'] = (0.25, 0.076)
    properties['text_player2'] = (0.75, 0.076)
    properties['text_event'] = (0.25, 0.924)
    properties['text_round'] = (0.75, 0.924)
    properties['text_angle'] = 2  # degree of rotation counter-clockwise
    properties['event_round_single_text'] = False  # Flag to determine if the event and round text is combined
    properties['event_round_text_split'] = ' '  # Text for between event and round when a single element
    # Font settings
    properties['font_location'] = os.path.join("Resources", "Fonts", "tt2004m.ttf")
    properties['font_player1_size'] = 45
    properties['font_player2_size'] = 45
    properties['font_event_size'] = 45
    properties['font_round_size'] = 45
    properties['font_color1'] = '#F5F5F5'  # (245, 245, 245)
    properties['font_color2'] = '#F5F5F5'  # (245, 245, 245)
    properties['font_color3'] = '#F5F5F5'  # (245, 245, 245)
    properties['font_color4'] = '#F5F5F5'  # (245, 245, 245)
    # Border Filter settings
    properties['font_glow_bool'] = False  # Flag to apply glow to font
    properties['font_glow_color'] = '#050505'  # (5, 5, 5)
    properties['font_glow_px'] = 3  # Pixel count for the blur in all directions
    properties['font_glow_itr'] = 25  # Iterations on applying filter
    properties['font_glow_offset'] = (0, 3)  # Offset to apply the filtered effect
    # Character Pixelation filter to characters
    properties['pixelate_filter_bool'] = False  # Flag to pixelate the characters
    properties['pixelate_filter_size'] = 16  # size of pixel squares
    # Useful flags
    properties['show_first_image'] = True  # Flag for showing one sample image when generating
    properties['one_char_flag'] = True  # Flag to determine if there is only one character on the overlay or multiple

    # return properties
    return properties


def setGlobalsQuarantainment(weekly_event):
    """
    Set necessary globals for Quarantainment event {number} for create_thumbnail.py
    properties dictionary is fed in, modified, then returned
    :param weekly_event:
    :return:
    """
    # Load in default
    properties = set_default_properties(weekly_event)

    # Character renders folder location
    properties['render_type'] = "Full render"
    # Background and Foreground overlay locations
    properties['background_file'] = os.path.join("Resources", 'Overlays', 'Background_Q.png')
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_Q.png')
    # Canvas flag
    properties['char_glow_bool'] = True
    # Center-point shift for canvas for characters
    properties['center_shift_1'] = (-0.04, +0.01)
    properties['center_shift_2_1'] = (-0.20, +0.11)  # Two character shift
    properties['center_shift_2_2'] = (+0.20, -0.11)
    properties['center_shift_3_1'] = (-0.15, +0.148)  # Three character shift
    properties['center_shift_3_2'] = (+0.25, -0.037)
    properties['center_shift_3_3'] = (-0.20, -0.148)
    properties['char_border'] = (0.00, 0.26)  # border for characters
    properties['resize'] = 1.0
    properties['resize_1'] = 0.85  # resize for character for multiple renders on image
    properties['resize_2'] = 0.75
    properties['resize_3'] = 0.60
    # Single character flag on overlay
    properties['one_char_flag'] = False
    # Return with modifications
    return properties


def setGlobalsSxT(weekly_event):
    """
    Set necessary globals for Students x Treehouse event {number} for create_thumbnail.py
    properties dictionary is fed in, modified, then returned
    :param weekly_event:
    :return:
    """
    # Set to Quaratainment settings and then adjust
    properties = setGlobalsQuarantainment(weekly_event)

    # Foreground overlay locations
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_SxT.png')
    # font size change
    properties['font_event_size'] = 44
    properties['font_round_size'] = 44
    # Return with modifications
    return properties


def setGlobalsFro(weekly_event):
    """
    Set all globals for Fro Friday event {number} for create_thumbnail.py
    properties dictionary is fed in, modified, then returned
    :param weekly_event:
    :return:
    """
    # Load in default
    properties = set_default_properties(weekly_event)

    # Character renders folder location
    properties['render_type'] = "Full render"
    # Background and Foreground overlay locations
    #properties['background_file'] = os.path.join("Resources", 'Overlays', 'Background_Fro.png')
    properties['background_file'] = os.path.join("Resources", 'Overlays', 'Background_Fro2.png')
    #properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_Fro.png')
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_Fro2.png')
    # Single character flag on overlay
    properties['one_char_flag'] = True
    # Scaler Variables for characters in window
    properties['resize_1'] = 1.00
    # Center-point shift for canvas for characters
    properties['center_shift_1'] = (-0.00, +0.00)  # Universal character shift
    properties['char_border'] = (0.00, 0.26)  # border for characters
    # Center-point for text on canvas with respect to whole canvas
    properties['text_player1'] = (0.23, 0.75)  # (0.20, 0.75)
    properties['text_player2'] = (0.77, 0.75)  # (0.80, 0.75)
    properties['text_event'] = (0.50, 0.075)
    properties['text_round'] = (0.50, 0.075)
    properties['text_angle'] = 0  # degree of rotation counter-clockwise
    # Font settings
    # properties['font_location'] = os.path.join("Resources", "Fonts", "LostLeonestReguler-MVVMn.otf")
    properties['font_location'] = os.path.join("Resources", "Fonts", "Molot.otf")
    properties['font_player1_size'] = 65  #42
    properties['font_player2_size'] = 65  #42
    properties['font_event_size'] = 45  #37
    properties['font_round_size'] = 45  #37
    properties['font_glow_bool'] = True
    properties['font_glow_color'] = '#101010'  # '#641fbf'  # (100, 31, 191)
    properties['font_glow_px'] = 2  # Pixel count for the blur in all directions
    properties['font_glow_itr'] = 25  # Iterations on applying filter
    properties['font_glow_offset'] = (0, 0)  # Offset to apply the filtered effect
    # Combined event and round text
    properties['event_round_single_text'] = True
    properties['event_round_text_split'] = ' - '
    # Return with modifications
    return properties


def setGlobalsAWG(weekly_event):
    """
    Set all globals for AWG event {number} for create_thumbnail.py
    properties dictionary is fed in, modified, then returned
    :param weekly_event:
    :return:
    """
    # Load in default
    properties = set_default_properties(weekly_event)

    # Character renders folder location
    properties['render_type'] = "Full render"
    # Background and Foreground overlay locations
    properties['background_file'] = os.path.join("Resources", 'Overlays', 'Background_AWG.png')
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_AWG_spring.png')
    # Character border settings
    properties['char_border'] = (0.00, 0.35)  # border for characters
    properties['char_offset1'] = (0, -0.00)  # offset for left player window placement on canvas
    properties['char_offset2'] = (0.5, -0.00)  # offset for right player window placement on canvas
    # Single character flag on overlay
    properties['one_char_flag'] = True
    # Scaler Variables for characters in window
    properties['resize_1'] = 1.00
    # Center-point shift for canvas for characters
    properties['center_shift_1'] = (+0.03, -0.03)  # Universal character shift
    # Center-point for text on canvas with respect to whole canvas
    properties['text_player1'] = (0.25, 0.70)
    properties['text_player2'] = (0.70, 0.70)
    properties['text_event'] = (0.50, 0.10)
    properties['text_round'] = (0.50, 0.10)
    properties['text_angle'] = 0  # degree of rotation counter-clockwise
    # Font settings
    properties['font_location'] = os.path.join("Resources", "Fonts", "ConnectionIi-2wj8.otf")
    properties['font_player1_size'] = 42
    properties['font_player2_size'] = 42
    properties['font_event_size'] = 42
    properties['font_round_size'] = 42
    properties['font_glow_bool'] = True
    properties['font_filter_px'] = 2  # Pixel count for the blur in all directions
    properties['font_filter_itr'] = 15  # Iterations on applying filter
    properties['font_filter_offset'] = (0, 1)  # Offset to apply the filtered effect
    # Character Pixelation filter to characters
    properties['pixelate_filter_bool'] = True  # Flag to pixelate the characters
    properties['pixelate_filter_size'] = 280  # size of pixel squares
    # Combined event and round text
    properties['event_round_single_text'] = True
    properties['event_round_text_split'] = ' - '
    # Return with modifications
    return properties


def setGlobalsC2C(weekly_event):
    """
    Set necessary globals for Students x Treehouse event {number} for create_thumbnail.py
    properties dictionary is fed in, modified, then returned
    :param number:
    :return:
    """
    # Set to Quaratainment settings and then adjust
    properties = setGlobalsQuarantainment(weekly_event)

    # Background and Foreground overlay locations
    properties['background_file'] = os.path.join("Resources", 'Overlays', 'Background_C2C.png')
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_C2C.png')
    # Single character flag on overlay
    properties['one_char_flag'] = True
    properties['resize_1'] = 1.0
    # Return with modifications
    return properties


def setGlobalsCatman(weekly_event):
    """
    Set necessary globals for Catman event {number} for create_thumbnail.py
    properties dictionary is fed in, modified, then returned
    :param weekly_event:
    :return:
    """
    # Set to Quaratainment settings and then adjust
    properties = setGlobalsQuarantainment(weekly_event)

    # Foreground overlay locations
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_Catman.png')
    # Return with modifications
    return properties


def setGlobalsIzAw(weekly_event):
    """
    Set necessary globals for IzAw Sub event {number} for create_thumbnail.py
    properties dictionary is fed in, modified, then returned
    :param weekly_event:
    :return:
    """
    # Set to Quaratainment settings and then adjust
    properties = setGlobalsQuarantainment(weekly_event)

    # Foreground overlay locations
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_IzAwSub.png')
    # Return with modifications
    return properties


def setGlobalsJustTechIt(weekly_event):
    """
    Set necessary globals for Catman event {number} for create_thumbnail.py
    properties dictionary is fed in, modified, then returned
    :param weekly_event:
    :return:
    """
    # Set to Quaratainment settings and then adjust
    properties = set_default_properties(weekly_event)

    # Event shorthand name for what text is on the graphic
    properties['event_short_name'] = properties['event_name'].replace("AWG", "")+"!"  # Just Tech It #!
    # Character renders folder location
    properties['render_type'] = "Full render"
    # Background and Foreground overlay locations
    properties['background_file'] = os.path.join("Resources", 'Overlays', 'Background_JustTechIt.png')
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_JustTechIt.png')
    # Center-point shift for canvas for characters
    properties['center_shift_1'] = (-0.00, +0.05)
    # Single character flag on overlay
    properties['one_char_flag'] = True
    properties['resize_1'] = 0.92
    # Canvas flag
    properties['char_glow_bool'] = False
    # Center-point for text on canvas with respect to whole canvas
    properties['text_player1'] = (0.24, 0.065)  # (0.25, 0.076)
    properties['text_player2'] = (0.76, 0.065)  # (0.75, 0.076)
    properties['text_event'] = (0.795, 0.919)  # (0.25, 0.924)
    properties['text_round'] = (0.205, 0.919)  # (0.75, 0.924)
    properties['text_angle'] = 0  # degree of rotation counter-clockwise
    # Font settings
    properties['font_location'] = os.path.join("Resources", "Fonts", "Teko-Light.ttf")
    properties['font_player1_size'] = 178  #42
    properties['font_player2_size'] = 178  #42
    properties['font_event_size'] = 164  #37
    properties['font_round_size'] = 164  #37
    properties['font_color1'] = '#C90000'  # (201, 0, 0)
    properties['font_color2'] = '#C90000'  # (201, 0, 0)
    properties['font_color3'] = '#C90000'  # (201, 0, 0)
    properties['font_color4'] = '#C90000'  # (201, 0, 0)
    # Return with modifications
    return properties
    
def setGlobalsIFN(weekly_event):
    """
    Set necessary globals for Immortal Fight Night {number} for create_thumbnail.py
    properties dictionary is fed in, modified, then returned
    :param weekly_event:
    :return:
    """
    # Set to Quaratainment settings and then adjust
    properties = set_default_properties(weekly_event)

    # Event shorthand name for what text is on the graphic
    properties['event_short_name'] = properties['event_name']  # Immortal Fight Night #
    # Character renders folder location
    properties['render_type'] = "Full render"
    # Background and Foreground overlay locations 
    properties['background_file'] = os.path.join("Resources", 'Overlays', 'Background_IFN.png')
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_IFN.png')
    # Center-point shift for canvas for characters
    properties['center_shift_1'] = (-0.00, +0.05)
    # Single character flag on overlay
    properties['one_char_flag'] = True
    properties['resize_1'] = 0.92
    # Canvas flag
    properties['char_glow_bool'] = False
    # Center-point for text on canvas with respect to whole canvas
    properties['text_player1'] = (0.24, 0.065)  # (0.25, 0.076)
    properties['text_player2'] = (0.76, 0.065)  # (0.75, 0.076)
    properties['text_event'] = (0.795, 0.919)  # (0.25, 0.924)
    properties['text_round'] = (0.205, 0.919)  # (0.75, 0.924)
    properties['text_angle'] = 0  # degree of rotation counter-clockwise
    # Font settings
    properties['font_location'] = os.path.join("Resources", "Fonts", "Bantayog-Light.otf")
    properties['font_player1_size'] = 90  #42
    properties['font_player2_size'] = 90  #42
    properties['font_event_size'] = 65  #37
    properties['font_round_size'] = 95  #37
    properties['font_color1'] = '#FCBA1C'  # (201, 0, 0)
    properties['font_color2'] = '#FCBA1C'  # (201, 0, 0)
    properties['font_color3'] = '#FCBA1C'  # (201, 0, 0)
    properties['font_color4'] = '#FCBA1C'  # (201, 0, 0)
    # Return with modifications
    return properties

def setGlobalsCRClash(weekly_event):
    """
    Set necessary globals for CR Clash {number} for create_thumbnail.py
    properties dictionary is fed in, modified, then returned
    :param weekly_event:
    :return:
    """
    # Set to Quaratainment settings and then adjust
    properties = set_default_properties(weekly_event)

    # Event shorthand name for what text is on the graphic
    properties['event_short_name'] = properties['event_name']  # Immortal Fight Night #
    # Character renders folder location
    properties['render_type'] = "Full render"
    # Background and Foreground overlay locations
    properties['background_file'] = os.path.join("Resources", 'Overlays', 'Background_CRClash.png')
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_CRClash.png')
    # Center-point shift for canvas for characters
    properties['center_shift_1'] = (-0.00, +0.05)
    # Single character flag on overlay
    properties['one_char_flag'] = True
    properties['resize_1'] = 0.92
    # Canvas flag
    properties['char_glow_bool'] = False
    # Center-point for text on canvas with respect to whole canvas
    properties['text_player1'] = (0.24, 0.065)  # (0.25, 0.076)
    properties['text_player2'] = (0.76, 0.065)  # (0.75, 0.076)
    properties['text_event'] = (0.795, 0.919)  # (0.25, 0.924)
    properties['text_round'] = (0.205, 0.919)  # (0.75, 0.924)
    properties['text_angle'] = 0  # degree of rotation counter-clockwise
    # Font settings
    properties['font_location'] = os.path.join("Resources", "Fonts", "Bantayog-Light.otf")
    properties['font_player1_size'] = 90  #42
    properties['font_player2_size'] = 90  #42
    properties['font_event_size'] = 80  #37 #100 for normal CR Clash Weekly
    properties['font_round_size'] = 95  #37 
    properties['font_color1'] = '#FFFFFF'  # (201, 0, 0)
    properties['font_color2'] = '#FFFFFF'  # (201, 0, 0)
    properties['font_color3'] = '#FFFFFF'  # (201, 0, 0)
    properties['font_color4'] = '#FFFFFF'  # (201, 0, 0)
    # Return with modifications
    return properties
    
def setGlobalsCRArcadian(weekly_event):
    """
    Set necessary globals for CR Clash {number} for create_thumbnail.py
    properties dictionary is fed in, modified, then returned
    :param weekly_event:
    :return:
    """
    # Set to Quaratainment settings and then adjust
    properties = set_default_properties(weekly_event)

    # Event shorthand name for what text is on the graphic
    properties['event_short_name'] = properties['event_name']  # Immortal Fight Night #
    # Character renders folder location
    properties['render_type'] = "Full render"
    # Background and Foreground overlay locations
    properties['background_file'] = os.path.join("Resources", 'Overlays', 'Background_CRClash.png')
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_CRArcadian.png')
    # Center-point shift for canvas for characters
    properties['center_shift_1'] = (-0.00, +0.05)
    # Single character flag on overlay
    properties['one_char_flag'] = True
    properties['resize_1'] = 0.92
    # Canvas flag
    properties['char_glow_bool'] = False
    # Center-point for text on canvas with respect to whole canvas
    properties['text_player1'] = (0.24, 0.065)  # (0.25, 0.076)
    properties['text_player2'] = (0.76, 0.065)  # (0.75, 0.076)
    properties['text_event'] = (0.795, 0.919)  # (0.25, 0.924)
    properties['text_round'] = (0.205, 0.919)  # (0.75, 0.924)
    properties['text_angle'] = 0  # degree of rotation counter-clockwise
    # Font settings
    properties['font_location'] = os.path.join("Resources", "Fonts", "Bantayog-Light.otf")
    properties['font_player1_size'] = 90  #42
    properties['font_player2_size'] = 90  #42
    properties['font_event_size'] = 100  #37
    properties['font_round_size'] = 95  #37
    properties['font_color1'] = '#FFFFFF'  # (201, 0, 0)
    properties['font_color2'] = '#FFFFFF'  # (201, 0, 0)
    properties['font_color3'] = '#FFFFFF'  # (201, 0, 0)
    properties['font_color4'] = '#FFFFFF'  # (201, 0, 0)
    # Return with modifications
    return properties
    
def setGlobalsClipIt(weekly_event):
    """
    Set necessary globals for Students x Treehouse event {number} for create_thumbnail.py
    properties dictionary is fed in, modified, then returned
    :param number:
    :return:
    """
    # Set to Quaratainment settings and then adjust
    properties = setGlobalsQuarantainment(weekly_event)

    # Single character flag on overlay
    properties['one_char_flag'] = True
    properties['resize_1'] = 0.92

    # Background and Foreground overlay locations
    properties['background_file'] = os.path.join("Resources", 'Overlays', 'Background_ClipIt.png')
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_ClipIt.png')
    
    # Center-point for text on canvas with respect to whole canvas
    properties['text_angle'] = 0  # degree of rotation counter-clockwise
    # Font settings
    properties['font_location'] = os.path.join("Resources", "Fonts", "Bantayog-Light.otf")
    properties['font_player1_size'] = 90  #67 Doubles  #90 HDR #100 Archive
    properties['font_player2_size'] = 90  #67 Doubles  #90 HDR #100 Archive
    properties['font_event_size'] = 120   #120 Doubles #120 HDR #120 Archive
    properties['font_round_size'] = 95    #65 Doubles  #70 HDR  #95  Archive
    properties['font_color1'] = '#FFFFFF'  # (201, 0, 0)
    properties['font_color2'] = '#FFFFFF'  # (201, 0, 0)
    properties['font_color3'] = '#FFFFFF'  # (201, 0, 0)
    properties['font_color4'] = '#FFFFFF'  # (201, 0, 0)
    # Return with modifications
    return properties


def setGlobalsQuarantainment_Top8():
    """
    Set necessary globals for Quarantainment Top 8 Graphic for create_top8_graphic.py
    properties dictionary is fed in, modified, then returned
    :return:
    """
    # Load in default
    properties = set_default_properties()
    # Character renders folder location
    properties['render_type'] = "Body render"
    properties['render_type2'] = "Diamond render"
    # Event match file information location
    properties['top8_info'] = os.path.join('Vod_Names', '_top8_test.txt')
    # Background and Foreground overlay locations
    properties['background_file'] = os.path.join("Resources", 'Top8_Graphics', 'Jetstream_Top8_Background.png')
    properties['foreground_file'] = os.path.join("Resources", 'Top8_Graphics', 'Jetstream_Top8_Foreground.png')
    # Canvas flag
    properties['char_glow_bool'] = True
    # Center-point shift for canvas for characters
    properties['resize'] = 0.517578125
    properties['resize_1'] = 0.517578125
    properties['resize_2'] = 1.00
    # Placements for windows
    properties['char_window'] = (0.33, 0.246)  # canvas for characters
    properties['char_offset1'] = (0.0, 0.005)  # Offset for 1
    properties['char_offset2'] = (0.0, 0.255)  # Offset for 2
    properties['char_offset3'] = (0.0, 0.505)  # Offset for 3
    properties['char_offset4'] = (0.0, 0.755)  # Offset for 4
    properties['char_offset5'] = (0.336, 0.005)  # Offset for 5
    properties['char_offset6'] = (0.336, 0.255)  # Offset for 6
    properties['char_offset7'] = (0.336, 0.505)  # Offset for 7
    properties['char_offset8'] = (0.336, 0.755)  # Offset for 8
    # Center-point shift for canvas for characters
    properties['center_shift_1'] = (+0.30, +0.00)  # Universal character shift
    properties['center_shift_2_1'] = (+0.00, +0.00)  # Two character shift
    properties['center_shift_2_2'] = (-0.38, +0.155)
    properties['center_shift_3_1'] = (-0.00, +0.00)  # Three character shift
    properties['center_shift_3_2'] = (+0.25, -0.037)
    properties['center_shift_3_3'] = (-0.20, -0.148)
    # Player Font settings
    properties['text_angle'] = 0
    properties['font_player_location'] = os.path.join("Resources", "Fonts", "BungeeInline-Regular.ttf")
    properties['font_player_color'] = '#F5F5F5'  # (245, 245, 245)
    properties['font_player_align'] = 'left'
    properties['font_player_size'] = 64
    properties['font_player1_offset'] = (0.015, 0.04)  # Offset for 1
    properties['font_player2_offset'] = (0.015, 0.29)  # Offset for 2
    properties['font_player3_offset'] = (0.015, 0.54)  # Offset for 3
    properties['font_player4_offset'] = (0.015, 0.79)  # Offset for 4
    properties['font_player5_offset'] = (0.3525, 0.04)  # Offset for 5
    properties['font_player6_offset'] = (0.3525, 0.29)  # Offset for 6
    properties['font_player7_offset'] = (0.3525, 0.54)  # Offset for 7
    properties['font_player8_offset'] = (0.3525, 0.79)  # Offset for 8
    # Twitter Font settings
    properties['font_twitter_location'] = os.path.join("Resources", "Fonts", "arial.ttf")
    properties['font_twitter_color'] = '#FFFFFF'  # (255, 255, 255)
    properties['font_twitter_back_color'] = '#00000090'  # (0, 0, 0, 25)
    properties['font_twitter_align'] = 'right'
    properties['font_twitter_size'] = 32
    properties['font_twitter1_offset'] = (0.32, 0.23)  # Offset for 1
    properties['font_twitter2_offset'] = (0.32, 0.48)  # Offset for 2
    properties['font_twitter3_offset'] = (0.32, 0.73)  # Offset for 3
    properties['font_twitter4_offset'] = (0.32, 0.98)  # Offset for 4
    properties['font_twitter5_offset'] = (0.6575, 0.23)  # Offset for 5
    properties['font_twitter6_offset'] = (0.6575, 0.48)  # Offset for 6
    properties['font_twitter7_offset'] = (0.6575, 0.73)  # Offset for 7
    properties['font_twitter8_offset'] = (0.6575, 0.98)  # Offset for 8
    # Event Info settings
    properties['font_event_location'] = os.path.join("Resources", "Fonts", "BungeeInline-Regular.ttf")
    properties['font_event_name_offset'] = (0.834, 0.285)
    properties['font_event_name_color'] = '#F5F5F5'  # (5, 5, 5)
    properties['font_event_name_size'] = 43
    properties['font_event_name_align'] = 'center'
    properties['font_event_date_offset'] = (0.90, 0.40)
    properties['font_event_date_color'] = '#050505'  # (5, 5, 5)
    properties['font_event_date_size'] = 40
    properties['font_event_date_align'] = 'center'
    properties['font_event_entrants_offset'] = (0.90, 0.455)
    properties['font_event_entrants_color'] = '#050505'  # (5, 5, 5)
    properties['font_event_entrants_size'] = 40
    properties['font_event_entrants_align'] = 'center'
    # Media Info settings
    properties['font_media_location'] = os.path.join("Resources", "Fonts", "arial.ttf")
    properties['font_media_color'] = '#050505'  # (5, 5, 5)
    properties['font_media_align'] = 'center'
    properties['font_media_size'] = 32
    properties['font_media_twitter_offset'] = (0.855, 0.79)
    properties['font_media_youtube_offset'] = (0.855, 0.855)
    properties['font_media_twitch_offset'] = (0.855, 0.915)
    properties['font_media_bracket_link_offset'] = (0.85, 0.975)
    # Set to Watch Info settings
    properties['font_stw_location'] = os.path.join("Resources", "Fonts", "BungeeInline-Regular.ttf")
    properties['font_stw_color'] = '#050505'  # (5, 5, 5)
    properties['font_stw_align'] = 'center'
    properties['font_stw_size'] = 40
    properties['font_stw_twolines'] = True
    properties['font_stw_line1_offset'] = (0.8345, 0.645)
    properties['font_stw_line2_offset'] = (0.8345, 0.705)

    # Return with modifications
    return properties


def setGlobalsSxT_Top8():
    """
    Set necessary globals for Students x Treehouse Top 8 Graphic for create_top8_graphic.py
    properties dictionary is fed in, modified, then returned
    :return:
    """
    # Set to Quaratainment settings and then adjust
    properties = setGlobalsQuarantainment_Top8()
    #
    # Event match file information location
    properties['top8_info'] = os.path.join('Vod_Names', '_top8_test.txt')
    # Foreground overlay locations
    properties['foreground_file'] = os.path.join("Resources", 'Overlays', 'Foreground_SxT.png')
    # Return with modifications
    return properties
