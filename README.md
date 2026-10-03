# Printing System: Browser Customer + Windows Admin App

Customers use the online website in their browser. The admin uses the separate Windows desktop app `desktop/admin_app.py`. Both connect to the same API server.

## Local test (Windows)
1. Install Python 3.11+.
2. Open Command Prompt in this folder.
3. Run `py -m venv .venv`
4. Run `.venv\\Scripts\\activate`
5. Run `pip install -r requirements.txt`
6. Set a private admin token: `set ADMIN_TOKEN=replace-with-a-long-random-secret`
7. Start API: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
8. Customer test page: `http://127.0.0.1:8000`
9. Open a second terminal and run `python desktop/admin_app.py --server http://127.0.0.1:8000`

## Build admin EXE
Run `scripts/build_admin_exe.bat`. The EXE is generated at `dist/PrintAdmin.exe`. This creates a packaged EXE, not a full click-through installer.

## Public launch requirements
Host the API on an internet-accessible server with HTTPS. Customers cannot reach a server running only on your own computer unless you configure secure hosting/network access. Use a strong admin token and add proper login/access control before public use.

## Important functional limitations
This is a starter project. Actual 4-in-1/6-in-1 PDF layout, reliable duplex printing, print preview, and physical print verification need further implementation/testing with your printer. The admin app sends files to the operating system's default print application; verify output before marking a job complete. Rejected/completed server files are deleted by the API.
