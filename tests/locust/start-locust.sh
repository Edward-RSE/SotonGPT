#!/bin/bash

source venv/bin/activate
locust \
	--headless \
    --users 250 \
    --spawn-rate 1 \
    --run-time 6h \
    --print-stats \
    --html "locust-stats.html" \
    --host http://sotongpt.soton.ac.uk
