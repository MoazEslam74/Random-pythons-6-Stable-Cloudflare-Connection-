import subprocess
import re
import os
import time
import json
import requests
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

# Global variables
backend_process = None
cloudflared_process = None
monitor_app = None  # Reference to the monitor UI
ENV_FILE_PATH = ".env"
CONFIG_FILE = "sync_config.json"
PORT = 8000  

# Global app configuration
app_config = {
    "mode": "local",
    "github_username": "",
    "github_token": "",
    "gist_id": ""
}

# --------- Config System ----------

def load_config():
    """Load saved settings to improve UX."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"mode": "local", "github_username": "", "github_token": "", "gist_id": ""}

def save_config(config):
    """Save settings locally."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f)
    except Exception:
        pass

# --------- UI Helper ----------
def log_msg(msg):
    """Send log messages to the Monitor UI instead of the standard terminal."""
    if monitor_app:
        monitor_app.append_log(msg)
    else:
        print(msg)

# --------- GitHub Gist Sync ----------

def update_github_gist(new_url, token, gist_id):
    """Update the JSON file inside the GitHub Gist."""
    url = f"https://api.github.com/gists/{gist_id}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    
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
            log_msg(f"[\u2713] Gist updated successfully! Frontend can now sync.")
        else:
            log_msg(f"[x] Failed to update Gist. HTTP Code: {response.status_code}")
    except Exception as e:
        log_msg(f"[x] Error connecting to GitHub API: {e}")

# --------- Core Functions ----------

def update_env(new_url):
    """Update the .env file with the new URL."""
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

    log_msg(f"[\u2713] Updated {ENV_FILE_PATH} successfully.")
    
    if app_config["mode"] == "remote":
        log_msg("[*] Syncing with GitHub Gist...")
        update_github_gist(new_url, app_config["github_token"], app_config["gist_id"])


def run_cloudflared():
    """Start Cloudflared and monitor output."""
    global cloudflared_process
    command = ["cloudflared.exe", "tunnel", "--url", f"localhost:{PORT}"]

    # Start process and capture output
    cloudflared_process = subprocess.Popen(
        command, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True, 
        bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

    url_pattern = re.compile(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)")
    log_msg("[*] Waiting for Cloudflare URL...")

    # Read output line by line (runs in background thread, so UI won't freeze)
    for line in iter(cloudflared_process.stdout.readline, ''):
        match = url_pattern.search(line)
        if match:
            new_url = match.group(1)
            log_msg(f"\n[+] Captured New URL:\n{new_url}\n")
            update_env(new_url)

    cloudflared_process.stdout.close()
    cloudflared_process.wait()

def watchdog_loop():
    """Self-monitoring loop that runs in a separate thread."""
    try:
        while True:
            log_msg("\n[*] Starting Cloudflare Session...")
            run_cloudflared()
            log_msg("[!] Connection lost or stopped. Retrying in 5s...")
            time.sleep(5)
    except Exception as e:
        log_msg(f"[x] Watchdog error: {e}")


# --------- GUI Classes ----------

class SetupUI:
    """The initial Setup Window for collecting configurations."""
    def __init__(self):
        self.config = load_config()
        self.user_data = None
        self.root = tk.Tk()
        self.root.title("Cloudflare Sync Settings")
        
        w, h = 480, 480
        ws, hs = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry('%dx%d+%d+%d' % (w, h, (ws/2)-(w/2), (hs/2)-(h/2)))
        
        tk.Label(self.root, text="Select Operation Mode:", font=("Arial", 11, "bold")).pack(pady=(15, 5))
        self.mode_var = tk.StringVar(value=self.config.get("mode", "local"))
        
        self.remote_frame = tk.Frame(self.root)
        
        tk.Radiobutton(self.root, text="Local Mode (Update .env only)", variable=self.mode_var, value="local", command=self.toggle_frame, font=("Arial", 10)).pack(anchor="w", padx=40)
        tk.Radiobutton(self.root, text="Remote Mode (Sync with GitHub Gist)", variable=self.mode_var, value="remote", command=self.toggle_frame, font=("Arial", 10)).pack(anchor="w", padx=40)

        # Remote Settings
        tk.Label(self.remote_frame, text="GitHub Username:", font=("Arial", 9)).pack(anchor="w", pady=(10, 0))
        self.entry_user = tk.Entry(self.remote_frame, width=45, font=("Arial", 10))
        self.entry_user.pack(pady=(0, 5))
        self.entry_user.insert(0, self.config.get("github_username", ""))

        tk.Label(self.remote_frame, text="GitHub Personal Access Token (Gist Scope):", font=("Arial", 9)).pack(anchor="w")
        self.entry_token = tk.Entry(self.remote_frame, width=45, font=("Arial", 10), show="*")
        self.entry_token.pack(pady=(0, 5))
        self.entry_token.insert(0, self.config.get("github_token", ""))

        tk.Label(self.remote_frame, text="Gist ID:", font=("Arial", 9)).pack(anchor="w")
        self.entry_gist = tk.Entry(self.remote_frame, width=45, font=("Arial", 10))
        self.entry_gist.pack(pady=(0, 10))
        self.entry_gist.insert(0, self.config.get("gist_id", ""))
        
        # Generator Button for JS Snippet
        tk.Button(self.remote_frame, text="< / > Generate Integration Code", command=self.generate_code, bg="#f0f0f0").pack(pady=5)
        
        self.toggle_frame()

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="✅ Start System", command=self.on_confirm, bg="#4CAF50", fg="white", width=15, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=10)
        
        self.root.mainloop()

    def toggle_frame(self):
        if self.mode_var.get() == "remote":
            self.remote_frame.pack(pady=10, fill="x", padx=40)
        else:
            self.remote_frame.pack_forget()

    def generate_code(self):
        """Generates JS snippet for React/Vue/JS dynamically based on inputs."""
        user = self.entry_user.get().strip()
        gist = self.entry_gist.get().strip()
        
        if not user or not gist:
            messagebox.showwarning("Warning", "Please enter GitHub Username and Gist ID first.")
            return
            
        code = f"""// --- Cloudflare Dynamic URL Fetcher ---
// Use this snippet in React, Vue, or Vanilla JS

const GITHUB_USERNAME = "{user}";
const GIST_ID = "{gist}";

export async function getActiveBackendUrl() {{
    try {{
        const cacheBuster = new Date().getTime();
        const RAW_URL = `https://gist.githubusercontent.com/${{GITHUB_USERNAME}}/${{GIST_ID}}/raw/backend_url.json?t=${{cacheBuster}}`;
        
        const response = await fetch(RAW_URL);
        if (!response.ok) throw new Error("Network response was not ok");
        
        const data = await response.json();
        return data.url; 
    }} catch (error) {{
        console.error("Failed to fetch dynamic backend URL:", error);
        return null;
    }}
}}"""
        code_win = tk.Toplevel(self.root)
        code_win.title("Integration Code")
        txt = scrolledtext.ScrolledText(code_win, wrap="word", height=18, width=70, font=("Courier", 10))
        txt.pack(padx=10, pady=10)
        txt.insert("1.0", code)
        txt.config(state="disabled")

    def on_confirm(self):
        selected_mode = self.mode_var.get()
        if selected_mode == "remote":
            if not self.entry_user.get() or not self.entry_token.get() or not self.entry_gist.get():
                messagebox.showwarning("Warning", "Please fill all remote fields!")
                return
                
        self.user_data = {
            "mode": selected_mode,
            "github_username": self.entry_user.get().strip(),
            "github_token": self.entry_token.get().strip(),
            "gist_id": self.entry_gist.get().strip()
        }
        save_config(self.user_data)
        self.root.destroy()

