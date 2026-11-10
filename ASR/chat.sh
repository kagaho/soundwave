#!/bin/bash
export ALSA_CARD=pipewire
python3 soundwave-agent-ver1_4.py --device 14 2>/dev/null &
