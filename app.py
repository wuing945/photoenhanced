from __future__ import annotations
import argparse, json, os, queue, secrets, sys, threading, time, traceback, webbrowser, io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
from engine import Retoucher, Settings, SUPPORTED, load_photo

ROOT=Path(__file__).resolve().parent
CONFIG=ROOT/'settings.json'
OUTPUT=ROOT/'results';INPUT=ROOT/'work'/'inputs'
try:
    saved_output=Path(json.loads(CONFIG.read_text(encoding='utf-8'))['output_dir'])
    if saved_output.is_absolute():OUTPUT=saved_output
except (OSError,ValueError,KeyError):pass
for p in [OUTPUT,INPUT]:p.mkdir(parents=True,exist_ok=True)
TOKEN=secrets.token_urlsafe(24)
LOCK=threading.Lock();JOBS={};FILES={};QUEUE=queue.Queue();CANCEL=threading.Event()
STATE={'ready':False,'error':'','stage':'���J�����ҫ�'}
PICKER_LOCK=threading.Lock()
for folder in INPUT.iterdir():
    if folder.is_dir():
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() in SUPPORTED:FILES[folder.name]=f
for report in sorted(OUTPUT.glob('*_report.json'))[-100:]:
    try:
        saved=json.loads(report.read_text(encoding='utf-8'))
        if saved.get('status')=='done' and (OUTPUT/saved['output']).is_file():
            saved['id']=report.stem;saved['output_dir']=str(OUTPUT);JOBS[report.stem]=saved
    except (ValueError,KeyError,OSError):pass

def worker():
    try:
        engine=Retoucher()
        STATE.update(ready=True,stage='�N��')
    except Exception as e:
        STATE.update(error=str(e),stage='�Ұʥ���')
        traceback.print_exc();return
    while True:
        job=QUEUE.get()
        try:
            if CANCEL.is_set():job.update(status='cancelled',message='�w����');continue
            job.update(status='running',message='�}�l�B�z')
            def progress(stage):job['message']=stage
            result=engine.process(job['path'],job['output_dir'],job['settings'],progress,edits=job.get('edits'))
            job.update(result)
        except Exception as e:
            traceback.print_exc();job.update(status='error',message=str(e))
        finally:QUEUE.task_done()

