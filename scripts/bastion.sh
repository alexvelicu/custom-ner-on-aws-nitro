#!/bin/bash
parent_path=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )
cd "$parent_path"

cd ../src
python3.7 -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
python3.7 bastion.py $1 $2
cd ../scripts/