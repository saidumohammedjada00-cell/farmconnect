"""Tiny fake clamd server so the real INSTREAM client code can be tested without ClamAV."""
import socket
import struct
import threading

# The standard EICAR antivirus test string, split so this file is not flagged by scanners.
EICAR = (b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!" + b"$H+H*")


class FakeClamd:
    def __init__(self, reply: bytes | None = None):
        self.reply, self.received = reply, b""
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _read(self, conn, n):
        buf = b""
        while len(buf) < n:
            part = conn.recv(n - len(buf))
            if not part:
                break
            buf += part
        return buf

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                if self._read(conn, 10) != b"zINSTREAM\0":
                    continue
                data = b""
                while True:
                    size = struct.unpack("!I", self._read(conn, 4))[0]
                    if size == 0:
                        break
                    data += self._read(conn, size)
                self.received = data
                if self.reply is not None:
                    conn.sendall(self.reply)
                elif EICAR in data:
                    conn.sendall(b"stream: Eicar-Test-Signature FOUND\0")
                else:
                    conn.sendall(b"stream: OK\0")

    def close(self):
        self.sock.close()
