"""
Script to take in renders from folders and organize them into a cleaner format
https://www.spriters-resource.com/nintendo_switch/supersmashbrosultimate/
Folder structure by default:
    Nintendo Switch - Super Smash Bros Ultimate - {Character}/Super Smash Bros Ultimate/Fighter Portraits/{Character}

Desire is to grab the portraits for each character organize them in the following way:
    Renders
        Square render
            Character (1)
            ...
            Character (8)
        Body render
        Wide render
        Diamond render
        Full render (incomplete)

"""
import os
import shutil

_character_list = [
    "Banjo & Kazooie",
    "Bayonetta",
    "Bowser",
    "Bowser Jr (Koopalings)",
    "Byleth",
    "Captain Falcon",
    "Chrom",
    "Cloud",
    "Corrin",
    "Daisy",
    "Dark Pit",
    "Dark Samus",
    "Diddy Kong",
    "Donkey Kong",
    "Dr Mario",
    "Duck Hunt",
    "Falco",
    "Fox",
    "Ganondorf",
    "Greninja",
    "Hero",
    "Ice Climbers",
    "Ike",
    "Incineroar",
    "Inkling",
    "Isabelle",
    "Jigglypuff",
    "Joker",
    "Kazuya Mishima",
    "Ken",
    "King Dedede",
    "King K Rool",
    "Kirby",
    "Link",
    "Little Mac",
    "Lucario",
    "Lucas",
    "Lucina",
    "Luigi",
    "Mario",
    "Marth",
    "Mega Man",
    "Meta Knight",
    "Mewtwo",
    "Mii",
    "Min Min",
    "Mr Game and Watch",
    "Ness",
    "Olimar (Alph)",
    "Pac-Man",
    "Palutena",
    "Peach",
    "Pichu",
    "Pikachu",
    "Piranha Plant",
    "Pit",
    "Pokémon Trainer",
    "Pokémon Trainer (Charizard)",
    "Pokémon Trainer (Ivysaur)",
    "Pokémon Trainer (Squirtle)",
    "Pyra and Mythra",
    "Richter",
    "Ridley",
    "ROB",
    "Robin",
    "Rosalina and Luma",
    "Roy",
    "Ryu",
    "Samus",
    "Sephiroth",
    "Sheik",
    "Shulk",
    "Simon",
    "Snake",
    "Sonic",
    "Sora",
    "Steve",
    "Terry Bogard",
    "Toon Link",
    "Villager",
    "Wario",
    "Wii Fit Trainer",
    "Wolf",
    "Yoshi",
    "Young Link",
    "Zelda",
    "Zero Suit Samus"
]
_character_mapping = {

    "Banjo & Kazooie": "banjo_and_kazooie",
    "Bayonetta": "bayonetta",
    "Bowser": "bowser",
    "Bowser Jr (Koopalings)": "bowser_jr",
    "Byleth": "byleth",
    "Captain Falcon": "captain_falcon",
    "Chrom": "chrom",
    "Cloud": "cloud",
    "Corrin": "corrin",
    "Daisy": "daisy",
    "Dark Pit": "dark_pit",
    "Dark Samus": "dark_samus",
    "Diddy Kong": "diddy_kong",
    "Donkey Kong": "donkey_kong",
    "Hero": "dq_hero",
    "Dr Mario": "dr_mario",
    "Duck Hunt": "duck_hunt",
    "Falco": "falco",
    "Fox": "fox",
    "Ganondorf": "ganondorf",
    "Greninja": "greninja",
    "Ice Climbers": "ice_climbers",
    "Ike": "ike",
    "Incineroar": "incineroar",
    "Inkling": "inkling",
    "Isabelle": "isabelle",
    "Kazuya Mishima": "demon",
    "Jigglypuff": "jigglypuff",
    "Joker": "joker",
    "Ken": "ken",
    "King Dedede": "king_dedede",
    "King K Rool": "king_k_rool",
    "Kirby": "kirby",
    "Link": "link",
    "Little Mac": "little_mac",
    "Lucario": "lucario",
    "Lucas": "lucas",
    "Lucina": "lucina",
    "Luigi": "luigi",
    "Mario": "mario",
    "Marth": "marth",
    "Mega Man": "mega_man",
    "Meta Knight": "meta_knight",
    "Mewtwo": "mewtwo",
    "Min Min": "minmin",
    "Mr Game and Watch": "mr_game_and_watch",
    "Ness": "ness",
    "Olimar (Alph)": "olimar",
    "Pac-Man": "pac_man",
    "Palutena": "palutena",
    "Peach": "peach",
    "Pichu": "pichu",
    "Pikachu": "pikachu",
    "Piranha Plant": "piranha_plant",
    "Pit": "pit",
    "Pokémon Trainer": "pokemon_trainer",
    "Pyra and Mythra": "pyra",
    "Richter": "richter",
    "Ridley": "ridley",
    "ROB": "rob",
    "Robin": "robin",
    "Rosalina and Luma": "rosalina_and_luma",
    "Roy": "roy",
    "Ryu": "ryu",
    "Samus": "samus",
    "Sephiroth": "sephiroth",
    "Sheik": "sheik",
    "Shulk": "shulk",
    "Simon": "simon",
    "Snake": "snake",
    "Sonic": "sonic",
    "Sora": "sora",
    "Steve": "steve",
    "Terry Bogard": "terry",
    "Toon Link": "toon_link",
    "Villager": "villager",
    "Wario": "wario",
    "Wii Fit Trainer": "wii_fit_trainer",
    "Wolf": "wolf",
    "Yoshi": "yoshi",
    "Young Link": "young_link",
    "Zelda": "zelda",
    "Zero Suit Samus": "zero_suit_samus"
}

