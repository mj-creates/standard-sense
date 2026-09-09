import os
import glob
import zipfile
import re

data_dir = "standards_data"
files = glob.glob(os.path.join(data_dir, "*.xlsx"))

total_rows = 0
for f in files:
    try:
        with zipfile.ZipFile(f, 'r') as z:
            sheet1_xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            rows = len(re.findall(r'<row ', sheet1_xml))
            # Get shared strings for schema
            shared_xml = z.read("xl/sharedStrings.xml").decode("utf-8")
            # Just extract some header strings for schema integrity if needed
            print(f"File: {os.path.basename(f)} | Rows (incl. header): {rows}")
            total_rows += rows
    except Exception as e:
        print(f"File: {os.path.basename(f)} | Error: {e}")

print(f"Total Rows: {total_rows}")
