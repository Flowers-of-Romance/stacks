"""Embedding server — keeps model in memory for fast repeated queries."""
import json
import sys
import io
from http.server import HTTPServer, BaseHTTPRequestHandler

DEFAULT_PORT = 7823


class EmbedHandler(BaseHTTPRequestHandler):
    model = None

    def do_POST(self):
        if self.path == "/embed":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            text = body.get("text", "")
            texts = body.get("texts", [])

            if texts:
                embeddings = self._embed_texts(texts)
                self._respond(200, {"embeddings": embeddings})
            elif text:
                embedding = self._embed_text(text)
                self._respond(200, {"embedding": embedding})
            else:
                self._respond(400, {"error": "provide 'text' or 'texts'"})
        else:
            self._respond(404, {"error": "not found"})

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok"})
        else:
            self._respond(404, {"error": "not found"})

    def _embed_text(self, text):
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def _embed_texts(self, texts):
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return [e.tolist() for e in embeddings]

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        # Suppress request logging
        pass


def start_server(port=DEFAULT_PORT):
    """Start the embedding server."""
    from stacks.embedder import get_model

    # Load model (suppress stderr noise)
    original_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        model = get_model()
    finally:
        sys.stderr = original_stderr

    EmbedHandler.model = model

    server = HTTPServer(("127.0.0.1", port), EmbedHandler)
    print(f"Embedding server running on http://127.0.0.1:{port}")
    print("Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()
