#!/bin/sh
# This helper lives outside the app and receives paths as separate arguments.
set -eu
pid=$1
target=$2
staged=$3
backup=$4
system=$5
attempt=0
while kill -0 "$pid" 2>/dev/null; do
    attempt=$((attempt + 1))
    if [ "$attempt" -gt 120 ]; then
        echo 'JParty did not exit; keeping the existing installation.'
        exit 1
    fi
    sleep 1
done
if [ ! -d "$target" ] || [ ! -d "$staged" ] || [ -e "$backup" ]; then
    echo 'The installation folders changed; keeping the existing installation.'
    exit 1
fi
mv "$target" "$backup"
if ! mv "$staged" "$target"; then
    mv "$backup" "$target"
    exit 1
fi
if [ "$system" = macos ]; then
    if ! /usr/bin/open -n "$target"; then
        mv "$target" "$staged"
        mv "$backup" "$target"
        /usr/bin/open -n "$target"
        exit 1
    fi
else
    if [ ! -x "$target/JParty" ]; then
        mv "$target" "$staged"
        mv "$backup" "$target"
        exit 1
    fi
    "$target/JParty" </dev/null &
fi