# TODO: Add stock icons conversion between names


def create_char_filename(char_name, char_file):
    """
    Create the character destination filename based off of the input name and filename.
    Extracts the alt from the filename
    This also handles off cases such as The Mii characters
    :param char_name:
    :param char_file:
    :return:
    """
    # Grab alt number from file name (5th last element) and increment by 1
    alt_num = int(char_file[-5]) + 1
    alt_str = "(" + str(alt_num) + ")"
    # Handle specific cases
    if char_name == "Mii":
        if "miigunn" in char_file:
            char_name = "Mii Gunner"
        elif "miiswordsman" in char_file:
            char_name = "Mii Swordsman"
        elif "miifight" in char_file:
            char_name = "Mii Brawler"
        else:
            char_name = "Mii Fighters"
    elif char_name == "Pokémon Trainer":
        char_name = "Pokemon Trainer"
    elif char_name == "Terry Bogard":
        char_name = "Terry"
    elif char_name == "Pyra and Mythra":
        char_name = "Pyra"
    # Create dest filename
    dest_filename = char_name + " " + alt_str + ".png"
    return dest_filename


def create_char_filename2(char_name, char_file):
    """
    Create the character destination filename based off of the input name and filename.
    Extracts the alt from the filename
    This also handles off cases such as The Mii characters
    :param char_name:
    :param char_file:
    :return:
    """
    # Grab alt number from file name (5th last element) and increment by 1
    alt_num = char_file[-5]
    if alt_num == 'n':
        alt_num = 1
    alt_str = "(" + str(alt_num) + ")"
    # Handle specific cases
    if char_name == "Mii":
        if "miigunn" in char_file:
            char_name = "Mii Gunner"
        elif "miiswordsman" in char_file:
            char_name = "Mii Swordsman"
        elif "miifight" in char_file:
            char_name = "Mii Brawler"
        else:
            char_name = "Mii Fighters"
    elif char_name == "Pokémon Trainer":
        char_name = "Pokemon Trainer"
    elif char_name == "Terry Bogard":
        char_name = "Terry"
    elif char_name == "Pyra and Mythra":
        char_name = "Pyra"
    # Create dest filename
    dest_filename = char_name + " " + alt_str + ".png"
    return dest_filename


