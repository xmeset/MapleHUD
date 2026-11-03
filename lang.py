import ctypes

LANG = "pl"

EN = {
    "Nie widzę okna MapleStory. Gra włączona?": "MapleStory window not found. Is the game running?",
    "Gra jest zminimalizowana.": "The game is minimized.",
    "Nie widzę paska EXP na dole gry. Coś go zasłania?": "Can't see the EXP bar at the bottom. Is something covering it?",
    "Overlay zasłania meso w ekwipunku – przesuń eq.": "The overlay covers the mesos in your inventory – move the inventory.",
    "Overlay zasłania pasek EXP.": "The overlay covers the EXP bar.",
    "Otwarty storage – zmiany meso pomijane.": "Storage open – meso changes ignored.",
    "Otwarty sklep – zmiany meso pomijane.": "Shop open – meso changes ignored.",
    "Otwarty trade – zmiany meso pomijane.": "Trade open – meso changes ignored.",
    "Nie mogę odczytać meso.": "Can't read the mesos.",
    "Pasek pokazuje tylko %. PPM > Ustaw poziom.": "The bar shows only %. Right-click > Set level.",
    "Śmierć – strata EXP nie liczy się do EXP/h.": "Died – the EXP loss doesn't count towards EXP/h.",
    "Szukam gry...": "Looking for the game...",
    "szukaj…": "search…",
    "brak": "none",
    "nic nie pasuje": "no matches",
    "Start / Pauza": "Start / Pause",
    "Koniec grindu (podsumowanie)": "End grind (summary)",
    "Reset sesji": "Reset session",
    "Szczegóły potów": "Potion details",
    "Pet: pot HP": "Pet: HP potion",
    "Pet: pot MP": "Pet: MP potion",
    "Edytuj potki.json (ceny, HP/MP, używane)": "Edit potki.json (prices, HP/MP, potions used)",
    "Wczytaj potki.json": "Reload potki.json",
    "Ustaw poziom (gdy pasek ma tylko %)": "Set level (when the bar shows only %)",
    "Przezroczystość": "Opacity",
    "Zamknij": "Close",
    "DO LV {}": "TO LV {}",
    "DO LVL": "TO LVL",
    "OST. 5 MIN": "LAST 5 MIN",
    "poty −{}": "pots −{}",
    "nie widzę HP/MP": "can't see HP/MP",
    "otwórz eq": "open inv",
    "POTY/HR": "POTS/HR",
    "NETTO/HR": "NET/HR",
    "Nie widzę HP/MP na pasku – poty nie są liczone.": "Can't see HP/MP on the status bar – potions aren't counted.",
    "Poty liczone dopiero gdy idzie EXP.": "Potions are counted only while you gain EXP.",
    "Ostatnio: {} ({} temu)": "Last: {} ({} ago)",
    "POTY": "POTIONS",
    "UŻYTE": "USED",
    "NA HR": "PER HR",
    "KOSZT": "COST",
    "wybierz": "choose",
    "bez peta": "no pet",
    "TWÓJ PET": "YOUR PET",
    "pet nie pije nic": "pet drinks nothing",
    "nie do kupienia": "not sold",
    "POT {} PETA": "PET {} POTION",
    "Meso zebrane": "Meso looted",
    "eq nie było otwarte": "inventory wasn't opened",
    "Poty": "Potions",
    "Netto": "Net",
    "Zapisano w sesje.csv": "Saved to sesje.csv",
    "Za krótko, nie zapisano": "Too short, not saved",
    " · kliknij, aby zamknąć": " · click to close",
    "KONIEC GRINDU": "GRIND SUMMARY",
    "brak (nie liczę)": "none (not counted)",
    "Porównanie map": "Map comparison",
    "Cel levelu…": "Level goal…",
    "Docelowy poziom (0 = brak):": "Target level (0 = none):",
    "CEL": "GOAL",
    "DZIŚ": "TODAY",
    "kliknij, aby ustawić poziom": "click to set a target level",
    "teraz": "now",
    "Brak danych – mapa pojawia się po runie dłuższym niż 15 min.":
        "No data yet – a map shows up after a run longer than 15 min.",
    "najlepszy z {}": "best of {}",
    "MAPY": "MAPS",
    "najlepszy run na mapie": "best run per map",
    "TOP 3 MAPY": "TOP 3 MAPS",
    "Inne HP": "Other HP",
    "Inne MP": "Other MP",
    "nierozpoznane · {} meso za {}": "unrecognized · {} meso per {}",
    "Poziom": "Level",
    "Twój poziom (jak w grze):": "Your level (as in game):",
    "Krycie w % (60-100):": "Opacity in % (60-100):",
}


def system_lang():
    try:
        return "pl" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x15 else "en"
    except Exception:
        return "pl"


def set_lang(code):
    global LANG
    LANG = code if code in ("pl", "en") else system_lang()


def T(text):
    return EN.get(text, text) if LANG == "en" else text
