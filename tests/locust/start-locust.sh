#!/bin/bash

source venv/bin/activate
locust \
	--headless \
    --users 100 \
    --spawn-rate 1 \
    --run-time 48h \
    --print-stats \
    --html "locust-stats.html" \
    --host http://sotongpt.soton.ac.uk
