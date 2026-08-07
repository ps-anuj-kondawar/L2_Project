import requests
import json
import re
import time
import os

URL = "http://localhost:7860/api/v1/audit"

def parse_testcases(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by headers (e.g. # Test 1 or ## Test J1)
    tests = []
    
    # regex to capture test blocks
    # Looking for "# Test" or "## Test" followed by content until the next test
    parts = re.split(r'^(#+\s+Test.*)$', content, flags=re.MULTILINE)
    
    if len(parts) > 1:
        for i in range(1, len(parts), 2):
            test_name = parts[i].strip()
            test_body = parts[i+1]
            
            # Extract input block
            input_match = re.search(r'Input\s+```(?:text)?\s*(.*?)\s*```', test_body, re.DOTALL | re.IGNORECASE)
            
            # Extract expected block
            expected_match = re.search(r'Expected(?:.*?)\s+```(?:text)?\s*(.*?)\s*```', test_body, re.DOTALL | re.IGNORECASE)
            
            if input_match:
                test_input = input_match.group(1).strip()
                test_expected = expected_match.group(1).strip() if expected_match else ""
                tests.append({
                    "name": test_name,
                    "input": test_input,
                    "expected": test_expected
                })
    return tests

def run_tests():
    tests = parse_testcases("testcases.md")
    if not tests:
        print("No tests found in testcases.md")
        return
        
    print(f"Found {len(tests)} test cases. Running them through the API (this may take a while)...")
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(tests, 1):
        name = test["name"]
        user_input = test["input"]
        expected_text = test["expected"]
        
        # Check if user asked for SDS
        expects_sds = "Generate SDS" in user_input or "16-section SDS generated" in expected_text or "Generate complete 16-section SDS" in expected_text
        # If they didn't ask for it, they expect "No SDS generated" or just shouldn't get one.
        
        # Determine jurisdiction and language if present
        region = "US"
        language = "en"
        
        if "Jurisdiction: EU CLP" in user_input:
            region = "EU"
        elif "Jurisdiction: WHMIS" in user_input:
            region = "CA"
            
        if "Language: Spanish" in user_input:
            language = "es"
        elif "Language: German" in user_input:
            language = "de"
        elif "Language: French" in user_input:
            language = "fr"
            
        payload = {
            "user_input": user_input,
            "intent": "audit", # Let the ReAct loop dynamically upgrade to "full" if SDS requested
            "region": region,
            "language": language
        }
        
        print(f"\n[{i}/{len(tests)}] Running {name}...")
        
        try:
            start = time.time()
            resp = requests.post(URL, json=payload, timeout=90)
            latency = time.time() - start
            
            if resp.status_code != 200:
                print(f"FAILED: HTTP {resp.status_code} - {resp.text}")
                failed += 1
                continue
                
            data = resp.json()
            comp = data.get("compliance_report", {})
            status = comp.get("overall_approval_status", "UNKNOWN")
            
            sds_generated = data.get("sds_html") is not None and data.get("sds_html") != ""
            
            print(f"  Status: {status} (in {latency:.2f}s)")
            print(f"  SDS Generated: {sds_generated}")
            
            # Basic Assertions based on "Expected" block
            test_failed = False
            fail_reason = ""
            
            if "REJECTED" in expected_text and status != "REJECTED":
                test_failed = True
                fail_reason += f"Expected REJECTED, got {status}. "
            elif "APPROVED" in expected_text and status != "APPROVED":
                test_failed = True
                fail_reason += f"Expected APPROVED, got {status}. "
            elif "REVIEW_REQUIRED" in expected_text and status != "REVIEW_REQUIRED":
                test_failed = True
                fail_reason += f"Expected REVIEW_REQUIRED, got {status}. "
                
            if expects_sds and not sds_generated:
                test_failed = True
                fail_reason += "Expected SDS to be generated, but it was NOT. "
            elif not expects_sds and sds_generated:
                test_failed = True
                fail_reason += "Expected NO SDS, but one WAS generated! "
                
            if test_failed:
                print(f"  [FAIL] {fail_reason}")
                failed += 1
            else:
                print("  [PASS]")
                passed += 1
                
        except Exception as e:
            print(f"  [ERROR] {e}")
            failed += 1
            
    print("\n" + "="*40)
    print(f"TEST RUN COMPLETE: {passed} PASSED, {failed} FAILED.")
    print("="*40)

if __name__ == "__main__":
    run_tests()
