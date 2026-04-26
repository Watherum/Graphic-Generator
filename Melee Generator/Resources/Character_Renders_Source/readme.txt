This is the backup folder. This folder is used to acquire the renders.

The renders come from two places. 
* https://www.spriters-resource.com/nintendo_switch/supersmashbrosultimate/
	This holds the renders for the characters. This also holds the stock icons
* https://www.smashbros.com/en_US/fighter/index.html/
	This holds the full character model renders (not present in the previous location).
The website links are in this folder.

The spriters-resource.com website allows you to download each character renders.
	All characters have the zip file: "Nintendo Switch - Super Smash Bros Ultimate - {Fighter}.zip"
	Contents in the folder: \Super Smash Bros Ultimate\Fighter Portraits\{Figheter}\{Images}
	Stock Icons location: \Super Smash Bros Ultimate\Stock Icons
	All these folders must be placed inside Input_Folder as the root
		Input_Folder\Super Smash Bros Ultimate\...

The download & download_all.bat files are used with the smashbros.com website, and place the renders in the Full_Render folder.
	download.bat allows the user to grab the renders for one character
	download_all.bat will loop through all the characters. This will result in over 1GB of images

The Series Icons image is also present in this folder.

The organize_renders.py will take all the renders and place them neatly in the Output_Folder
	Each character will be labeled as "{Fighter} (alt)" in the corresponding folder
	Both Stock and Fighter images must be placed inside the Input_Folder for the script to function

	Once the script is complete, the Output_Folder will be populated