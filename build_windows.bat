@echo off
setlocal
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py -m pip install pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed --name TalkLite talklite.py

echo.
echo Build complete: dist\TalkLite.exe
pause
