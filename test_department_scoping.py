import unittest
from pipeline import ComplianceEngine

class TestDepartmentScoping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = ComplianceEngine()
        
    def test_strict_department_scoping(self):
        # Query containing electrical keywords but scoped strictly to CIVIL
        res = self.engine.search_top_standards("PVC Insulated cable 1100V", k=5, department="CIVIL")
        
        # Verify no electrical codes like IS 1554 or IS 694 leaked
        electrical_codes = ["IS 1554", "IS 694", "IS 10322", "IS 8828"]
        for standard in res:
            self.assertNotIn(standard["is_code"], electrical_codes, "Cross-domain leakage detected!")
            
    def test_explicit_code_boost(self):
        res = self.engine.search_top_standards("General construction works", k=5, department="CIVIL", explicit_codes={"IS1786"})
        top_match = res[0]
        self.assertEqual(top_match["is_code"], "IS 1786", "Explicit code did not receive heavy score boost.")
        self.assertTrue(top_match["score"] < 0.5, "Boosted score should be significantly reduced.")
        
    def test_fallback_global_search(self):
        res = self.engine.search_top_standards("PVC Insulated cable 1100V", k=5, department=None)
        codes = [r["is_code"] for r in res]
        self.assertIn("IS 1554", codes, "Global search failed to find relevant generic code.")

if __name__ == "__main__":
    unittest.main()
