import json, os, subprocess, tempfile, threading, time, unittest, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from drop_host import Handler, HostState, consume_owner_cmd_file, validate_owner_cmd_path, validate_root
import drop_host as drop_host_module

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
    def test_owner_can_create_fresh_single_use_invitation(self):
        old_id,old_secret=self.host.invite_id,self.host.invite_secret
        rid=self.host.request_pair(old_id,old_secret,"old")
        self.host.invite_deadline=time.monotonic()-1
        new_id,new_secret=self.host.new_invite()
        self.assertNotEqual((old_id,old_secret),(new_id,new_secret));self.assertFalse(self.host.invite_consumed)
        self.assertGreater(self.host.invite_deadline,time.monotonic());self.assertEqual("superseded",self.host.pending[rid]["status"])
        with self.assertRaises(PermissionError):self.host.request_pair(old_id,old_secret,"old")
        new_rid=self.host.request_pair(new_id,new_secret,"new")
        with self.assertRaises(PermissionError):self.host.request_pair(new_id,new_secret,"again")
        self.host.approve(new_rid)
        audit=self.host.audit_path.read_text();self.assertIn('"event":"invitation_create"',audit);self.assertNotIn(new_secret,audit)
    def test_new_invitation_fails_closed_when_audit_fails(self):
        before=(self.host.invite_id,self.host.invite_secret,self.host.invite_deadline,self.host.invite_consumed)
        self.host.audit=lambda *args,**kwargs: (_ for _ in ()).throw(OSError("audit unavailable"))
        with self.assertRaises(OSError):self.host.new_invite()
        self.assertEqual(before,(self.host.invite_id,self.host.invite_secret,self.host.invite_deadline,self.host.invite_consumed))
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
        old_id=self.host.invite_id;partial.write_text("new-invite\n",encoding="utf-8");os.chmod(partial,0o600);os.replace(partial,inbox)
        self.assertTrue(consume_owner_cmd_file(self.host,inbox));self.assertNotEqual(old_id,self.host.invite_id);self.assertFalse(self.host.invite_consumed)
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

class DropDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name)
        self.root=base/"shared";self.root.mkdir();self.state=base/"private"
        self.host=HostState(self.root,self.state,1,1,enable_diagnostics=True);self.token=None
    def tearDown(self):
        self.host.revoke()
        self.tmp.cleanup()
    def _pair(self):
        rid=self.host.request_pair(self.host.invite_id,self.host.invite_secret,"diag-test")
        self.host.approve(rid);self.token=self.host.pair_result(rid,self.host.invite_secret)["token"]
    def _wait_terminal(self,rid,limit=8):
        deadline=time.monotonic()+limit;status=None
        while time.monotonic()<deadline:
            status=self.host.diagnostic_result(rid,self.token)["status"]
            if status in ("completed","failed","blocked","denied"):break
            time.sleep(0.05)
        return status
    def test_diagnostics_disabled_by_default(self):
        host=HostState(self.root,self.state,1,1)
        with self.assertRaises(PermissionError):host.request_diagnostic("system.identity",{},"x")
    def test_request_requires_active_session(self):
        with self.assertRaises(PermissionError):self.host.request_diagnostic("system.identity",{},"bogus")
    def test_request_rejects_unknown_command_or_args(self):
        self._pair()
        with self.assertRaises(ValueError):self.host.request_diagnostic("not-a-command",{},self.token)
        with self.assertRaises(ValueError):self.host.request_diagnostic("system.identity",{"x":1},self.token)
    def test_approve_runs_and_completes(self):
        self._pair();rid=self.host.request_diagnostic("system.identity",{},self.token)
        self.host.approve_diagnostic(rid);self.assertEqual("completed",self._wait_terminal(rid))
        result=self.host.diagnostic_result(rid,self.token)["result"]
        self.assertEqual(0,result["exit_code"]);self.assertTrue(result["output"].strip())
    def test_deny_stays_denied(self):
        self._pair();rid=self.host.request_diagnostic("system.identity",{},self.token)
        self.host.deny_diagnostic(rid)
        self.assertEqual("denied",self.host.diagnostic_result(rid,self.token)["status"])
    def test_approve_after_revoke_or_freeze_fails_closed(self):
        self._pair();rid=self.host.request_diagnostic("system.identity",{},self.token)
        self.host.revoke()
        with self.assertRaises(ValueError):self.host.approve_diagnostic(rid)
    def test_approve_after_freeze_fails_closed(self):
        self._pair();rid=self.host.request_diagnostic("system.identity",{},self.token)
        self.host.freeze()
        with self.assertRaises(ValueError):self.host.approve_diagnostic(rid)
    def test_session_binding_tamper_fails_closed(self):
        self._pair();rid=self.host.request_diagnostic("system.identity",{},self.token)
        self.host.diagnostic_requests[rid]["session_hash"]="tampered"
        with self.assertRaises(ValueError):self.host.approve_diagnostic(rid)
    def test_timeout_kills_process_tree(self):
        old=drop_host_module.DIAGNOSTIC_TIMEOUT_SECONDS
        drop_host_module.DIAGNOSTIC_TIMEOUT_SECONDS=1
        try:result=drop_host_module._run_fixed_diagnostic(("/bin/sleep","5"),self.state)
        finally:drop_host_module.DIAGNOSTIC_TIMEOUT_SECONDS=old
        self.assertTrue(result["timed_out"])
    def test_redaction_removes_secrets(self):
        self.assertIn("[REDACTED]",drop_host_module._redact_diagnostic_text("apiKey=sk-abcdefghijklmnopqrstuvwxyz0123456789"))
        self.assertIn("[REDACTED]",drop_host_module._redact_diagnostic_text("Authorization: Bearer deadbeef"))
        self.assertIn("[REDACTED]",drop_host_module._redact_diagnostic_text("prefix xyzabcdefghijklmnopqrstuvwxyz0123456789 suffix"))
    def test_terminate_diagnostic_process(self):
        proc=subprocess.Popen(("/bin/sleep","30"),start_new_session=True)
        drop_host_module._terminate_diagnostic_process(proc)
        self.assertIsNotNone(proc.wait(timeout=5))

if __name__=="__main__":unittest.main(verbosity=2)
