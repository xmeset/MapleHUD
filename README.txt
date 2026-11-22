MapleHUD - overlay for MapleStory Classic World
================================================

What it shows (two small panels on both sides of the game's bottom bar):
  left:  LV, map, EXP/hr and % of level/hr, EXP/hr over the last 5 min, time to next level
         square button = end grind and summary, triangle = new grind
         clock = loot pickup timer (1:30 by default, then "LOOT!")
         arrow ^ = best maps, level goal and TODAY (EXP, time, EXP/h, mesos today);
         click a map = all its runs
  right: meso/h, potion cost/h, net/h (arrow ^ = potion list, your pet and what it drinks)

How to run:
  1. Extract the whole folder (right-click the zip > Extract All).
  2. Start the game (windowed or borderless works best).
  3. Run MapleHUD.exe.
  Windows may show "Windows protected your PC" - click
  "More info" > "Run anyway" (the program isn't signed).

Language: follows Windows. To change: right-click a panel > Jezyk / Language.

Where the data comes from (screenshots only, nothing in the game is changed):
  EXP     - the EXP bar at the bottom of the game
  meso    - the meso counter in your inventory: open it now and then
            (loot sold at a shop during a grind counts as earnings)
  potions - item counts on the quickslot, and HP/MP jumps on the status bar
            (pet potions included)
  map     - name from the minimap (the minimap must be open)

Settings:
  potki.json - which potions to count ("uzywane"), how much HP/MP they give and their
               prices ("cena"). After a change: right-click a panel > Reload potki.json.
  Right-click a panel: start/pause, end grind, reset, timer, pet potions, opacity, language, close.
  Final Attack (bowman): while the buff is up, its icon shows by the quickslot.

Results are saved in the data folder:
  mapy.csv  - time, EXP, EXP/hr, meso, potion cost, net, meso/h and net/h per map
              (open in Excel; close it before playing)
  sesje.csv - the same for the whole grind
  sesja.log - detailed log (useful when something doesn't work)

MapleHUD (c) 2026 tesem
Licenses of the open source components used: THIRD-PARTY-LICENSES.txt