def public_job(job):return {k:v for k,v in job.items() if k not in ('path','edits')}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,body,kind='application/json; charset=utf-8'):
        if isinstance(body,(dict,list)):body=json.dumps(body,ensure_ascii=False).encode('utf-8')
        elif isinstance(body,str):body=body.encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def route(self):
        path=urlsplit(self.path).path
        host=self.headers.get('Host','')
        if host not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):
            raise ValueError('�L�Ī������ӷ�')
        prefix='/'+TOKEN
        if not path.startswith(prefix+'/'):raise PermissionError('�L�Ī��u�@���q')
        origin=self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
            raise PermissionError('�u�������������ШD')
        return unquote(path[len(prefix):])
    def do_GET(self):
        try:
            path=self.route()
            if path=='/':return self.send(200,(ROOT/'ui.html').read_bytes(),'text/html; charset=utf-8')
            if path=='/editor.js':return self.send(200,(ROOT/'editor.js').read_bytes(),'text/javascript; charset=utf-8')
            if path.startswith('/source/'):
                ident=path.split('/')[2]
                if ident not in FILES:raise ValueError('�Э��s�[�J�ӷ��Ӥ�')
                image,_,_,_=load_photo(FILES[ident])
                buf=io.BytesIO();image.save(buf,format='JPEG',quality=96,subsampling=0)
                return self.send(200,buf.getvalue(),'image/jpeg')
            if path=='/api/state':
                with LOCK:data={'state':dict(STATE),'jobs':[public_job(j) for j in JOBS.values()],'output':str(OUTPUT),'files':[{'id':k,'name':v.name} for k,v in FILES.items()]}
                return self.send(200,data)
            if path.startswith('/file/'):
                name=path[6:]
                if Path(name).name!=name or '/' in name or '\\' in name:raise ValueError('�L�Ī��ɦW')
                f=None
                for job in JOBS.values():
                    names=[job.get(k) for k in ('output','preview','before','mask')]+job.get('comparisons',[])
                    if name in names:
                        candidate=Path(job.get('output_dir',str(OUTPUT)))/name
                        if candidate.is_file():f=candidate;break
                if f is None:return self.send(404,{'error':'�䤣���ɮ�'})
                kind={'.jpg':'image/jpeg','.png':'image/png','.json':'application/json'}.get(f.suffix,'application/octet-stream')
                return self.send(200,f.read_bytes(),kind)
            return self.send(404,{'error':'�䤣�쭶��'})
        except PermissionError as e:self.send(403,{'error':str(e)})
        except Exception as e:self.send(400,{'error':str(e)})
    def do_POST(self):
        global OUTPUT
        try:
            path=self.route()
            length=int(self.headers.get('Content-Length','0'))
            if not 0<=length<=150*1024*1024:raise ValueError('��i�ɮפW���� 150 MB')
            raw=self.rfile.read(length)
            if path=='/api/upload':
                name=Path(unquote(self.headers.get('X-File-Name','photo.jpg'))).name
                if Path(name).suffix.lower() not in SUPPORTED:raise ValueError('�䴩 JPG�BPNG�BWebP�BBMP �P�歶 TIFF')
                ident=secrets.token_hex(8);folder=INPUT/ident;folder.mkdir()
                p=folder/name;p.write_bytes(raw)
                FILES[ident]=p
                return self.send(200,{'id':ident,'name':name})
            data=json.loads(raw or b'{}')
            if path in ('/api/set-output','/api/choose-output'):
                if path=='/api/choose-output':
                    if any(j['status'] in ('queued','running') for j in JOBS.values()):
                        raise ValueError('�е��ثe�妸������A�ܧ��X��Ƨ�')
                    if not PICKER_LOCK.acquire(blocking=False):raise ValueError('��Ƨ���ܵ����w�}��')
                    try:
                        from folder_picker import choose_folder
                        chosen=choose_folder(str(OUTPUT))
                    finally:PICKER_LOCK.release()
                    if not chosen:return self.send(200,{'cancelled':True,'output':str(OUTPUT)})
                    data={'path':chosen}
                with LOCK:
                    if any(j['status'] in ('queued','running') for j in JOBS.values()):
                        raise ValueError('�е��ثe�妸������A�ܧ��X��Ƨ�')
                    value=str(data.get('path','')).strip().strip('"')
                    if not value:raise ValueError('�п�J��X��Ƨ���������|')
                    destination=Path(os.path.expandvars(value)).expanduser()
                    if not destination.is_absolute():raise ValueError('�п�J������|�A�Ҧp D:\\�׹Ϧ��~')
                    destination=destination.resolve()
                    destination.mkdir(parents=True,exist_ok=True)
                    import tempfile
                    with tempfile.TemporaryFile(dir=destination):pass
                    temporary=CONFIG.with_suffix('.tmp')
                    temporary.write_text(json.dumps({'output_dir':str(destination)},ensure_ascii=False),encoding='utf-8')
                    temporary.replace(CONFIG)
                    OUTPUT=destination
                return self.send(200,{'output':str(OUTPUT)})
            if path=='/api/start':
                if not STATE['ready']:raise ValueError(STATE['error'] or '�ҫ����b���J')
                settings=Settings.parse(data.get('settings')).__dict__
                ids=data.get('ids',[])
                edits=data.get('edits',[])
                if not isinstance(edits,list) or len(edits)>1000:raise ValueError('����ƶq�L�h')
                if edits and len(ids)!=1:raise ValueError('��ʵ���@���u��M�Τ@�i�ӷ��Ӥ�')
                if not ids:raise ValueError('�Х��[�J�Ӥ�')
                if any(i not in FILES for i in ids):raise ValueError('�Ӥ��u�@���q�w���ġA�Э��s�[�J')
                if any(j['status'] in ('queued','running') for j in JOBS.values()):raise ValueError('�е��ثe�妸������A�}�l')
                CANCEL.clear();created=[]
                for ident in ids:
                    jid=secrets.token_hex(8);p=FILES[ident]
                    job={'id':jid,'name':p.name,'path':str(p),'status':'queued','message':'���ݳB�z','settings':settings,'output_dir':str(OUTPUT),'edits':edits,'source_id':ident}
                    with LOCK:JOBS[jid]=job
                    QUEUE.put(job);created.append(jid)
                return self.send(200,{'jobs':created})
            if path=='/api/cancel':CANCEL.set();return self.send(200,{'ok':True})
            if path=='/api/open-output':os.startfile(OUTPUT);return self.send(200,{'ok':True})
            if path=='/api/shutdown':
                if any(j['status'] in ('queued','running') for j in JOBS.values()):raise ValueError('�Х����ݩΨ����ثe�妸')
                self.send(200,{'ok':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            self.send(404,{'error':'�䤣��ާ@'})
        except PermissionError as e:self.send(403,{'error':str(e)})
        except Exception as e:self.send(400,{'error':str(e)})

def main():
    global OUTPUT
    parser=argparse.ArgumentParser();parser.add_argument('inputs',nargs='*');parser.add_argument('--no-browser',action='store_true');parser.add_argument('--port',type=int,default=0);parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    if args.output_dir:
        OUTPUT=args.output_dir.expanduser().resolve();OUTPUT.mkdir(parents=True,exist_ok=True)
    if args.inputs:
        engine=Retoucher();failed=False
        try:
            for item in args.inputs:
                p=Path(item);paths=sorted(q for q in p.rglob('*') if q.suffix.lower() in SUPPORTED and q.is_file()) if p.is_dir() else [p]
                for f in paths:
                    try:print(json.dumps(engine.process(f,OUTPUT),ensure_ascii=False),flush=True)
                    except Exception as e:failed=True;print(json.dumps({'name':f.name,'status':'error','message':str(e)},ensure_ascii=False),flush=True)
        finally:engine.close()
        return 1 if failed else 0
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    url=f'http://127.0.0.1:{server.server_port}/{TOKEN}/'
    (ROOT/'work'/'session.json').write_text(json.dumps({'url':url,'pid':os.getpid()}),encoding='utf-8')
    print(url,flush=True)
    threading.Thread(target=worker,daemon=True).start()
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever(poll_interval=.3)
    finally:server.server_close()
    return 0

if __name__=='__main__':sys.exit(main())
