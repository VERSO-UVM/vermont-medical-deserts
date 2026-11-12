#!/usr/bin/env python3
"""Extract Vermont providers from the NPPES monthly file.

1. Download the "Monthly NPPES Downloadable File" ZIP (about 1 GB) from
   https://download.cms.gov/nppes/NPI_Files.html
2. Run:  python3 vt_npi_extract.py NPPES_Data_Dissemination_<Month>_<Year>.zip

Reads the CSV straight out of the ZIP (no need to unzip the ~10 GB file).
Writes vt_npi.csv (all columns, Vermont practice addresses only) and prints
a summary. Uses only the Python standard library.
"""
import csv
import io
import sys
import zipfile
from collections import Counter

STATE_COL = "Provider Business Practice Location Address State Name"
CITY_COL = "Provider Business Practice Location Address City Name"
TYPE_COL = "Entity Type Code"            # 1 = individual, 2 = organization
TAXONOMY_COL = "Healthcare Provider Taxonomy Code_1"
DEACTIVATED_COL = "NPI Deactivation Date"


def main(zip_path, out_path="vt_npi.csv"):
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist()
                 if n.lower().startswith("npidata_pfile")
                 and n.lower().endswith(".csv")
                 and "fileheader" not in n.lower()]
        if not names:
            sys.exit("No npidata_pfile_*.csv found in ZIP: %s" % z.namelist())
        with z.open(names[0]) as raw, open(out_path, "w", newline="") as out:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))
            for col in (STATE_COL, CITY_COL, TYPE_COL, TAXONOMY_COL):
                if col not in reader.fieldnames:
                    sys.exit("Expected column missing: %r. CMS may have "
                             "changed the layout; check the Readme." % col)
            writer = csv.DictWriter(out, fieldnames=reader.fieldnames)
            writer.writeheader()
            types, cities, taxonomies = Counter(), Counter(), Counter()
            total = kept = 0
            for row in reader:
                total += 1
                if row[STATE_COL].strip().upper() != "VT":
                    continue
                if row.get(DEACTIVATED_COL, "").strip():
                    continue
                writer.writerow(row)
                kept += 1
                types[row[TYPE_COL]] += 1
                cities[row[CITY_COL].strip().upper()] += 1
                taxonomies[row[TAXONOMY_COL]] += 1

    print("Source file: %s" % names[0])
    print("Rows scanned: %d   Vermont rows kept: %d" % (total, kept))
    print("Individuals (type 1): %d" % types.get("1", 0))
    print("Organizations (type 2): %d" % types.get("2", 0))
    print("\nTop 20 practice cities:")
    for city, n in cities.most_common(20):
        print("  %-25s %d" % (city, n))
    print("\nTop 25 primary taxonomy codes (look up at taxonomy.nucc.org):")
    for code, n in taxonomies.most_common(25):
        print("  %-12s %d" % (code or "(blank)", n))
    print("\nWrote %s" % out_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
