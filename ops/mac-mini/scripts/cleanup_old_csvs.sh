#!/usr/bin/env bash
# Delete CSV files older than 30 days in the free data directory
if [ -d "$HOME/hedge/data/free" ]; then
    find "$HOME/hedge/data/free" -name "*.csv" -type f -mtime +30 -print -delete
else
    echo "Directory $HOME/hedge/data/free does not exist; nothing to clean."
fi
