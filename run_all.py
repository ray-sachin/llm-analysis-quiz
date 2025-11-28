import subprocess
import time
import sys
import os
from dotenv import load_dotenv

def run_all():
    # Load env vars
    load_dotenv()
    
    # Handle API Key
    api_key = os.getenv("GOOGLE_API_KEY")
    aipipe = os.getenv("AIPIPE_TOKEN")
    
    env = os.environ.copy()
    if not api_key and aipipe:
        print("Using AIPIPE_TOKEN as GOOGLE_API_KEY")
        env["GOOGLE_API_KEY"] = aipipe
    
    # Ensure SECRET is set
    env["SECRET"] = "sachin"
        
    print("Starting main.py...")
    # Start main.py in background, redirecting output to file to avoid deadlock
    log_file = open("server.log", "w")
    server = subprocess.Popen(
        [sys.executable, "-u", "main.py"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=os.getcwd(),
        env=env
    )
    
    print("Waiting for server to start (10s)...")
    time.sleep(10)
    
    # Check if server is still running
    if server.poll() is not None:
        print("Server crashed!")
        log_file.close()
        with open("server.log", "r") as f:
            print(f.read())
        return
    
    print("Server running. Starting test_simple.py...")
    
    # Run test
    test = subprocess.run(
        [sys.executable, "test_simple.py"],
        capture_output=True,
        text=True,
        cwd=os.getcwd()
    )
    
    print("Test output:")
    print(test.stdout)
    print("Test stderr:")
    print(test.stderr)
    
    print("Waiting for agent to complete (max 300s)...")
    start_wait = time.time()
    
    while time.time() - start_wait < 300:
        log_file.flush()
        with open("server.log", "r") as f:
            content = f.read()
            if "Tasks completed succesfully" in content:
                print("Agent completed successfully!")
                break
        if server.poll() is not None:
            print("Server crashed during agent execution!")
            break
        time.sleep(5)
    else:
        print("Timeout waiting for agent completion.")

    print("Terminating server...")
    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
        
    log_file.close()
    
    print("Server final output (from server.log):")
    with open("server.log", "r") as f:
        print(f.read())

if __name__ == "__main__":
    run_all()
