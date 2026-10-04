"""Quiet desktop launcher, with a visible error if startup fails."""
from pathlib import Path
import ctypes,json,os,sys,traceback,urllib.request,urllib.parse,webbrowser
root=Path(__file__).resolve().parent
try:
    (root/'work').mkdir(exist_ok=True)
    log=open(root/'work'/'startup.log','a',encoding='utf-8',buffering=1)
    sys.stdout=log;sys.stderr=log
    session=root/'work'/'session.json'
    if session.exists():
        try:
            url=json.loads(session.read_text(encoding='utf-8'))['url']
            parsed=urllib.parse.urlsplit(url)
            if parsed.scheme=='http' and parsed.hostname=='127.0.0.1':
                with urllib.request.urlopen(url+'api/state',timeout=2) as r:
                    state=json.load(r)
                if 'state' in state and 'jobs' in state:
                    webbrowser.open(url);sys.exit(0)
        except Exception:pass
    from app import main
    main()
except Exception as e:
    traceback.print_exc()
    ctypes.windll.user32.MessageBoxW(None,'�L�k�Ұʥ����H���׹ϡG\n'+str(e)+'\n\n�нT�{ ZIP �w��������A�ìd�� work/startup.log�C','�Ұʥ���',0x10)
