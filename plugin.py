#!/usr/bin/env python3
"""Flea send-target plugin for Android Quick Share, backed by the quickshare CLI.

Flea gives a request 30 seconds and stops idle plugins, while a Quick Share send waits for
someone to tap Accept and then copies the file. So `send` hands the transfer to a detached
process that runs `quickshare send` and announces the result, the way omarchy-tailscale-send
does for Taildrop, and answers Flea at once.
"""
import json
import os
import shutil
import subprocess
import sys

BROWSE_SECONDS = "2"
GLYPH = "󰄜"

# What `quickshare --json send` ends with, and the notification each result becomes.
RESULTS = {
    "delivered": ("Sent to {name}", "normal"),
    "declined": ("{name} declined", "normal"),
    "cancelled": ("{name} cancelled the transfer", "normal"),
    "failed": ("Could not send to {name}", "critical"),
}


def quickshare():
    found = shutil.which("quickshare")
    if found:
        return found
    local = os.path.expanduser("~/.local/bin/quickshare")
    return local if os.access(local, os.X_OK) else None


def targets():
    program = quickshare()
    if not program:
        return [{"id": "missing", "label": "Install quickshare to send", "state": "missing"}]
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
    if not quickshare():
        raise ValueError("quickshare is not installed.")
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--deliver", target, *paths],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return f"Sending to {target}. Accept on the device."


def notify(title, body, urgency):
    if shutil.which("omarchy-notification-send"):
        command = ["omarchy-notification-send", "-g", GLYPH, "--app-name", "Quick Share"]
        if urgency == "critical":
            command += ["-u", "critical"]
        command += [title, body]
    else:
        command = ["notify-send", "-a", "Quick Share", "-u", urgency, title, body]
    subprocess.run(command, check=False)


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


def serve():
    for line in iter(lambda: sys.stdin.buffer.readline(65538), b""):
        if len(line) > 65536:
            break
        try:
            request = json.loads(line)
            op = request.get("op")
            if op == "hello":
                reply = {"op": "ready", "protocolVersion": 1}
            elif op == "targets":
                reply = {"op": "targets", "targets": targets()}
            elif op == "send":
                reply = {"op": "done", "message": send(request.get("target"), request.get("paths", []))}
            elif op == "settings":
                reply = {"op": "done"}
            elif op == "cancel":
                break
            else:
                reply = {"op": "error", "message": "Unsupported action."}
        except (ValueError, TypeError) as error:
            reply = {"op": "error", "message": str(error)[:4096]}
        print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[1] == "--deliver":
        deliver(sys.argv[2], sys.argv[3:])
    else:
        serve()
