#!/bin/bash

source venv/bin/activate
locust \
    --users 1 \
    --spawn-rate 1 \
    --run-time 1h \
    --json \
    --json-file "locust" \
    --print-stats \
    --html "stats.html" \
    --host http://sotongpt.soton.ac.uk

