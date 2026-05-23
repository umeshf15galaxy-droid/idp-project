"""
api/index.py — Vercel Serverless entry point for FastAPI.
Vercel routes all /api/* requests here.
"""
import sys
import os

# Add backend directory to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import app  # noqa: F401 — Vercel needs 'app' exported
