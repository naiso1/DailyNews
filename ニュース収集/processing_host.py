"""Select the processing workstation before any collection or status writes."""
import json
from pathlib import Path
import re
import socket


def processing_host_status(root, hostname=None):
    policy = Path(root) / "deployment/workstation/processing_host.json"
    try:
        data = json.loads(policy.read_text(encoding="utf-8-sig"))
        active = data["active_host"]
        if (type(data.get("schema_version")) is not int or data["schema_version"] != 1
                or not isinstance(active, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}", active)):
            raise ValueError("Invalid processing-host policy")
    except Exception as exc:
        raise RuntimeError("Processing-host policy unavailable or invalid; no processing started") from exc
    current = socket.gethostname() if hostname is None else hostname
    return {"hostname": current, "activeHost": active,
            "allowed": current.casefold() == active.casefold()}


def enforce_processing_host(root, check_only=False):
    status = processing_host_status(root)
    if check_only or not status["allowed"]:
        # A retired workstation must NOT overwrite the new workstation's mail status.
        print("[PROCESSING_HOST] " + json.dumps(status), flush=True)
        raise SystemExit(0)
