#!/usr/bin/env python3
"""Molt Drop demo pairing and structured-file client."""
import argparse, json, time, urllib.error, urllib.parse, urllib.request

class Client:
    def __init__(self,url,token=None):self.url=url.rstrip("/");self.token=token
    def call(self,method,path,body=None,authenticated=True):
        data=None if body is None else json.dumps(body).encode();headers={"Content-Type":"application/json"}
        if authenticated:
            if not self.token:raise ValueError("--token is required")
            headers["Authorization"]="Bearer "+self.token
        request=urllib.request.Request(self.url+path,data=data,method=method,headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=15) as response:return json.load(response)
        except urllib.error.HTTPError as e:
            try:detail=json.load(e)
            except Exception:detail={"error":str(e)}
            raise SystemExit("Molt request failed (%d): %s"%(e.code,detail.get("error",detail)))

def main():
    p=argparse.ArgumentParser();p.add_argument("--url",required=True);p.add_argument("--token");sub=p.add_subparsers(dest="op",required=True)
    pair=sub.add_parser("pair");pair.add_argument("--invitation-id",required=True);pair.add_argument("--invitation-secret",required=True);pair.add_argument("--label",default="demo-agent");pair.add_argument("--wait",type=int,default=120)
    ls=sub.add_parser("list");ls.add_argument("path",nargs="?",default=".")
    read=sub.add_parser("read");read.add_argument("path")
    create=sub.add_parser("create");create.add_argument("path");create.add_argument("--content",required=True)
    diag=sub.add_parser("diagnostic-request");diag.add_argument("command",choices=("system.identity","openclaw.which","openclaw.version","wsl.status","network.check"))
    ds=sub.add_parser("diagnostic-status");ds.add_argument("request_id")
    a=p.parse_args();c=Client(a.url,a.token)
    if a.op=="pair":
        result=c.call("POST","/pair/request",{"invitation_id":a.invitation_id,"invitation_secret":a.invitation_secret,"label":a.label},False);rid=result["request_id"]
        print("Pair request pending owner approval: "+rid,flush=True);deadline=time.monotonic()+a.wait
        while time.monotonic()<deadline:
            time.sleep(1);result=c.call("POST","/pair/status",{"request_id":rid,"invitation_secret":a.invitation_secret},False)
            if result["status"]=="approved":print("MOLT_SESSION_TOKEN="+result["token"]);print("Copy the complete token above; do not use a visually truncated value.");return
            if result["status"]!="pending":raise SystemExit("Pairing "+result["status"])
        raise SystemExit("Timed out waiting for owner approval")
    if a.op=="diagnostic-request":result=c.call("POST","/diagnostics/request",{"command":a.command,"args":{}})
    elif a.op=="diagnostic-status":result=c.call("POST","/diagnostics/status",{"request_id":a.request_id})
    else:
        query=lambda path:"?"+urllib.parse.urlencode({"path":path})
        if a.op=="list":result=c.call("GET","/files/list"+query(a.path))
        elif a.op=="read":result=c.call("GET","/files/read"+query(a.path))
        else:result=c.call("POST","/files/create",{"path":a.path,"content":a.content})
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
