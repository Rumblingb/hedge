#!/usr/bin/env bash
# Delete CSV files older than 30 days in the free data directory
find "$HOME/hedge/data/free" -name "*.csv" -type f -mtime +30 -print -delete
