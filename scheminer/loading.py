import re
from pathlib import Path

import pandas as pd


def load_csv_folder(path: Path):
    return [pd.read_csv(f) for f in path.glob("*.csv")]
