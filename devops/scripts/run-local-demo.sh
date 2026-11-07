#!/usr/bin/env bash
# ==============================================================================
# Script: run-local-demo.sh
# Purpose: Start a private, local demonstration environment for the Boutique
#          application running on boutique-dev-eks without public exposure.
# ==============================================================================
set -euo pipefail

NAMESPACE="boutique"
FRONTEND_PORT=3000
GATEWAY_PORT=3001
DEMO_PORT=8080

echo "==> Starting local port-forwards to boutique-dev-eks..."
kubectl port-forward -n "$NAMESPACE" svc/frontend ${FRONTEND_PORT}:3000 >/dev/null 2>&1 &
PID_FE=$!

kubectl port-forward -n "$NAMESPACE" svc/gateway ${GATEWAY_PORT}:3001 >/dev/null 2>&1 &
PID_GW=$!

cleanup() {
  echo ""
  echo "==> Stopping demo and terminating port-forwards..."
  kill "$PID_FE" "$PID_GW" 2>/dev/null || true
  exit 0
}
trap cleanup EXIT INT TERM

# Wait for ports to become available
sleep 2

echo "==> Boutique Application Local Demo is LIVE!"
echo "    Frontend Direct : http://localhost:${FRONTEND_PORT}"
echo "    Gateway Direct  : http://localhost:${GATEWAY_PORT}"
echo "    Unified Website : http://localhost:${DEMO_PORT}"
echo ""
echo "Press Ctrl+C to terminate."

# Lightweight Python reverse proxy uniting frontend static assets and gateway /api routes
python3 -c "
import http.server
import socketserver
import urllib.request
import urllib.error

class DemoProxy(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.proxy_request('GET')
    def do_POST(self):
        self.proxy_request('POST')
    def do_PUT(self):
        self.proxy_request('PUT')
    def do_DELETE(self):
        self.proxy_request('DELETE')
    def do_HEAD(self):
        self.proxy_request('HEAD')

    def proxy_request(self, method):
        if self.path.startswith('/api/'):
            target_url = f'http://127.0.0.1:${GATEWAY_PORT}' + self.path
        else:
            target_url = f'http://127.0.0.1:${FRONTEND_PORT}' + self.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        req = urllib.request.Request(target_url, data=body, method=method)
        for k, v in self.headers.items():
            if k.lower() not in ['host', 'content-length']:
                req.add_header(k, v)

        try:
            with urllib.request.urlopen(req) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for k, v in e.headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())

with socketserver.ThreadingTCPServer(('127.0.0.1', ${DEMO_PORT}), DemoProxy) as httpd:
    httpd.serve_forever()
"
