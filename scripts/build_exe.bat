@echo off
py -m pip install -r requirements.txt
py -m PyInstaller --onefile --console desktop\print_client.py --name PrintClient
echo EXE created in dist\PrintClient.exe
pause
