#!/bin/sh
#
# Use -d option to start enclave in debug mode
parent_path=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )
cd "$parent_path"

export PYTHONDONTWRITEBYTECODE=1

eif=nitro-test.eif
enclave_name=nitro-test

nitro-cli terminate-enclave --all

if [[ $1 = "--debug" ]]; then
    nitro-cli run-enclave --debug-mode --cpu-count 2 --memory 6144 --eif-path $eif
    nitro-cli console --enclave-name $enclave_name
else
    nitro-cli run-enclave --cpu-count 2 --memory 6144 --eif-path $eif
fi
