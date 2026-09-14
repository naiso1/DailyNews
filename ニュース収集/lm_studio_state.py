"""Native LM Studio load-state checks shared by startup and idle reload."""
import json
import os
from urllib.parse import urlsplit
import urllib.request


def gpu_load_args():
    value = os.environ.get("LLM_GPU_OFFLOAD", "").strip().lower()
    if value in {"", "auto"}:
        return []
    if value not in {"off", "max"}:
        try:
            valid = 0 <= float(value) <= 1
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("LLM_GPU_OFFLOAD must be auto, off, max, or a ratio from 0 to 1")
    return ["--gpu", value]


def loaded_model_ids(host, opener=None):
    if opener is None:
        if (urlsplit(host).hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({})).open
        else:
            opener = urllib.request.urlopen
    # The OpenAI-compatible list also includes unloaded models when JIT is on.
    # Only native API load state can safely guard against overlapping loads.
    for endpoint in ("/api/v1/models", "/api/v0/models"):
        try:
            with opener(f"{host}{endpoint}", timeout=5) as r:
                data = json.loads(r.read())
            if endpoint == "/api/v1/models":
                models = data["models"]
                if not isinstance(models, list):
                    raise ValueError("Invalid model list")
                loaded = set()
                for model in models:
                    instances = model["loaded_instances"]
                    if not isinstance(instances, list):
                        raise ValueError("Missing instance state")
                    for instance in instances:
                        identifier = instance["id"]
                        if not isinstance(identifier, str) or not identifier.strip():
                            raise ValueError("Invalid loaded instance ID")
                        loaded.add(identifier.strip())
                return loaded
            models = data["data"]
            if not isinstance(models, list):
                raise ValueError("Invalid legacy model list")
            loaded = set()
            for model in models:
                if model.get("state") not in {"loaded", "not-loaded", "unloaded"}:
                    raise ValueError("Missing legacy load state")
                if model["state"] == "loaded":
                    identifier = model["id"]
                    if not isinstance(identifier, str) or not identifier.strip():
                        raise ValueError("Invalid legacy model ID")
                    loaded.add(identifier.strip())
            return loaded
        except Exception:
            continue
    raise RuntimeError("Cannot verify LM Studio loaded models; refusing another load.")
