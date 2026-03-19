"""Allow running as: python -m stacks"""
import sys
import os
import io

# Suppress noisy torch/safetensors stderr output during model loading
_original_stderr = sys.stderr

def main_quiet():
    from stacks.cli import main
    # Redirect stderr to suppress torch loading noise
    sys.stderr = io.StringIO()
    try:
        main()
    finally:
        sys.stderr = _original_stderr

if __name__ == "__main__":
    main_quiet()
