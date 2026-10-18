import itertools
import json
import logging
import os
import queue
import shutil
import socket
import subprocess
import tempfile
import threading
import time

log = logging.getLogger("aiostreamer.mpv_ipc")

CONNECT_TIMEOUT = 15.0
REPLY_TIMEOUT = 10.0


class MpvError(Exception):
    pass


def command_line(executable, socket_path, options):
    args = [executable, "--input-ipc-server=%s" % socket_path]
    for key, value in options.items():
        if value is True:
            value = "yes"
        elif value is False:
            value = "no"
        args.append("--%s=%s" % (key, value))
    return args


class MpvIpc:
    def __init__(self, options, on_exit=None, executable="mpv"):
        self._options = options
        self._on_exit = on_exit
        self._executable = executable
        self._dir = None
        self._proc = None
        self._sock = None
        self._send_lock = threading.Lock()
        self._ids = itertools.count(1)
        self._pending = {}
        self._events = {}
        self._observers = {}
        self._dispatch = queue.Queue()
        self._closed = threading.Event()

    def start(self):
        self._dir = tempfile.mkdtemp(prefix="aios-mpv-")
        path = os.path.join(self._dir, "ipc.sock")
        self._proc = subprocess.Popen(command_line(self._executable, path, self._options), stdin=subprocess.DEVNULL)
        self._sock = self._connect(path)
        threading.Thread(target=self._read, name="aios-mpv-read", daemon=True).start()
        threading.Thread(target=self._deliver, name="aios-mpv-events", daemon=True).start()

    def _connect(self, path):
        deadline = time.monotonic() + CONNECT_TIMEOUT
        while True:
            if self._proc.poll() is not None:
                self._cleanup()
                raise MpvError("mpv exited with code %s" % self._proc.returncode)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(path)
                return sock
            except OSError:
                sock.close()
                if time.monotonic() > deadline:
                    self.terminate()
                    raise MpvError("mpv IPC socket did not appear")
                time.sleep(0.05)

    def bind_event(self, name, callback):
        self._events.setdefault(name, []).append(callback)

    def observe(self, name, callback):
        observer_id = next(self._ids)
        self._observers[observer_id] = (name, callback)
        self.command("observe_property", observer_id, name)

    def command(self, *args):
        if self._sock is None or self._closed.is_set():
            raise MpvError("mpv is not running")
        request_id = next(self._ids)
        slot = {"done": threading.Event()}
        self._pending[request_id] = slot
        line = json.dumps({"command": list(args), "request_id": request_id}).encode() + b"\n"
        try:
            with self._send_lock:
                self._sock.sendall(line)
            if not slot["done"].wait(REPLY_TIMEOUT):
                raise MpvError("no reply to %s" % args[0])
        except OSError as exc:
            raise MpvError(str(exc))
        finally:
            self._pending.pop(request_id, None)
        reply = slot.get("reply")
        if reply is None:
            raise MpvError("mpv closed")
        if reply.get("error") != "success":
            raise MpvError("%s: %s" % (args[0], reply.get("error")))
        return reply.get("data")

    def _read(self):
        buffer = b""
        try:
            while True:
                chunk = self._sock.recv(65536)
                if not chunk:
                    break
                buffer += chunk
                *lines, buffer = buffer.split(b"\n")
                for line in lines:
                    if line.strip():
                        self._handle(line)
        except OSError:
            pass
        self._sock.close()
        self._finish()

    def _handle(self, line):
        try:
            message = json.loads(line)
        except ValueError:
            log.debug("bad mpv message: %r", line)
            return
        if "request_id" in message and "event" not in message:
            slot = self._pending.get(message["request_id"])
            if slot is not None:
                slot["reply"] = message
                slot["done"].set()
            return
        event = message.get("event")
        if event == "property-change":
            observer = self._observers.get(message.get("id"))
            if observer:
                name, callback = observer
                self._dispatch.put((callback, (name, message.get("data"))))
        elif event:
            for callback in self._events.get(event, []):
                self._dispatch.put((callback, (message,)))

    def _deliver(self):
        while True:
            entry = self._dispatch.get()
            if entry is None:
                break
            callback, args = entry
            try:
                callback(*args)
            except Exception:
                log.exception("mpv callback failed")

    def _finish(self):
        if self._closed.is_set():
            return
        self._closed.set()
        for slot in list(self._pending.values()):
            slot["done"].set()
        if self._on_exit:
            self._dispatch.put((self._on_exit, ()))
        self._dispatch.put(None)
        if self._proc is not None:
            try:
                self._proc.wait(5)
            except subprocess.TimeoutExpired:
                pass
        self._cleanup()

    def _cleanup(self):
        if self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None

    def terminate(self):
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._cleanup()
