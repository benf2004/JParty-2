import os
import sys
import json
from pathlib import Path

def get_user_data_dir():
    if sys.platform == "darwin":
        # Standard macOS location: ~/Library/Application Support/JParty
        path = Path.home() / "Library" / "Application Support" / "JParty"
    else:
        path = Path.home() / ".jparty"
    
    path.mkdir(parents=True, exist_ok=True)
    return path

user_data_dir = get_user_data_dir()
config_path = str(user_data_dir / "config.json")
log_path = str(user_data_dir / "latest.log")
history_path = str(user_data_dir / "history.json")

# Ensure config.json exists
if not os.path.exists(config_path):
    from jparty.constants import DEFAULT_CONFIG
    with open(config_path, 'w') as f:
        json.dump(DEFAULT_CONFIG, f)

# Ensure history.json exists
if not os.path.exists(history_path):
    with open(history_path, 'w') as f:
        json.dump({}, f)
