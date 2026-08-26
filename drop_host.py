#!/usr/bin/env python3
"""Molt Agent Drop demo host: localhost HTTP behind an explicit SSH tunnel."""
import argparse, hashlib, hmac, json, os, secrets, signal, stat, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlparse

MAX_TEXT_BYTES = 2_000_000
MAX_OWNER_COMMAND_BYTES = 4096
def digest(value): return hashlib.sha256(value.encode()).hexdigest()

def is_link(path):
    if path.is_symlink(): return True
    if sys.platform == "win32":
        try: return bool(os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        except (AttributeError, OSError): return False
    return False

def _secure_open_flags():
    return getattr(os,"O_BINARY",0)|getattr(os,"O_NOFOLLOW",0)

def _check_private_regular_file(path,st):
    if getattr(st,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0):
        raise ValueError("owner command must not be a reparse point")
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise ValueError("owner command must be a single regular file")
    # Windows' st_mode does not describe its DACL. The enclosing state directory
    # is the Windows trust boundary; reparse points are rejected separately.
    if os.name != "nt" and stat.S_IMODE(st.st_mode)&0o077:
        raise PermissionError("owner command file permissions must be 0600 or stricter")

def validate_root(path, create=False):
    raw=Path(path).expanduser()
    if create: raw.mkdir(parents=True,exist_ok=True)
    root=raw.resolve(strict=True)
    if not root.is_dir() or is_link(root): raise ValueError("root must be a real directory, not a link/reparse point")
    if root == Path(root.anchor).resolve() or root == Path.home().resolve():
        raise ValueError("refusing filesystem/drive root or user home/profile")
    return root

class HostState:
    def __init__(self,root,state_dir,invite_ttl,session_ttl,create_root=False):
        if invite_ttl<=0 or session_ttl<=0: raise ValueError("TTLs must be positive")
        self.root=validate_root(root,create_root)
        state_raw=Path(state_dir).expanduser()
        state_raw.mkdir(parents=True,exist_ok=True)
        if is_link(state_raw): raise ValueError("state directory must not be a link/reparse point")
        self.state_dir=state_raw.resolve(strict=True)
        if self.state_dir==self.root or self.root in self.state_dir.parents: raise ValueError("state directory must be outside authorized root")
        if not self.state_dir.is_dir(): raise ValueError("state directory must be a directory")
        try: os.chmod(self.state_dir,0o700)
        except OSError: pass
        self.audit_path=self.state_dir/"audit.jsonl"; self.invite_id=secrets.token_urlsafe(18); self.invite_secret=secrets.token_urlsafe(32)
        self.invite_hash=digest(self.invite_secret); self.invite_deadline=time.monotonic()+invite_ttl*60; self.session_ttl=session_ttl*60
        self.pending={}; self.invite_consumed=False; self.claimed_request_id=None; self.token_hash=None; self.session_deadline=None
        self.revoked=False; self.frozen=False; self.lock=threading.RLock(); self.server=None; self.stopping=False
        self.audit("host_start","system","allowed",{"root":str(self.root)})

    def audit(self,event,request,decision,result=None):
        record={"ts":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"event":event,"request":request,"decision":decision,"result":result or {}}
        line=json.dumps(record,ensure_ascii=False,separators=(",",":"))+"\n"
        with self.lock:
            if self.audit_path.exists() and is_link(self.audit_path): raise OSError("audit path is a link/reparse point")
            fd=os.open(str(self.audit_path),os.O_WRONLY|os.O_CREAT|os.O_APPEND|_secure_open_flags(),0o600)
            try:
                st=os.fstat(fd)
                if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1: raise OSError("audit is not a single regular file")
                if getattr(st,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0): raise OSError("audit is a reparse point")
                if os.name!="nt" and stat.S_IMODE(st.st_mode)&0o077: raise OSError("audit permissions are broader than 0600")
                os.write(fd,line.encode()); os.fsync(fd)
            finally: os.close(fd)

    def request_pair(self,invite_id,secret,label):
        with self.lock:
            if time.monotonic()>=self.invite_deadline:
                self.audit("pair_request","pair","denied",{"reason":"invitation expired"}); raise PermissionError("invitation expired")
            valid=not self.invite_consumed and hmac.compare_digest(invite_id,self.invite_id) and hmac.compare_digest(digest(secret),self.invite_hash)
            if not valid:
                self.audit("pair_request","pair","denied",{"reason":"invalid invitation"}); raise PermissionError("invalid invitation")
            rid=secrets.token_urlsafe(18); clean_label=label[:100]
            self.audit("pair_request",rid,"pending",{"label":clean_label})
            self.pending[rid]={"status":"pending","label":clean_label,"token":None}
            self.invite_consumed=True; self.claimed_request_id=rid
            return rid

    def approve(self,rid):
        with self.lock:
            item=self.pending.get(rid)
            if not item or item["status"]!="pending" or self.claimed_request_id!=rid: raise ValueError("no pending request")
            if time.monotonic()>=self.invite_deadline:
                item["status"]="expired"; self.audit("approval",rid,"denied",{"reason":"invitation expired"}); raise ValueError("invitation expired")
            token=secrets.token_urlsafe(32)
            self.audit("approval",rid,"allowed",{"session_ttl_seconds":int(self.session_ttl)})
            self.token_hash=digest(token); self.session_deadline=time.monotonic()+self.session_ttl
            item.update(status="approved",token=token)

    def deny(self,rid):
        with self.lock:
            item=self.pending.get(rid)
            if not item or item["status"]!="pending": raise ValueError("no pending request")
            self.audit("approval",rid,"denied"); item["status"]="denied"

    def pair_result(self,rid,secret):
        with self.lock:
            item=self.pending.get(rid)
            if not item or not hmac.compare_digest(digest(secret),self.invite_hash): raise PermissionError("invalid pairing request")
            if item["status"]=="approved":
                token=item["token"]; item["token"]=None; item["status"]="delivered"
                return {"status":"approved","token":token,"expires_in":max(0,int(self.session_deadline-time.monotonic()))}
            return {"status":item["status"]}

    def session_status(self,token):
        with self.lock:
            if self.revoked:return "revoked"
            if self.frozen:return "frozen"
            if self.session_deadline is None:return "not approved"
            if time.monotonic()>=self.session_deadline:return "expired"
            if not token or not hmac.compare_digest(digest(token),self.token_hash):return "unauthorized"
            return "active"

    def revoke(self,reason="owner revoke"):
        with self.lock:
            # Revocation remains fail-safe even if its audit write is unavailable.
            self.revoked=True; self.token_hash=None
            self.audit("revoke","session","allowed",{"reason":reason})

    def safe_path(self,rel,missing=False):
        if not isinstance(rel,str) or not rel or "\\" in rel or "\0" in rel: raise ValueError("non-empty POSIX relative path required")
        pure=PurePosixPath(rel)
        if pure.is_absolute() or ".." in pure.parts or any(":" in x for x in pure.parts): raise ValueError("path traversal denied")
        current=self.root
        for part in pure.parts:
            current=current/part
            if current.exists() and is_link(current): raise ValueError("link/reparse-point path denied")
        parent=current.parent.resolve(strict=True)
        if current!=self.root and parent!=self.root and self.root not in parent.parents: raise ValueError("path escapes root")
        if not missing and not current.exists(): raise FileNotFoundError(rel)
        return current

    def stop(self):
        if not self.stopping:
            self.stopping=True
            try:self.revoke("host stop")
            except OSError:self.revoked=True
            if self.server:threading.Thread(target=self.server.shutdown,daemon=True).start()

class Handler(BaseHTTPRequestHandler):
    server_version="MoltDropDemo/1"
    def log_message(self,*_):pass
    @property
    def host(self):return self.server.host
    def reply(self,code,value):
        data=json.dumps(value,ensure_ascii=False).encode(); self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def body(self):
        n=int(self.headers.get("Content-Length","0"))
        if n<0 or n>MAX_TEXT_BYTES+4096:raise ValueError("request too large")
        value=json.loads(self.rfile.read(n))
        if not isinstance(value,dict):raise ValueError("JSON object required")
        return value
    def auth(self):
        header=self.headers.get("Authorization",""); token=header[7:] if header.startswith("Bearer ") else ""; status=self.host.session_status(token)
        if status!="active":
            self.host.audit("api_request",urlparse(self.path).path,"denied",{"reason":status}); self.reply(401 if status=="unauthorized" else 410,{"error":status}); return False
        return True
    def do_POST(self):
        route=urlparse(self.path).path
        try:
            if route=="/pair/request":
                b=self.body(); rid=self.host.request_pair(str(b.get("invitation_id","")),str(b.get("invitation_secret","")),str(b.get("label","agent"))); self.reply(202,{"status":"pending","request_id":rid}); return
            if route=="/pair/status":
                b=self.body(); self.reply(200,self.host.pair_result(str(b.get("request_id","")),str(b.get("invitation_secret","")))); return
            if route=="/files/create":
                if not self.auth():return
                b=self.body(); rel=b.get("path"); content=b.get("content")
                if not isinstance(content,str) or len(content.encode())>MAX_TEXT_BYTES:raise ValueError("content must be text up to 2 MB")
                path=self.host.safe_path(rel,True); self.host.audit("file_create",rel,"allowed",{"phase":"attempt"})
                with path.open("x",encoding="utf-8",newline="") as f:f.write(content);f.flush();os.fsync(f.fileno())
                self.host.audit("file_create",rel,"allowed",{"phase":"complete","bytes":len(content.encode())}); self.reply(201,{"ok":True,"path":rel}); return
            self.host.audit("api_request",route,"denied",{"reason":"unknown route"}); self.reply(404,{"error":"not found"})
        except PermissionError as e:self.reply(403,{"error":str(e)})
        except FileExistsError:
            self.host.audit("file_create","existing file","denied",{"reason":"exists"}); self.reply(409,{"error":"file already exists; overwrite forbidden"})
        except (ValueError,FileNotFoundError,IsADirectoryError,NotADirectoryError,UnicodeError,json.JSONDecodeError) as e:
            self.host.audit("api_request",route,"denied",{"reason":str(e)}); self.reply(400,{"error":str(e)})
        except OSError:self.reply(503,{"error":"host state or filesystem operation failed"})
    def do_GET(self):
        route=urlparse(self.path).path
        if route=="/health":self.reply(200,{"ok":True,"paired":self.host.session_deadline is not None});return
        if not self.auth():return
        rel=parse_qs(urlparse(self.path).query).get("path",["."])[0]
        try:
            path=self.host.safe_path(rel)
            if route=="/files/list":
                if not path.is_dir():raise ValueError("not a directory")
                items=[]
                for item in sorted(path.iterdir(),key=lambda p:p.name.casefold()):
                    if is_link(item):continue
                    items.append({"name":item.name,"type":"dir" if item.is_dir() else "file","size":item.stat().st_size if item.is_file() else None})
                result={"path":rel,"items":items}
            elif route=="/files/read":
                if not path.is_file():raise ValueError("not a regular file")
                if path.stat().st_size>MAX_TEXT_BYTES:raise ValueError("file exceeds 2 MB")
                result={"path":rel,"content":path.read_text(encoding="utf-8")}
            else:self.host.audit("api_request",route,"denied",{"reason":"unknown route"});self.reply(404,{"error":"not found"});return
            self.host.audit("api_request",route,"allowed",{"path":rel});self.reply(200,result)
        except (ValueError,FileNotFoundError,IsADirectoryError,NotADirectoryError,UnicodeError) as e:self.host.audit("api_request",route,"denied",{"reason":str(e)});self.reply(400,{"error":str(e)})
        except OSError:self.reply(503,{"error":"host state or filesystem operation failed"})

def owner_console(host):
    print("Owner commands: approve REQUEST_ID | deny REQUEST_ID | revoke | freeze | status",flush=True)
    while not host.stopping:
        try:line=input("molt-owner> ").strip()
        except EOFError:return
        try:
            cmd,_,arg=line.partition(" ")
            if cmd=="approve":host.approve(arg);print("Approved. Agent may retrieve one session token.",flush=True)
            elif cmd=="deny":host.deny(arg);print("Denied.",flush=True)
            elif cmd=="revoke":host.revoke();print("Revoked.",flush=True)
            elif cmd=="freeze":host.frozen=True;host.audit("freeze","session","allowed");print("Frozen.",flush=True)
            elif cmd=="status":print(json.dumps({k:v["status"] for k,v in host.pending.items()}),flush=True)
            elif cmd:print("Unknown owner command.",flush=True)
        except (ValueError,OSError) as e:print("Owner action failed: "+str(e),flush=True)

def owner_file_console(host,path):
    """Consume atomically-published, host-local acceptance-test commands."""
    path=validate_owner_cmd_path(host,path)
    print("Owner command file: %s (polling)"%path,flush=True)
    while not host.stopping:
        try:
            consume_owner_cmd_file(host,path)
        except (OSError,ValueError,PermissionError,UnicodeError) as e:
            print("Owner command file rejected: "+str(e),file=sys.stderr,flush=True)
        time.sleep(0.5)

def validate_owner_cmd_path(host,path):
    """Limit the automation inbox to one direct child of the private state dir."""
    raw=Path(path).expanduser()
    if not raw.is_absolute(): raw=Path.cwd()/raw
    if ".." in raw.parts or raw.name in ("",".","..") or raw.parent.resolve(strict=True)!=host.state_dir:
        raise ValueError("owner command file must be a direct child of state-dir")
    if is_link(raw.parent) or (raw.exists() and is_link(raw)):
        raise ValueError("owner command path must not use a link/reparse point")
    if raw==host.audit_path: raise ValueError("owner command file must not be the audit file")
    return raw

def consume_owner_cmd_file(host,path):
    """Claim one complete file by rename, verify it, execute it, then remove it."""
    path=validate_owner_cmd_path(host,path)
    try: before=os.lstat(path)
    except FileNotFoundError:return False
    if is_link(path): raise ValueError("owner command path is a link/reparse point")
    _check_private_regular_file(path,before)
    if before.st_size>MAX_OWNER_COMMAND_BYTES: raise ValueError("owner command file is too large")
    claimed=host.state_dir/(".owner-cmd-"+secrets.token_hex(12)+".claimed")
    os.replace(path,claimed)
    try:
        after=os.lstat(claimed)
        if (before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino):
            raise OSError("owner command file identity changed during claim")
        _check_private_regular_file(claimed,after)
        fd=os.open(str(claimed),os.O_RDONLY|_secure_open_flags())
        try:
            opened=os.fstat(fd)
            if (after.st_dev,after.st_ino)!=(opened.st_dev,opened.st_ino): raise OSError("owner command identity mismatch")
            data=os.read(fd,MAX_OWNER_COMMAND_BYTES+1)
        finally:os.close(fd)
        if len(data)>MAX_OWNER_COMMAND_BYTES: raise ValueError("owner command file is too large")
        if not data.endswith(b"\n"): raise ValueError("owner command file is incomplete (final newline required)")
        text=data.decode("utf-8")
        lines=[line.strip() for line in text.splitlines() if line.strip()]
        if len(lines)!=1: raise ValueError("exactly one owner command is required per file")
        _run_owner_line(host,lines[0]); return True
    finally:
        try:claimed.unlink()
        except FileNotFoundError:pass

def _run_owner_line(host,line):
    """Execute one owner command line; returns True when it should be removed."""
    parts=line.split()
    if not parts:raise ValueError("empty owner command")
    cmd=parts[0]; arg=parts[1] if len(parts)==2 else ""
    if (cmd in ("approve","deny") and len(parts)!=2) or (cmd in ("revoke","freeze","status") and len(parts)!=1):
        raise ValueError("invalid owner command arguments")
    try:
        if cmd=="approve":host.approve(arg);print("Approved %s. Agent may retrieve one session token."%arg,flush=True);return True
        if cmd=="deny":host.deny(arg);print("Denied %s."%arg,flush=True);return True
        if cmd=="revoke":host.revoke();print("Revoked.",flush=True);return True
        if cmd=="freeze":host.frozen=True;host.audit("freeze","session","allowed");print("Frozen.",flush=True);return True
        if cmd=="status":print(json.dumps({k:v["status"] for k,v in host.pending.items()}),flush=True);return True
        raise ValueError("unknown owner command")
    except (ValueError,OSError) as e:
        print("Owner action failed: "+str(e),flush=True)
    return True

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",required=True);ap.add_argument("--create-root",action="store_true");ap.add_argument("--state-dir",required=True);ap.add_argument("--port",type=int,default=8765);ap.add_argument("--invite-ttl",type=float,default=10);ap.add_argument("--session-ttl",type=float,default=60);ap.add_argument("--owner-cmd-file",default=None);a=ap.parse_args()
    host=HostState(a.root,a.state_dir,a.invite_ttl,a.session_ttl,a.create_root);host.server=ThreadingHTTPServer(("127.0.0.1",a.port),Handler);host.server.host=host
    print("MOLT_URL=http://127.0.0.1:%d"%host.server.server_port,flush=True);print("MOLT_INVITATION_ID="+host.invite_id,flush=True);print("MOLT_INVITATION_SECRET="+host.invite_secret,flush=True);print("Invitation expires in %g minutes and is single-use."%a.invite_ttl,flush=True)
    if a.owner_cmd_file:
        threading.Thread(target=owner_file_console,args=(host,a.owner_cmd_file),daemon=True).start()
    threading.Thread(target=owner_console,args=(host,),daemon=True).start();signal.signal(signal.SIGINT,lambda *_:host.stop());signal.signal(signal.SIGTERM,lambda *_:host.stop())
    try:host.server.serve_forever()
    finally:host.stop();host.server.server_close()
if __name__=="__main__":main()
