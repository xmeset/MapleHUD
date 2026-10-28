@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv || exit /b 1
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || exit /b 1
)
".venv\Scripts\python.exe" -m pip install -q pyinstaller || exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --name MapleHUD --icon MapleHUD.ico ^
  --paths engine --collect-all winrt ^
  --add-data "engine\assets;assets" --add-data "potki.json;." --add-data "MapleHUD.ico;." --add-data "ikony;ikony" ^
  maple_hud.py || exit /b 1
copy /y potki.json dist\MapleHUD\potki.json >nul
copy /y CZYTAJ.txt dist\MapleHUD\CZYTAJ.txt >nul
copy /y LICENSE.txt dist\MapleHUD\LICENSE.txt >nul
copy /y engine\LICENSE dist\MapleHUD\THIRD-PARTY-LICENSES.txt >nul
powershell -NoProfile -Command "Compress-Archive -Force -Path dist\MapleHUD -DestinationPath ..\MapleHUD.zip"
robocopy dist\MapleHUD ..\MapleHUD /E /XF potki.json /R:0 /W:0 /NFL /NDL /NJH /NJS >nul
if errorlevel 8 echo Uwaga: MapleHUD.exe jest wlaczony - zamknij go i odpal build.bat jeszcze raz.
echo Gotowe: ..\MapleHUD (apka) i ..\MapleHUD.zip (dla znajomych)
