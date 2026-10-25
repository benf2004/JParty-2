#!/bin/bash
set -euo pipefail
ios_dir="$(cd "$(dirname "$0")" && pwd)"
repo_dir="$(dirname "$ios_dir")"
python_bin="${JPARTY_PYTHON:-$repo_dir/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then python_bin="$(command -v python3)"; fi
simulator_id="${JPARTY_SIMULATOR_ID:-}"
if [[ -z "$simulator_id" ]]; then
    simulator_id="$(xcrun simctl list devices available --json | "$python_bin" -c '
import json, sys
devices = [d for group in json.load(sys.stdin)["devices"].values() for d in group if d["isAvailable"] and "iPhone" in d["name"]]
devices.sort(key=lambda d: d["state"] != "Booted")
if not devices: sys.exit("Install an iPhone simulator in Xcode first.")
print(devices[0]["udid"])
')"
fi
derived_data="$ios_dir/DerivedData"
mkdir -p "$derived_data"
destination="platform=iOS Simulator,id=$simulator_id"
echo "Building iOS client and tests…"
if ! xcodebuild -project "$ios_dir/JParty.xcodeproj" -scheme "JParty Native Smoke" \
    -destination "$destination" -derivedDataPath "$derived_data" \
    -parallel-testing-enabled NO build-for-testing CODE_SIGNING_ALLOWED=NO > "$derived_data/native-smoke-build.log" 2>&1; then
    tail -80 "$derived_data/native-smoke-build.log"
    exit 1
fi
xcrun simctl boot "$simulator_id" 2>/dev/null || true
xcrun simctl bootstatus "$simulator_id" -b
xcrun simctl install "$simulator_id" "$derived_data/Build/Products/Debug-iphonesimulator/JParty.app"
"$python_bin" "$ios_dir/tests/fixture_server.py" > "$derived_data/native-smoke-server.log" 2>&1 &
fixture_pid=$!
trap 'kill "$fixture_pid" 2>/dev/null || true' EXIT
"$python_bin" -c '
import time, urllib.request
for _ in range(50):
    try:
        with urllib.request.urlopen("http://127.0.0.1:18080/", timeout=0.2): break
    except OSError: time.sleep(0.1)
else: raise SystemExit("HTTP fixture did not start. Check DerivedData/native-smoke-server.log.")
'
if ! kill -0 "$fixture_pid" 2>/dev/null; then
    cat "$derived_data/native-smoke-server.log"
    exit 1
fi
echo "Testing native microphone → LAN HTTP → authenticated M4A upload…"
if ! xcodebuild -project "$ios_dir/JParty.xcodeproj" -scheme "JParty Native Smoke" \
    -destination "$destination" -derivedDataPath "$derived_data" \
    -parallel-testing-enabled NO test-without-building CODE_SIGNING_ALLOWED=NO > "$derived_data/native-smoke-tests.log" 2>&1; then
    tail -100 "$derived_data/native-smoke-tests.log"
    cat "$derived_data/native-smoke-server.log"
    exit 1
fi
rg 'Executed |TEST.*SUCCEEDED' "$derived_data/native-smoke-tests.log"
rg 'Verified native M4A upload' "$derived_data/native-smoke-server.log"
