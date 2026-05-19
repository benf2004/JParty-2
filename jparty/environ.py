import sys
import os

if getattr(sys, "frozen", False):
    # For PyInstaller, _MEIPASS is where bundled resources are.
    # The application itself might be in .app/Contents/MacOS
    root = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
