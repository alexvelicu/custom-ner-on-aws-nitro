#!/bin/bash

export_key=False
ls -la
ls -la server
# Sart the server
cd app
python3 server.py --export $export_key