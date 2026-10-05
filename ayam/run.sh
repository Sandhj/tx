#!/bin/bash

# Cek jika bot.sh sudah running
if pgrep -f "appayam.py" > /dev/null; then
    echo "Bot sudah berjalan. Keluar."
    exit 1
fi

python /data/data/com.termux/files/home/tx/ayam/appayam.py
