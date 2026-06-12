:: Script to grab all the character  renders from the Smash Bros Ultimate website
:: https://www.smashbros.com/en_US/fighter/index.html
:: This script saves all characters and alts in the Full_Render folder adjacent to the script

@echo off

for %%x in (
banjo_and_kazooie
bayonetta
bowser
bowser_jr
byleth
captain_falcon
chrom
cloud
corrin
daisy
dark_pit
dark_samus
diddy_kong
donkey_kong
dq_hero
dr_mario
duck_hunt
falco
fox
ganondorf
greninja
ice_climbers
ike
incineroar
inkling
isabelle
jigglypuff
joker
ken
king_dedede
king_k_rool
kirby
link
little_mac
lucario
lucas
lucina
luigi
mario
marth
mega_man
meta_knight
mewtwo
minmin
mr_game_and_watch
ness
olimar
pac_man
palutena
peach
pichu
pikachu
piranha_plant
pit
pokemon_trainer
pyra
richter
ridley
rob
robin
rosalina_and_luma
roy
ryu
samus
sephiroth
sheik
shulk
simon
snake
sonic
steve
terry
toon_link
villager
wario
wii_fit_trainer
wolf
yoshi
young_link
zelda
zero_suit_samus
) do (
echo Character is %%x
	for %%y in (main main2 main3 main4 main5 main6 main7 main8) do (
	powershell -Command "Invoke-WebRequest https://www.smashbros.com/assets_v2/img/fighter/%%x/%%y.png -OutFile Input_Folder/Full_Render/%%x_%%y.png"
	)
)
pause