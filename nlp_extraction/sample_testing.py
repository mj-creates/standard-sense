
import json
import sys
from pathlib import Path

# Ensure project root is available
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nlp_extraction.extractor import extract_from_text


# ================================================================
# SAMPLE 1 - LED STREET LIGHT
# ================================================================

sample_1 = """
Tender Title: Supply of LED Street Lights
Product: LED Street Light Fixture

Technical Specifications:
- Power: 120W
- Protection: IP66
- Lifespan: 50000 hours
- Operating voltage: 230V AC
- Colour temperature: 5700K
- Housing material: aluminium die-cast
- Warranty: 5 years
- Standard: IS 10322
"""

result_1 = extract_from_text(sample_1, "MY_TENDER_001")

print("=" * 72)
print("MY SAMPLE 1 - LED STREET LIGHT")
print("=" * 72)
print(json.dumps(result_1, indent=2, ensure_ascii=False))


# ================================================================
# SAMPLE 2 - ELECTRICAL CABLE
# ================================================================

sample_2 = """
Tender Title: Supply of PVC Insulated Copper Cable
Product: PVC insulated copper cable

Technical Specifications:
- Working voltage up to 1100V
- Industrial power distribution
- Flame retardant sheath
- Conductor size 4 sq mm
- Operating temperature -15°C to 70°C
"""

result_2 = extract_from_text(sample_2, "MY_TENDER_002")

print("\n" + "=" * 72)
print("MY SAMPLE 2 - ELECTRICAL CABLE")
print("=" * 72)
print(json.dumps(result_2, indent=2, ensure_ascii=False))


# ================================================================
# SAMPLE 3 - SOLAR PANEL
# ================================================================

sample_3 = """
Tender Title: Supply of Solar Photovoltaic Modules
Product: Solar PV Module

Technical Specifications:
- Rated power: 550W
- Operating voltage: 41V
- Efficiency: 21.5%
- Material: monocrystalline silicon
- Warranty: 25 years
"""

result_3 = extract_from_text(sample_3, "MY_TENDER_003")

print("\n" + "=" * 72)
print("MY SAMPLE 3 - SOLAR PANEL")
print("=" * 72)
print(json.dumps(result_3, indent=2, ensure_ascii=False))
