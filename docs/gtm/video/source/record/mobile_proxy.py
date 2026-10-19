import http.server, urllib.request, sys, os
ROOT=sys.argv[1]; UP="https://procurepilot.iron-sys.com"
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s,*a,**k): super().__init__(*a,directory=ROOT,**k)
    def _proxy(s):
        n=int(s.headers.get('Content-Length') or 0); body=s.rfile.read(n) if n else None
        hdr={k:v for k,v in s.headers.items() if k.lower() not in ('host','origin','referer','content-length','accept-encoding')}
        req=urllib.request.Request(UP+s.path,data=body,headers=hdr,method=s.command)
        try: r=urllib.request.urlopen(req,timeout=60); code=r.status; data=r.read(); rh=r.headers
        except urllib.error.HTTPError as e: code=e.code; data=e.read(); rh=e.headers
        s.send_response(code)
        for k,v in rh.items():
            if k.lower() not in ('transfer-encoding','connection','content-length','content-encoding','access-control-allow-origin'): s.send_header(k,v)
        s.send_header('Content-Length',str(len(data))); s.end_headers(); s.wfile.write(data)
    def do_GET(s):
        if s.path.startswith('/api/'): return s._proxy()
        p=s.translate_path(s.path)
        if not os.path.exists(p) or (os.path.isdir(p) and not os.path.exists(os.path.join(p,'index.html'))): s.path='/index.html'
        return super().do_GET()
    def do_POST(s): s._proxy()
    def do_PUT(s): s._proxy()
    def do_PATCH(s): s._proxy()
    def do_DELETE(s): s._proxy()
    def log_message(s,*a): pass
http.server.ThreadingHTTPServer(('127.0.0.1',4310),H).serve_forever()
