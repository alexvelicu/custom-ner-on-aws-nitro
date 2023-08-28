#!/bin/bash
#
# Use the --server option to run the client app as a REST API server

parent_path=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )
cd "$parent_path"

cd ../src/
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
echo "Starting client"
python3 client.py $1 $2 $3 $4 $5 $6
cd ../scripts/