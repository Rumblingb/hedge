#!/bin/bash
cd /Users/brain/hedge
export RH_BRAIN_ROOT="${RH_BRAIN_ROOT:-/Users/brain/hedge/.rumbling-hedge}"
python3 scripts/brain_cortex.py cycle --advisory-only
