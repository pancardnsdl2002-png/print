@echo off
py -m pip install -r requirements.txt
py -m PyInstaller --onefile --windowed desktop\admin_app.py --name PrintAdmin
echo Desktop app created at dist\PrintAdmin.exe
pause
