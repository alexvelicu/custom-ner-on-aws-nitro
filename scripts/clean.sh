#!/bin/bash
#
# Remove unnecessary files from prohect
parent_path=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )
cd "$parent_path"

rm *.pem 2> /dev/null
rm *.eif 2> /dev/null
rm ../result.html 2> /dev/null
rm ../src/result.html 2> /dev/null
rm ../src/enclave-description.json 2> /dev/null
rm -rf ../src/.venv 2> /dev/null
rm -rf ../src/__pycache__ 2> /dev/null
rm -rf ../src/common/__pycache__ 2> /dev/null
rm -rf ../src/server/__pycache__ 2> /dev/null