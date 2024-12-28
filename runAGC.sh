#!/bin/bash

echo "Starting VirtualAGC"
screen -dm bash -c "cd /home/gazzapac-dsky/virtualagc/yaAGC/; ./yaAGC --port=19797 --core=../Colossus249/Colossus249.bin"

echo "Starting DSKY"
sudo python3 piDSKY-gp.py
