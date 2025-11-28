import requests
import json
import sys

# Test the local endpoint with detailed logging  
url = "http://127.0.0.1:7860/solve"

output_lines = []

def log(msg):
    print(msg)
    output_lines.append(msg)

# Test 1: Valid request (should return 200)
log("=" * 60)
log("TEST 1: Valid request with demo URL")
log("=" * 60)

payload = {
    "email": "test@example.com",
    "secret": "sachin", 
    "url": "https://tds-llm-analysis.s-anand.net/demo"
}

try:
    log(f"Payload: {json.dumps(payload, indent=2)}")
    log("Sending POST request...")
    
    response = requests.post(url, json=payload, timeout=900)
    
    log(f"\nStatus Code: {response.status_code}")
    log(f"\nResponse Body:")
    log(json.dumps(response.json(), indent=2))
    
except Exception as e:
    log(f"\nERROR: {type(e).__name__}: {e}")
    import traceback
    log(traceback.format_exc())

# Test 2: Invalid secret (should return 403)
log("\n" + "=" * 60)
log("TEST 2: Invalid secret")
log("=" * 60)

payload_wrong_secret = {
    "email": "test@example.com",
    "secret": "wrong_secret",
    "url": "https://tds-llm-analysis.s-anand.net/demo"
}

try:
    response = requests.post(url, json=payload_wrong_secret)
    log(f"Status Code: {response.status_code} (expected 403)")
    log(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    log(f"ERROR: {e}")

log("\n" + "=" * 60)
log("TESTS COMPLETED")
log("=" * 60)

# Save to file
with open("test_results.txt", "w") as f:
    f.write("\n".join(output_lines))
    
log("\nResults saved to test_results.txt")
