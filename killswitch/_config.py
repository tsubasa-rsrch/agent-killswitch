"""Configuration loading from env vars and config file."""

import json
import os
from pathlib import Path

_CONFIG_DIR = Path.home() / ".killswitch"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

_DEFAULTS = {
    "server_url": "",
    "api_key": "",
    "heartbeat_interval": 5,
    "local_mode": True,
}


def load_config() -> dict:
    """Load config from file, then overlay env vars."""
    config = dict(_DEFAULTS)

    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE) as f:
                file_config = json.load(f)
            config.update(file_config)
        except (json.JSONDecodeError, OSError):
            pass

    env_map = {
        "KILLSWITCH_SERVER_URL": "server_url",
        "KILLSWITCH_API_KEY": "api_key",
        "KILLSWITCH_HEARTBEAT_INTERVAL": "heartbeat_interval",
        "KILLSWITCH_LOCAL_MODE": "local_mode",
    }
    for env_key, config_key in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            if config_key == "heartbeat_interval":
                config[config_key] = int(val)
            elif config_key == "local_mode":
                config[config_key] = val.lower() not in ("0", "false", "no")
            else:
                config[config_key] = val

    if config["server_url"]:
        config["local_mode"] = False

    return config


def save_config(config: dict) -> None:
    """Save config to file."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
