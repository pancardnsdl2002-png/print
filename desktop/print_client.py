import argparse, os, time
from pathlib import Path
import requests

QUEUE = Path.home() / "PrintingClient" / "offline_queue"
QUEUE.mkdir(parents=True, exist_ok=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--server',default='http://127.0.0.1:8000')
    p.add_argument('--token',default=os.getenv('ADMIN_TOKEN','change-me-now'))
    p.add_argument('--interval',type=int,default=10)
    p.add_argument('--no-print',action='store_true')
    a=p.parse_args(); base=a.server.rstrip('/'); headers={'X-Admin-Token':a.token}
    print('Client started. Local queue:',QUEUE)
    while True:
        try:
            jobs=requests.get(base+'/api/desktop/jobs',headers=headers,timeout=15).json()
            for j in jobs:
                jid=j['id']; path=QUEUE/(f"job_{jid}_"+Path(j['original_name']).name)
                if not path.exists():
                    r=requests.get(f'{base}/api/desktop/jobs/{jid}/file',headers=headers,timeout=60); r.raise_for_status(); path.write_bytes(r.content)
                if a.no_print:
                    print('Downloaded only:',path); continue
                if os.name=='nt':
                    try:
                        os.startfile(str(path),'print')
                        print('Sent to default app for printing:',path)
                        print('IMPORTANT: verify physical print before completing this job.')
                        # Do not auto-complete: default print command may return before printing finishes.
                    except Exception as e: print('Print command failed:',e)
                else: print('Downloaded for manual printing:',path)
        except Exception as e: print('Server unavailable; downloaded local files remain:',e)
        time.sleep(max(3,a.interval))
if __name__=='__main__': main()
