"""ML-02 data validation + figures.   python scripts/ml02/validate_data.py [--source ncep_r1|era5]"""
import argparse
import json

import _boot

log = _boot.setup("validate")
from aethentra.temperature.validation import validate  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--source")
a = ap.parse_args()
r = validate.run(a.source)
st = validate.station_inventory()
print(json.dumps({k: r[k] for k in ("source", "raw_files", "n_cells", "n_land", "cells_with_any_missing_day", "t2m_1981_2010_percentiles")}, indent=1))
print(st.to_string(max_rows=80))
