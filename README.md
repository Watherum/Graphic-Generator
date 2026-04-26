# Graphic Generation
This project is based off the work of my good friend CR_Jetstream!

This project is now mainly focused on generating thumbnails and top 8 graphics for Rivals 2. 
Ultimate Support is still maintained but not the main focus. Some Melee support exists as well.

Using the docs below and the Rivals 2 section as a guide you can use this for either game. Or modify it to create thumbnails for a new game

## Notes
Currently these scripts only run with python 3.9. An exe is included.

## Usage
Before anything run the requirements_isntall.cmd file to make sure all dependencies are installed correctly.

Go into the {Game} Generator and edit the fetch_sets.cmd file to your tournament slug and event from start gg. 
Then run the file. This will generate a text file in the \Vod_names folder. Edit that file and remove all matches not on stream.
Add any character data that may be missing. 
Then create / run a Run_{event}.cmd file which will generate your thumbnails in the \Youtube_Thumbnails folder of the generator. 
I recommend creating a cmd file for each event you need it for. 

To customize what your thumbnails will looks like, ensure that you have a foreground and a background for your thumbnails in \Resources\Overlays.
I recommend using canva or something similar to build out what you need. 

You will also need to modify populate_globals.py and create functions for your event. 

## Maintainence
Add new skins to \Resources\Character_Renders\Full render

Add new characters to \Resources\Character_database.csv

Add new competitors and adjust their skins in \Resources\player_database.csv

## Generating Top 8 Graphics

While possible its a lot of trial and error to get perfect. 

You will still need a foreground and a background image, but they go in \Resources\Top8_Graphics

In {Game} Generator\Top_8_Infos be sure to make your top 8 file to populate the data. 

Lastly, edit create_top8_graphic with your event and use trial and error to place and edit all texts and images where you like. 

Run Run_Top8 to generate a top 8 graphic. It will be placed in {Game} Generator\Top_8_Results\{Event name}

You may need to create the {Game} Generator\Top_8_Results & {Game} Generator\Top_8_Infos folders.


# Original Readme
A project for quickly creating YouTube Thumbnails and Top 8 Graphgics for Nintendo fighting game Super Smash Brothers Ultimate.
The purpose of this project is to provide an efficient way to create these images. This is especially useful for weekly events or big events with lots of videos.

[The source of this project is available here][https://github.com/CR-Jetstream/SSBU_Thumbnails].

This project has been a side project and has no current commitment to long term support.