#!/usr/bin/env python3
"""Flea send-target plugin for Android Quick Share, backed by the quickshare CLI.

Flea gives a request 30 seconds and stops idle plugins, while a Quick Share send waits for
someone to tap Accept and then copies the file. So `send` hands the transfer to a detached
process that runs `quickshare send` and announces the result, the way omarchy-tailscale-send
does for Taildrop, and answers Flea at once.

Receiving outlives every plugin session too, so a detached `--receive` process owns it from
start to end. Plugin sessions only start that process; it stops itself by watching the saved
settings.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import platform
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

PLUGIN_ID = "quickshare.send"

BROWSE_SECONDS = "2"

# The quickshare release this plugin version runs. Updating the plugin moves both together.
CLI_VERSION = "0.3.0"
CLI_SHA256 = {
    "x86_64": "f180aa7ea34a9518727be1c3f849c627ecabb30edd7be31c2de9ab2697a26d5a",
    "aarch64": "d97b79b96f0699cc8f78dfee5890fa6f3a2a65bccae8cfdcd65e7486d5158a05",
}
CLI_URL = "https://github.com/JaxonWright/quickshare/releases/download/v{version}/quickshare-{arch}-linux"
BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
GLYPH = "󰄜"

# How long each Receiving choice keeps this computer visible. None means not visible.
VISIBLE_SECONDS = {"off": None, "everyone": 600}
TICK_SECONDS = 2
# quickshare declines a transfer its --ask program has not answered within 60 seconds.
ASK_SECONDS = 55
STOP_SECONDS = 5

# What `quickshare --json send` ends with, and the notification each result becomes.
RESULTS = {
    "delivered": ("Sent to {name}", "normal"),
    "declined": ("{name} declined", "normal"),
    "cancelled": ("{name} cancelled the transfer", "normal"),
    "failed": ("Could not send to {name}", "critical"),
}


class Unavailable(Exception):
    """quickshare could not be found or downloaded; the message is shown as a menu row."""


def download(arch, path):
    url = CLI_URL.format(version=CLI_VERSION, arch=arch)
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            data = response.read(64 * 1024 * 1024)
    except OSError as error:
        raise Unavailable("Could not download quickshare") from error
    if hashlib.sha256(data).hexdigest() != CLI_SHA256[arch]:
        raise Unavailable("Downloaded quickshare failed its checksum")
    os.makedirs(BIN_DIR, exist_ok=True)
    partial = path + ".partial"
    with open(partial, "wb") as file:
        file.write(data)
    os.chmod(partial, 0o755)
    os.replace(partial, path)


def quickshare():
    arch = platform.machine()
    if arch in CLI_SHA256:
        path = os.path.join(BIN_DIR, f"quickshare-{CLI_VERSION}")
        if not os.access(path, os.X_OK):
            download(arch, path)
        return path
    found = shutil.which("quickshare") or os.path.expanduser("~/.local/bin/quickshare")
    if os.access(found, os.X_OK):
        return found
    raise Unavailable(f"No quickshare build for {arch}")


def targets():
    try:
        program = quickshare()
    except Unavailable as problem:
        return [{"id": "unavailable", "label": str(problem), "state": "unavailable"}]
    try:
        run = subprocess.run([program, "--json", "browse", "--timeout", BROWSE_SECONDS],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows, seen = [], set()
    for line in run.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        name = event.get("name")
        if event.get("t") == "device" and isinstance(name, str) and name and name not in seen:
            seen.add(name)
            rows.append({"id": name, "label": name, "state": "ready"})
    return rows


def send(target, paths):
    if not isinstance(target, str) or not target:
        raise ValueError("Choose a device to send to.")
    if not paths or len(paths) > 512 or not all(isinstance(p, str) and os.path.isabs(p) for p in paths):
        raise ValueError("Select at least one file.")
    if any(os.path.isdir(p) for p in paths):
        raise ValueError("Quick Share sends files, not folders.")
    try:
        quickshare()
    except Unavailable as problem:
        raise ValueError(f"{problem}.") from problem
    detach([sys.executable, os.path.abspath(__file__), "--deliver", target, *paths])
    return f"Sending to {target}. Accept on the device."


def notify(title, body, urgency, show=None):
    """`show` is a file the notification offers to reveal in Flea."""
    if shutil.which("omarchy-notification-send"):
        command = ["omarchy-notification-send", "-g", GLYPH, "--app-name", "Quick Share"]
        if urgency == "critical":
            command += ["-u", "critical"]
        command += [title, body]
        if show:
            command += ["--action", "Show", "flea", "--select", "--with", show]
        subprocess.run(command, check=False)
        return
    command = ["notify-send", "-a", "Quick Share", "-u", urgency]
    if not show:
        subprocess.run([*command, "--", title, body], check=False)
        return
    # notify-send waits until the notification closes to report the chosen action.
    threading.Thread(target=offer_show, args=([*command, "--action=show=Show", "--", title, body], show),
                     daemon=True).start()


def offer_show(command, path):
    run = subprocess.run(command, capture_output=True, text=True, check=False)
    if run.stdout.strip() == "show":
        detach(["flea", "--select", path])


def detach(command):
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def deliver(target, paths):
    what = os.path.basename(paths[0]) if len(paths) == 1 else f"{len(paths)} files"
    run = subprocess.run([quickshare(), "--json", "send", "--to", target, *paths],
                         capture_output=True, text=True)
    code = "failed"
    for line in run.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("t") == "result" and event.get("code") in RESULTS:
            code = event["code"]
    title, urgency = RESULTS[code]
    reason = run.stderr.strip().splitlines()[-1].removeprefix("quickshare: ") if run.stderr.strip() else ""
    notify(title.format(name=target), reason if code == "failed" and reason else what, urgency)


def receiving(settings):
    """How long to stay visible and the folder to save into, or None when receiving is off.

    The folder is None for quickshare's default, the Downloads folder.
    """
    seconds = VISIBLE_SECONDS.get(settings.get("receiving"))
    if seconds is None:
        return None
    folder = settings.get("folder")
    folder = os.path.expanduser(folder.strip()) if isinstance(folder, str) else ""
    usable = os.path.isabs(folder) and os.path.isdir(folder) and os.access(folder, os.W_OK | os.X_OK)
    return seconds, (folder if usable else None)


def saved_settings():
    """The settings Flea saved for this plugin, {} when it is disabled or removed, or None when
    the file cannot be read right now."""
    state = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    try:
        with open(os.path.join(state, "flea", "ui.json"), encoding="utf-8") as file:
            plugins = json.load(file).get("plugins", {})
    except (OSError, ValueError, AttributeError):
        return None
    entry = plugins.get(PLUGIN_ID) if isinstance(plugins, dict) else None
    if not isinstance(entry, dict) or entry.get("enabled") is not True:
        return {}
    settings = entry.get("settings")
    return settings if isinstance(settings, dict) else {}


def lock_path():
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return os.path.join(runtime, "flea-quickshare-receiver.lock")
    return os.path.join(tempfile.gettempdir(), f"flea-quickshare-receiver-{os.getuid()}.lock")


def take_lock():
    """The open lock file when this process now owns receiving, or None when another does."""
    try:
        lock = open(lock_path(), "a")
    except OSError:
        return None
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return None
    return lock


def start_receiving(settings):
    if not isinstance(settings, dict) or receiving(settings) is None:
        return
    probe = take_lock()
    if probe is None:
        return
    probe.close()
    detach([sys.executable, os.path.abspath(__file__), "--receive"])


def turn_receiving_off():
    """Save Receiving as Off through Flea, so its page shows Off and no session restarts it."""
    request = {"c": "plugins", "op": "set", "id": 1, "plugin": PLUGIN_ID, "key": "receiving", "value": "off"}
    try:
        flea = subprocess.Popen(["flea", "--backend"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return
    timer = threading.Timer(10, flea.kill)
    timer.start()
    # Flea answers only while its input stays open, so wait for the outcome before closing it.
    with contextlib.suppress(OSError, ValueError):
        flea.stdin.write(json.dumps(request) + "\n")
        flea.stdin.flush()
        for line in flea.stdout:
            with contextlib.suppress(ValueError):
                if json.loads(line).get("t") == "pluginop":
                    break
    timer.cancel()
    with contextlib.suppress(OSError):
        flea.stdin.close()
    try:
        flea.wait(STOP_SECONDS)
    except subprocess.TimeoutExpired:
        flea.kill()
        flea.wait()


class Ended(Exception):
    """The session is ending (SIGTERM or SIGHUP)."""


def ended(signum, frame):
    raise Ended


class Receiver:
    """One `quickshare receive` child and what its events mean."""

    def __init__(self, program, folder):
        self.program, self.folder = program, folder
        self.senders = {}
        self.buffer = b""
        self.errors = tempfile.TemporaryFile()
        command = [program, "--json", "receive", "--ask", os.path.abspath(__file__)]
        if folder:
            command[3:3] = ["--dir", folder]
        self.child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                      stderr=self.errors)

    def pump(self, seconds):
        """Handle what quickshare printed within `seconds`. False once it has exited."""
        fd = self.child.stdout.fileno()
        if not select.select([fd], [], [], seconds)[0]:
            return True
        chunk = os.read(fd, 65536)
        if not chunk:
            return False
        *lines, self.buffer = (self.buffer + chunk).split(b"\n")
        for line in lines:
            with contextlib.suppress(ValueError, AttributeError, TypeError):
                self.handle(json.loads(line))
        return True

    def handle(self, event):
        kind, request = event.get("t"), event.get("id")
        if kind == "request":
            self.senders[request] = event.get("from") or "a phone"
        elif kind == "received":
            sender = self.senders.pop(request, "a phone")
            files = [name for name in event.get("files", []) if isinstance(name, str)]
            folder = event.get("dir") or ""
            what = files[0] if len(files) == 1 else f"{len(files)} files"
            first = os.path.join(folder, files[0]) if files else folder
            notify(f"Received from {sender}", what, "normal", first if os.path.exists(first) else folder or None)
        elif kind == "result":
            sender = self.senders.pop(request, "a phone")
            if event.get("code") == "failed":
                notify(f"Could not receive from {sender}", "The transfer failed.", "critical")

    def reason(self):
        self.errors.seek(0)
        lines = self.errors.read().decode(errors="replace").strip().splitlines()
        return lines[-1].removeprefix("quickshare: ") if lines else "quickshare stopped."

    def stop(self):
        if self.child.poll() is None:
            self.child.send_signal(signal.SIGINT)
            try:
                self.child.wait(STOP_SECONDS)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait()
        self.errors.close()


def receive():
    lock = take_lock()
    plan = receiving(saved_settings() or {}) if lock else None
    if plan is None:
        return
    seconds, folder = plan
    deadline = time.monotonic() + seconds
    receiver, turn_off = None, True
    signal.signal(signal.SIGTERM, ended)
    signal.signal(signal.SIGHUP, ended)
    try:
        receiver = Receiver(quickshare(), folder)
        notify("Receiving with Quick Share",
               f"Nearby phones can send files for {seconds // 60} minutes. "
               f"They go to {os.path.basename(folder) if folder else 'Downloads'}.", "normal")
        next_check = 0
        while True:
            if not receiver.pump(TICK_SECONDS):
                notify("Could not receive with Quick Share", receiver.reason(), "critical")
                break
            if time.monotonic() < next_check:
                continue
            next_check = time.monotonic() + TICK_SECONDS
            if time.monotonic() >= deadline:
                notify("Stopped receiving with Quick Share",
                       "Turn Receiving on in Flea's Quick Share settings to receive again.", "normal")
                break
            settings = saved_settings()
            plan = receiving(settings) if settings is not None else (seconds, receiver.folder)
            if plan is None:
                turn_off = False
                break
            if plan[1] != receiver.folder:
                receiver.stop()
                receiver = Receiver(receiver.program, plan[1])
    except (Unavailable, OSError) as problem:
        notify("Could not receive with Quick Share", str(problem), "critical")
    except Ended:
        pass
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        if receiver:
            receiver.stop()
    if turn_off:
        turn_receiving_off()


def ask():
    """Ask whether to accept the transfer quickshare describes in the environment. 0 accepts."""
    files = [name for name in os.environ.get("QUICKSHARE_FILES", "").split("\n") if name]
    what = files[0] if len(files) == 1 else f"{len(files)} files"
    question = f"{os.environ['QUICKSHARE_FROM']} wants to send {what} · PIN {os.environ.get('QUICKSHARE_PIN', '')}"
    try:
        run = subprocess.run(["timeout", str(ASK_SECONDS), "notify-send", "--app-name=Quick Share",
                              f"--expire-time={ASK_SECONDS * 1000}", "--action=accept=Accept",
                              "--action=decline=Decline", "--", "Quick Share", question],
                             stdin=subprocess.DEVNULL, capture_output=True, text=True)
    except OSError:
        return 1
    return 0 if run.stdout.strip() == "accept" else 1


def serve():
    for line in iter(lambda: sys.stdin.buffer.readline(65538), b""):
        if len(line) > 65536:
            break
        try:
            request = json.loads(line)
            op = request.get("op")
            if op == "hello":
                start_receiving(request.get("settings"))
                reply = {"op": "ready", "protocolVersion": 1}
            elif op == "targets":
                reply = {"op": "targets", "targets": targets()}
            elif op == "send":
                reply = {"op": "done", "message": send(request.get("target"), request.get("paths", []))}
            elif op == "settings":
                start_receiving(request.get("settings"))
                reply = {"op": "done"}
            elif op == "cancel":
                break
            else:
                reply = {"op": "error", "message": "Unsupported action."}
        except (ValueError, TypeError) as error:
            reply = {"op": "error", "message": str(error)[:4096]}
        print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    if "QUICKSHARE_FROM" in os.environ:
        sys.exit(ask())
    elif len(sys.argv) > 3 and sys.argv[1] == "--deliver":
        deliver(sys.argv[2], sys.argv[3:])
    elif sys.argv[1:] == ["--receive"]:
        receive()
    else:
        serve()
