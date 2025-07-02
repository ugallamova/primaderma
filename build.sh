#!/usr/bin/env bash
# exit on error
set -o errexit

# Install Python 3.10
pyenv install 3.10.12 -s
pyenv global 3.10.12

# Install dependencies
pip install -r requirements.txt