def organize_from_renders_zip(char_name, new_folder_location):
    """
    Organize images from zip file structure to new renders structure provided a character name
    Zip structure is in the following format
        Super Smash Bros Ultimate/Fighter Portraits/{Character}
            chara_0_{char_shorthand}_00.png
            ...
            chara_0_{char_shorthand}_07.png
            chara_1_{char_shorthand}_00.png
            ...
    Desired location is in the following format
        Renders
            Square render
                Character (1)
                ...
                Character (8)
            Body render
            Wide render
            Diamond render
    Move the images from the zip structure to the new location
        chara_0 --> Square render
        chara_1 --> Body render
        chara_3 --> Wide render
        chara_4 --> Diamond render
        chara_5 --> Single Full render
        chara_6 --> Face render
        chara_7 --> Single render with shadow
    Create mapping for images to new format:
        chara_0_{char_shorthand}_00.png --> char_name (1)
        ...
        chara_0_{char_shorthand}_07.png --> char_name (8)
    return a mapping of (source_folder, source_filename, new_folder, new_filename)
    :param char_name:
    :param new_folder_location:
    :return:
    """
    # Create return mapping for character files
    #  mapping has structure (source_filename, new_filename)
    return_mapping = []
    # Lookup character folder
    source_path = os.path.join("Input_Folder", "Super Smash Bros Ultimate", "Fighter Portraits")
    if char_name not in os.listdir(source_path):
        return return_mapping
    # Character folder exists
    source_path = os.path.join(source_path, char_name)
    # source_path = os.path.join("Character_Renders_Backup", "Full body")
    filenames = os.listdir(source_path)
    # Walk through files
    for a_file in filenames:
        # Expecting this format:
        #  chara_{render}_{char_shorthand}_{render #}.png
        #  Ex. chara_0_buddy_00.png
        if a_file.endswith(".png") and a_file.startswith("chara_") and a_file[-7:-5] == '_0':
            # Create filename for character "{char} (0).png", ..., "{char} (8).png"
            dest_file = create_char_filename(char_name, a_file)
            # Save information based off filename
            if a_file.startswith("chara_0_"):  # Char 0 case
                dest_folder = os.path.join(new_folder_location, "Square render")
                return_mapping.append((source_path, a_file, dest_folder, dest_file))
            elif a_file.startswith("chara_1_"):  # Char 1 case
                dest_folder = os.path.join(new_folder_location, "Body render")
                return_mapping.append((source_path, a_file, dest_folder, dest_file))
            elif a_file.startswith("chara_3_"):  # Char 3 case
                continue  # Skipping
                dest_folder = os.path.join(new_folder_location, "Wide render")
                return_mapping.append((source_path, a_file, dest_folder, dest_file))
            elif a_file.startswith("chara_4_"):  # Char 4 case
                dest_folder = os.path.join(new_folder_location, "Diamond render")
                return_mapping.append((source_path, a_file, dest_folder, dest_file))
            elif a_file.startswith("chara_6_"):  # Char 6 case
                continue # Skipping
                dest_folder = os.path.join(new_folder_location, "Face render")
                return_mapping.append((source_path, a_file, dest_folder, dest_file))
            # end of chara case
        elif a_file.endswith(".png") and "main" in a_file:
            # Full render case
            if char_name not in _character_mapping.keys():
                print("Note:", char_name, "not found in mapping")
                continue
            # check if source file {character}_main exists
            s_char_name = _character_mapping[char_name]
            if not a_file.startswith(s_char_name.lower() + "_main"):
                continue
            # Create filename for character "{char} (0).png", ..., "{char} (8).png"
            dest_file = create_char_filename2(char_name, a_file)
            dest_folder = os.path.join(new_folder_location, "Full render")
            return_mapping.append((source_path, a_file, dest_folder, dest_file))
            # end of main case
        # end of loop
    return return_mapping


def save_char_files(file_mapping):
    """
    Given a file mapping, save a copy of the source file to the new file location and name
    file_mapping has structure [(source folder 1, source file 1, dest folder 1, dest file 1)]
    :param file_mapping:
    :return:
    """
    if not file_mapping:
        return False
    for s_folder, s_file, d_folder, d_file in file_mapping:
        # Create folder if it does not exist
        if not os.path.exists(d_folder):
            os.makedirs(d_folder)
        # check if destination file already exists, skip copy if it does
        d_path = os.path.join(d_folder, d_file)
        if os.path.exists(d_path):
            print("\tPath:", d_path, "skipped")
            continue
        # Copy file to new folder if it
        s_path = os.path.join(s_folder, s_file)
        shutil.copy(s_path, d_folder)
        # Rename copied file to destination path
        cpy_file = os.path.join(d_folder, s_file)
        os.rename(cpy_file, d_path)
    return True


if __name__ == "__main__":
    # Loop through character list
    save_location = os.path.join("Output_Folder")
    for a_char in _character_list:
        char_file_mapping = organize_from_renders_zip(a_char, save_location)
        if save_char_files(char_file_mapping):
            print(a_char, "saved successfully")
    print("Done")

