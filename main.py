import subprocess
import re
import os
import time
import json
import requests
import sys
import tkinter as tk
from tkinter import messagebox

# Global variables
backend_process = None  # Global variable to save process state
ENV_FILE_PATH = ".env"
CONFIG_FILE = "sync_config.json"
PORT = 8000  # The port used by your backend

# Global app configuration
app_config = {
    "mode": "local",
    "github_token": "",
    "gist_id": ""
}

# --------- Config & UI System ----------

def load_config():
    """Load saved settings to improve UX (no need to re-enter token every time)."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"mode": "local", "github_token": "", "gist_id": ""}

def save_config(config):
    """Save settings locally."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f)
    except Exception:
        pass

def get_startup_settings():
    """Display UI to select operation mode and collect GitHub credentials if needed."""
    config = load_config()
    user_data = None

    root = tk.Tk()
    root.title("Cloudflare Sync Settings")
    
    # Center the window
    w, h = 420, 380
    ws, hs = root.winfo_screenwidth(), root.winfo_screenheight()
    x, y = (ws/2) - (w/2), (hs/2) - (h/2)
    root.geometry('%dx%d+%d+%d' % (w, h, x, y))
    
    # 1. Mode Selection
    tk.Label(root, text="Select Operation Mode:", font=("Arial", 11, "bold")).pack(pady=(15, 5))
    
    mode_var = tk.StringVar(value=config.get("mode", "local"))
    
    # Frame for remote settings (Gist)
    remote_frame = tk.Frame(root)
    
    def toggle_remote_frame():
        """Show or hide GitHub Gist inputs based on selected mode."""
        if mode_var.get() == "remote":
            remote_frame.pack(pady=10, fill="x", padx=20)
        else:
            remote_frame.pack_forget()

    tk.Radiobutton(root, text="Local Mode (Update .env only)", variable=mode_var, value="local", command=toggle_remote_frame, font=("Arial", 10)).pack(anchor="w", padx=40)
    tk.Radiobutton(root, text="Remote Mode (Sync with GitHub Gist)", variable=mode_var, value="remote", command=toggle_remote_frame, font=("Arial", 10)).pack(anchor="w", padx=40)

    # Remote Settings Inputs
    tk.Label(remote_frame, text="GitHub Personal Access Token:", font=("Arial", 9)).pack(anchor="w")
    entry_token = tk.Entry(remote_frame, width=40, font=("Arial", 10), show="*")
    entry_token.pack(pady=(0, 10))
    entry_token.insert(0, config.get("github_token", ""))

    tk.Label(remote_frame, text="Gist ID:", font=("Arial", 9)).pack(anchor="w")
    entry_gist = tk.Entry(remote_frame, width=40, font=("Arial", 10))
    entry_gist.pack(pady=(0, 5))
    entry_gist.insert(0, config.get("gist_id", ""))
    
    tk.Label(remote_frame, text="* Create a secret Gist with 'backend_url.json'", font=("Arial", 8, "italic"), fg="gray").pack(anchor="w")

    # Initial UI state setup
    toggle_remote_frame()

    # Buttons actions
    def on_confirm():
        nonlocal user_data
        selected_mode = mode_var.get()
        token = entry_token.get().strip()
        gist_id = entry_gist.get().strip()

        if selected_mode == "remote":
            if not token or not gist_id:
                messagebox.showwarning("Warning", "Please provide both Token and Gist ID for Remote Mode!", parent=root)
                return
            
        user_data = {
            "mode": selected_mode,
            "github_token": token,
            "gist_id": gist_id
        }
        
        save_config(user_data)
        root.destroy()

    def on_cancel():
        root.destroy()
        sys.exit()

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=20)
    
    tk.Button(btn_frame, text="✅ Start System", command=on_confirm, bg="#4CAF50", fg="white", width=15, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=10)
    tk.Button(btn_frame, text="❌ Exit", command=on_cancel, bg="#dc3545", fg="white", width=10, font=("Arial", 10)).pack(side=tk.LEFT, padx=10)

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()
    
    return user_data

# --------- GitHub Gist Sync ----------

def update_github_gist(new_url, token, gist_id):
    """Update the JSON file inside the GitHub Gist to act as a cloud registry."""
    url = f"https://api.github.com/gists/{gist_id}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    
    # Structure required by GitHub API to update a file inside a Gist
    data = {
        "files": {
            "backend_url.json": {
                "content": json.dumps({"url": new_url})
            }
        }
    }

    try:
        response = requests.patch(url, headers=headers, json=data)
        if response.status_code == 200:
            print(f"[\u2713] Gist updated successfully: The Frontend can now reach the new URL.")
        else:
            print(f"[x] Failed to update Gist. HTTP Code: {response.status_code}")
    except Exception as e:
        print(f"[x] Error connecting to GitHub API: {e}")

# --------- Core Functions ----------

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
    
    # Trigger cloud sync if remote mode is active
    if app_config["mode"] == "remote":
        print("[*] Remote mode is active. Syncing with GitHub Gist...")
        update_github_gist(new_url, app_config["github_token"], app_config["gist_id"])


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
        match = url_pattern.search(line)
        if match:
            new_url = match.group(1)
            print(f"\n[+] Captured the new URL: {new_url}")
            update_env(new_url)

    process.stdout.close()
    process.wait()
    return process.returncode


# --------- Main Execution ----------
if __name__ == "__main__":
    # 1. Start UI and get configuration
    config = get_startup_settings()
    if not config:
        sys.exit()
        
    app_config.update(config)
    
    print(f"\n✅ System initialized in [{app_config['mode'].upper()}] mode.\n")

    # 2. Self-monitoring watchdog to restart when the tunnel fails or disconnects
    try:
        while True:
            print("[*] Starting a new Cloudflare session...")
            run_cloudflared()
            print("[!] Cloudflared stopped or the connection was lost. Retrying in 5 seconds...")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n[!] System stopped by the user.")
        if backend_process:
            print("[*] Shutting down the backend...")
            backend_process.terminate()
            backend_process.wait()
        print("[\u2713] Safe exit. Goodbye!")