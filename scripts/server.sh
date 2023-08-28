#!/bin/bash
parent_path=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )
cd "$parent_path"
echo "$parent_path"

if [[ $1 = "--simulate" ]]; then
    cd ../src/
    pwd
    echo "Running server simulating Nitro enclave"
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r ../requirements.txt
    python3 server.py --simulate True
else
    echo "Running server with Nitro enclave"
    if [[ $1 = "--debug" ]]; then
        ./run.sh --debug
    else
        ./run.sh
    fi
fi
cd ../scripts/