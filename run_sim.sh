#!/bin/bash
source integration_venv/bin/activate
pip install --ignore-installed numpy pandas xgboost
PYTHONPATH=pipeline python pipeline/src/simulate_history.py