class MonitorUI:
    """The Live Monitor Window replacing the terminal output."""
    def __init__(self, root):
        self.root = root
        self.root.title("System Monitor - Cloudflare Sync")
        self.root.geometry("600x400")
        self.root.configure(bg="#1e1e1e")
        
        # Header
        mode_label = tk.Label(root, text=f"Mode: {app_config['mode'].upper()}", bg="#1e1e1e", fg="#4CAF50", font=("Arial", 12, "bold"))
        mode_label.pack(pady=10)

        # Log Console (ScrolledText)
        self.console = scrolledtext.ScrolledText(root, state='disabled', bg="#000000", fg="#00FF00", font=("Consolas", 10), wrap=tk.WORD)
        self.console.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # Handle clean exit
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def append_log(self, msg):
        """Thread-safe GUI update using .after()"""
        self.root.after(0, self._insert_text, msg)

    def _insert_text(self, msg):
        self.console.config(state='normal')
        self.console.insert(tk.END, msg + "\n")
        self.console.see(tk.END)  # Auto-scroll to bottom
        self.console.config(state='disabled')

    def on_closing(self):
        """Stop background processes cleanly before exiting."""
        self.append_log("\n[!] Shutting down system...")
        global cloudflared_process
        if cloudflared_process:
            cloudflared_process.terminate()
        self.root.destroy()
        sys.exit()

# --------- Main Execution ----------
if __name__ == "__main__":
    # 1. Setup UI
    setup = SetupUI()
    if not setup.user_data:
        sys.exit()
        
    app_config.update(setup.user_data)

    # 2. Start Monitor UI
    root = tk.Tk()
    monitor_app = MonitorUI(root)
    
    # 3. Start Watchdog in a separate background thread
    worker_thread = threading.Thread(target=watchdog_loop, daemon=True)
    worker_thread.start()

    # 4. Run GUI Event Loop
    root.mainloop()