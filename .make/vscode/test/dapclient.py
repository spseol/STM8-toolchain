"""Minimal Debug Adapter Protocol client over a child process's stdio (stdlib only)."""

import json
import os
import subprocess
import threading
import time


class DapClient:
    """Starts ARGV and talks DAP with it.

    request() returns the whole response message (check ["success"]); wait_event() takes
    the first unread event of that name. `events` keeps every event seen, `junk` keeps text
    the child printed outside DAP framing, `stderr` its standard error.
    """

    def __init__(self, argv, env=None, cwd=None):
        self.proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env if env is not None else os.environ.copy(), cwd=cwd,
        )
        self.events = []
        self.junk = []
        self.stderr = []
        self._unread = []
        self._responses = {}
        self._seq = 0
        self._cond = threading.Condition()
        self.closed = False
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self):
        out = self.proc.stdout
        while True:
            length = None
            while True:  # headers, tolerating stray lines before them
                line = out.readline()
                if not line:
                    with self._cond:
                        self.closed = True
                        self._cond.notify_all()
                    return
                text = line.decode("utf-8", "replace").rstrip("\r\n")
                if text.lower().startswith("content-length:"):
                    length = int(text.split(":", 1)[1])
                elif text == "" and length is not None:
                    break
                elif text != "":
                    self.junk.append(text)
            body = out.read(length)
            msg = json.loads(body.decode("utf-8"))
            with self._cond:
                if msg.get("type") == "response":
                    self._responses[msg["request_seq"]] = msg
                else:
                    self.events.append(msg)
                    self._unread.append(msg)
                self._cond.notify_all()

    def _read_stderr(self):
        for line in self.proc.stderr:
            self.stderr.append(line.decode("utf-8", "replace").rstrip())

    def send(self, message):
        body = json.dumps(message).encode("utf-8")
        self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        self.proc.stdin.flush()

    def request(self, command, arguments=None, timeout=20):
        self._seq += 1
        seq = self._seq
        message = {"seq": seq, "type": "request", "command": command}
        if arguments is not None:
            message["arguments"] = arguments
        self.send(message)
        deadline = time.monotonic() + timeout
        with self._cond:
            while seq not in self._responses:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(f"no response to {command} in {timeout} s")
                if self.closed:
                    raise ConnectionError(f"adapter exited before answering {command}")
                self._cond.wait(left)
            return self._responses.pop(seq)

    def wait_event(self, name, timeout=20):
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                for i, event in enumerate(self._unread):
                    if event.get("event") == name:
                        return self._unread.pop(i)
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(f"no {name} event in {timeout} s")
                if self.closed:
                    raise ConnectionError(f"adapter exited before {name} event")
                self._cond.wait(left)

    def output_text(self):
        """All text of `output` events seen so far."""
        return "".join(e["body"].get("output", "") for e in self.events if e.get("event") == "output")

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


def repl(client, expression, timeout=30):
    """`evaluate` in the repl context; returns the whole response."""
    return client.request("evaluate", {"expression": expression, "context": "repl"}, timeout=timeout)


def top_frame(client, thread_id):
    frames = client.request("stackTrace", {"threadId": thread_id})["body"]["stackFrames"]
    return frames[0] if frames else None
