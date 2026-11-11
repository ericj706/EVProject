import http.server
import socketserver
import webbrowser
import threading
import sys
import os

# Set working directory to the folder containing this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Find an available port automatically to prevent "Port already in use" errors
import socket

def get_available_port(default_port=8000):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", default_port))
            return default_port
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

PORT = get_available_port(8000)

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def start_server():
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
            print(f"서버가 포트 {PORT}에서 성공적으로 실행되었습니다.")
            url = f"http://localhost:{PORT}/dashboard/index.html"
            print(f"브라우저를 엽니다: {url}")
            webbrowser.open(url)
            httpd.serve_forever()
    except OSError as e:
        print(f"\\n[오류] 사용할 수 있는 서버 포트({PORT})가 이미 사용중입니다!")
        print("잠시 후 창을 닫고 다시 실행하시거나 열려있는 다른 서버 검은 창을 닫아주세요.\\n")
        sys.exit(1)

if __name__ == '__main__':
    try:
        start_server()
    except KeyboardInterrupt:
        sys.exit(0)
