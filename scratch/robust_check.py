import sys
import os

# Add current dir to path to ensure we can import invesalius_rs
sys.path.insert(0, os.getcwd())

try:
    import invesalius_rs._native as _native
    print("Successfully imported invesalius_rs._native")
    print("Attributes:")
    for attr in sorted(dir(_native)):
        if not attr.startswith("__"):
            print(f"  - {attr}")
except Exception as e:
    print(f"Failed to import _native: {e}")

try:
    import invesalius_rs
    print("\nSuccessfully imported invesalius_rs")
except Exception as e:
    print(f"\nFailed to import invesalius_rs: {e}")
