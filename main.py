import subprocess
import re
import os
import time

ENV_FILE_PATH = ".env"
PORT = 8000  # The port used by your backend

def update_env(new_url):
    """Update the .env file with the new URL without deleting other variables."""
    env_vars = {}
    if os.path.exists(ENV_FILE_PATH):
        with open(ENV_FILE_PATH, 'r', encoding='utf-8') as file:
            for line in file:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    env_vars[key] = value

    env_vars['API_URL'] = new_url

    with open(ENV_FILE_PATH, 'w', encoding='utf-8') as file:
        for key, value in env_vars.items():
            file.write(f"{key}={value}\n")

    print(f"[\u2713] Updated {ENV_FILE_PATH} successfully: API_URL={new_url}")

def run_cloudflared():
    """Start the tool and monitor terminal output in real time."""
    command = ["cloudflared.exe", "tunnel", "--url", f"localhost:{PORT}"]

    # Combine stderr with stdout because cloudflared writes the URL in error logs
    process = subprocess.Popen(
        command, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True, 
        bufsize=1
    )

    # Regex pattern to capture the random subdomain
    url_pattern = re.compile(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)")

    print("[*] Starting Cloudflared and looking for the URL...")

    # Read output line by line while the program is running
    for line in iter(process.stdout.readline, ''):
        # You can uncomment the next line to see all Cloudflare logs
        # print(line.strip())

        match = url_pattern.search(line)
        if match:
            new_url = match.group(1)
            print(f"\n[+] Captured the new URL: {new_url}")
            update_env(new_url)

    process.stdout.close()
    process.wait()
    return process.returncode

# Self-monitoring watchdog to restart when the tunnel fails or disconnects
while True:
    print("\n[*] Starting a new Cloudflare session...")
    run_cloudflared()
    print("[!] Cloudflared stopped or the connection was lost. Retrying in 5 seconds...")
    time.sleep(5)