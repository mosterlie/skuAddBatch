import os
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

class ImageServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        file_path = params.get('path', [None])[0]
        
        if not file_path:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing path parameter")
            return

        file_path = os.path.abspath(urllib.parse.unquote(file_path))
        if os.path.exists(file_path):
            if os.path.isdir(file_path):
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                
                try:
                    files = [f for f in os.listdir(file_path) if os.path.isfile(os.path.join(file_path, f)) and f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))]
                    # Sort files so that the order is deterministic (e.g. 1.jpg, 2.jpg)
                    files.sort()
                    self.wfile.write(json.dumps(files).encode('utf-8'))
                except Exception as e:
                    self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            elif os.path.isfile(file_path):
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                ext = os.path.splitext(file_path)[1].lower()
                content_type = 'image/png' if ext == '.png' else 'image/jpeg'
                self.send_header('Content-Type', content_type)
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"File not found: " + file_path.encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

    def log_message(self, format, *args):
        pass # Suppress standard log output

if __name__ == '__main__':
    port = 31415
    server = HTTPServer(('localhost', port), ImageServerHandler)
    print(f"SKU 本地图片传输服务已在后台运行: http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
