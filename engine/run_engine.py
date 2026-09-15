"""PyInstaller entry point for the DubFlow engine.

Kept free of relative imports so PyInstaller can analyze it directly.
"""
from dubflow.main import main

if __name__ == "__main__":
    main()
