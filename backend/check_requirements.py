#!/usr/bin/env python3
"""
Script to validate that all requirements are properly installed
"""
import sys
import importlib
from pathlib import Path

# Critical dependencies that must be present
REQUIRED_PACKAGES = [
    "fastapi",
    "uvicorn",
    "sqlmodel",
    "google.generativeai",
    "docx",
    "dotenv",
]

def check_package(package_name):
    """Check if a package can be imported."""
    try:
        importlib.import_module(package_name)
        return True, None
    except ImportError as e:
        return False, str(e)

def main():
    """Main validation function."""
    print("Checking required packages...")
    print("=" * 60)
    
    all_good = True
    
    for package in REQUIRED_PACKAGES:
        success, error = check_package(package)
        status = "✓" if success else "✗"
        print(f"{status} {package}")
        if not success:
            print(f"  Error: {error}")
            all_good = False
    
    print("=" * 60)
    
    if all_good:
        print("\n✓ All required packages are installed!")
        return 0
    else:
        print("\n✗ Some packages are missing!")
        print("Run: pip install -r requirements.txt")
        return 1

if __name__ == "__main__":
    sys.exit(main())

