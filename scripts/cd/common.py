"""Repository-side imports; the installed executor never imports repository code."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'infra/modules/management-host/deployer'))
from contract import *  # noqa: F403
