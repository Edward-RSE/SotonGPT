#!/bin/bash

source venv/bin/activate
locust \
	--headless \
    --users 64 \
    --spawn-rate 1 \
    --run-time 1h \
    --host https://sotongpt.soton.ac.uk
