#!/usr/bin/env python3
"""Standalone Deck entry point: python3 deck.py  (or ./launch.sh)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from first_mate.deck_server import serve_deck

if __name__ == "__main__":
    serve_deck()
