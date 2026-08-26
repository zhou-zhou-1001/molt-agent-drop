import json, os, tempfile, threading, time, unittest, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from drop_host import Handler, HostState, consume_owner_cmd_file, validate_owner_cmd_path, validate_root

class DropTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name);self.root=base/"shared";self.root.mkdir();self.state=base/"private";(self.root/"hello.txt").write_text("hello",encoding="utf-8")
        self.host=HostState(self.root,self.state,1,1);self.server=None;self.base=None
        try:self.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        except PermissionError:return
        self.server.host=self.host;self.host.server=self.server
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base="http://127.0.0.1:%d"%self.server.server_port
    def tearDown(self):
        if self.server:self.server.shutdown();self.server.server_close()
        self.tmp.cleanup()
    def call(self,method,path,body=None,token=None):
        if not self.base:self.skipTest("sandbox forbids loopback bind; run outside restricted sandbox for HTTP integration")
        data=None if body is None else json.dumps(body).encode();headers={"Content-Type":"application/json"}
        if token:headers["Authorization"]="Bearer "+token
        req=urllib.request.Request(self.base+path,data=data,method=method,headers=headers)
        with urllib.request.urlopen(req,timeout=3) as response:return response.status,json.load(response)
    def error(self,code,method,path,body=None,token=None):
        with self.assertRaises(urllib.error.HTTPError) as cm:self.call(method,path,body,token)
        self.assertEqual(code,cm.exception.code);cm.exception.close()
    def pair(self):
        _,value=self.call("POST","/pair/request",{"invitation_id":self.host.invite_id,"invitation_secret":self.host.invite_secret,"label":"test"});rid=value["request_id"]
        self.error(410,"GET","/files/read?path=hello.txt",token="not-yet")
        self.host.approve(rid);_,value=self.call("POST","/pair/status",{"request_id":rid,"invitation_secret":self.host.invite_secret});return value["token"]
    def test_pair_approval_and_single_use(self):
        _,request=self.call("POST","/pair/request",{"invitation_id":self.host.invite_id,"invitation_secret":self.host.invite_secret,"label":"test"});rid=request["request_id"]
        self.error(403,"POST","/pair/request",{"invitation_id":self.host.invite_id,"invitation_secret":self.host.invite_secret})
        self.host.approve(rid);_,first=self.call("POST","/pair/status",{"request_id":rid,"invitation_secret":self.host.invite_secret});token=first["token"]
        _,second=self.call("POST","/pair/status",{"request_id":rid,"invitation_secret":self.host.invite_secret});self.assertEqual({"status":"delivered"},second)
        self.assertEqual("hello",self.call("GET","/files/read?path=hello.txt",token=token)[1]["content"])
        text=self.host.audit_path.read_text();self.assertNotIn(token,text);self.assertNotIn(self.host.invite_secret,text)
    def test_expired_invitation_is_rejected(self):
        self.host.invite_deadline=time.monotonic()-1
        with self.assertRaises(PermissionError):self.host.request_pair(self.host.invite_id,self.host.invite_secret,"test")
    def test_structured_files_no_escape_or_overwrite(self):
        token=self.pair();self.assertEqual(200,self.call("GET","/files/list?path=.",token=token)[0])
        self.assertEqual(201,self.call("POST","/files/create",{"path":"new.txt","content":"new"},token)[0]);self.assertEqual("new",(self.root/"new.txt").read_text())
        self.error(409,"POST","/files/create",{"path":"hello.txt","content":"overwrite"},token);self.assertEqual("hello",(self.root/"hello.txt").read_text())
        for bad in ("../outside","/etc/passwd","C:/Windows/x","a\\b"):
            self.error(400,"GET","/files/read?path="+urllib.parse.quote(bad),token=token)
        self.error(404,"POST","/command",{"name":"anything"},token)
    def test_revoke_and_audit_fail_closed_create(self):
        token=self.pair();original=self.host.audit
        def broken(event,*args,**kwargs):
            if event=="file_create":raise OSError("audit unavailable")
            return original(event,*args,**kwargs)
        self.host.audit=broken;self.error(503,"POST","/files/create",{"path":"blocked.txt","content":"x"},token);self.assertFalse((self.root/"blocked.txt").exists())
        self.host.audit=original;self.host.revoke();self.error(410,"GET","/files/list?path=.",token=token)
    def test_state_outside_and_dangerous_roots(self):
        self.assertFalse((self.root/"audit.jsonl").exists())
        with self.assertRaises(ValueError):validate_root(Path.home())
    def test_owner_command_file_atomic_single_command_and_permissions(self):
        rid=self.host.request_pair(self.host.invite_id,self.host.invite_secret,"test")
        inbox=self.state/"owner_cmd.txt";partial=self.state/"publish.tmp"
        partial.write_text("approve "+rid,encoding="utf-8");os.chmod(partial,0o600);os.replace(partial,inbox)
        with self.assertRaises(ValueError):consume_owner_cmd_file(self.host,inbox)
        self.assertEqual("pending",self.host.pending[rid]["status"]);self.assertFalse(inbox.exists())
        partial.write_text("approve "+rid+"\n",encoding="utf-8");os.chmod(partial,0o600);os.replace(partial,inbox)
        self.assertTrue(consume_owner_cmd_file(self.host,inbox));self.assertEqual("approved",self.host.pending[rid]["status"]);self.assertFalse(inbox.exists())
    def test_owner_command_rejects_escape_link_and_broad_mode(self):
        outside=Path(self.tmp.name)/"outside.txt"
        with self.assertRaises(ValueError):validate_owner_cmd_path(self.host,outside)
        with self.assertRaises(ValueError):validate_owner_cmd_path(self.host,self.state/"sub"/".."/"owner_cmd.txt")
        inbox=self.state/"owner_cmd.txt";target=self.state/"target.txt";target.write_text("status\n")
        try:inbox.symlink_to(target)
        except (OSError,NotImplementedError):self.skipTest("symlinks unavailable")
        with self.assertRaises(ValueError):consume_owner_cmd_file(self.host,inbox)
        inbox.unlink();target.replace(inbox)
        if os.name!="nt":
            os.chmod(inbox,0o644)
            with self.assertRaises(PermissionError):consume_owner_cmd_file(self.host,inbox)
    def test_direct_invitation_token_and_revoke_state(self):
        rid=self.host.request_pair(self.host.invite_id,self.host.invite_secret,"test")
        with self.assertRaises(PermissionError):self.host.request_pair(self.host.invite_id,self.host.invite_secret,"again")
        self.host.approve(rid);first=self.host.pair_result(rid,self.host.invite_secret);token=first["token"]
        self.assertEqual({"status":"delivered"},self.host.pair_result(rid,self.host.invite_secret))
        self.assertEqual("active",self.host.session_status(token));self.host.revoke();self.assertEqual("revoked",self.host.session_status(token))

if __name__=="__main__":unittest.main(verbosity=2)
