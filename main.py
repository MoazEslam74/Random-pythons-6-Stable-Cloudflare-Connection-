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
monitor_app = None  
ENV_FILE_PATH = ".env"
CONFIG_FILE = "sync_config.json"
PORT = 8000  

# Global app configuration
app_config = {
    "mode": "local",
    "github_username": "",
    "github_token": "",
    "gist_id": "",
    "cf_account_id": "",
    "cf_namespace_id": "",
    "cf_token": "",
    "cf_worker_url": ""
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
    return app_config.copy()

def save_config(config):
    """Save settings locally."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f)
    except Exception:
        pass

# --------- UI Helper ----------
def log_msg(msg):
    """Send log messages to the Monitor UI instead of standard terminal."""
    if monitor_app:
        monitor_app.append_log(msg)
    else:
        print(msg)

# --------- Cloud Sync Integrations ----------

def update_github_gist(new_url, token, gist_id):
    """Update the JSON file inside the GitHub Gist."""
    url = f"https://api.github.com/gists/{gist_id}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {"files": {"backend_url.json": {"content": json.dumps({"url": new_url})}}}

    try:
        response = requests.patch(url, headers=headers, json=data)
        if response.status_code == 200:
            log_msg("[\u2713] Gist updated successfully! Frontend can now sync.")
        else:
            log_msg(f"[x] Failed to update Gist. HTTP Code: {response.status_code}")
    except Exception as e:
        log_msg(f"[x] Error connecting to GitHub API: {e}")

def update_cloudflare_kv(new_url, account_id, namespace_id, token):
    """Update the ACTIVE_BACKEND_URL key in Cloudflare KV."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/ACTIVE_BACKEND_URL"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain"
    }

    try:
        response = requests.put(url, headers=headers, data=new_url)
        if response.status_code == 200:
            log_msg("[\u2713] Cloudflare KV updated successfully (Zero Cache)!")
        else:
            log_msg(f"[x] Failed to update KV. HTTP Code: {response.status_code} - {response.text}")
    except Exception as e:
        log_msg(f"[x] Error connecting to Cloudflare API: {e}")

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
    
    # Route to the correct cloud sync provider
    mode = app_config.get("mode")
    if mode == "gist":
        log_msg("[*] Syncing with GitHub Gist...")
        update_github_gist(new_url, app_config["github_token"], app_config["gist_id"])
    elif mode == "kv":
        log_msg("[*] Syncing with Cloudflare KV...")
        update_cloudflare_kv(new_url, app_config["cf_account_id"], app_config["cf_namespace_id"], app_config["cf_token"])

def run_cloudflared():
    """Start Cloudflared and monitor output."""
    global cloudflared_process
    command = ["cloudflared.exe", "tunnel", "--url", f"localhost:{PORT}"]

    cloudflared_process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
        text=True, bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

    url_pattern = re.compile(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)")
    log_msg("[*] Waiting for Cloudflare URL...")

    for line in iter(cloudflared_process.stdout.readline, ''):
        match = url_pattern.search(line)
        if match:
            new_url = match.group(1)
            log_msg(f"\n[+] Captured New URL:\n{new_url}\n")
            update_env(new_url)

    cloudflared_process.stdout.close()
    cloudflared_process.wait()

def watchdog_loop():
    """Self-monitoring loop in a background thread."""
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
    def __init__(self):
        self.config = load_config()
        self.user_data = None
        self.root = tk.Tk()
        self.root.title("Cloudflare Sync Settings")
        
        w, h = 500, 550
        ws, hs = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry('%dx%d+%d+%d' % (w, h, (ws/2)-(w/2), (hs/2)-(h/2)))
        
        tk.Label(self.root, text="Select Operation Mode:", font=("Arial", 11, "bold")).pack(pady=(15, 5))
        self.mode_var = tk.StringVar(value=self.config.get("mode", "local"))
        
        # Radio Buttons
        tk.Radiobutton(self.root, text="Local Mode (Update .env only)", variable=self.mode_var, value="local", command=self.toggle_frames, font=("Arial", 10)).pack(anchor="w", padx=40)
        tk.Radiobutton(self.root, text="Remote Mode: GitHub Gist (Easy)", variable=self.mode_var, value="gist", command=self.toggle_frames, font=("Arial", 10)).pack(anchor="w", padx=40)
        tk.Radiobutton(self.root, text="Remote Mode: Cloudflare KV (Advanced)", variable=self.mode_var, value="kv", command=self.toggle_frames, font=("Arial", 10)).pack(anchor="w", padx=40)

        # Gist Frame
        self.gist_frame = tk.Frame(self.root)
        tk.Label(self.gist_frame, text="GitHub Username:", font=("Arial", 9)).pack(anchor="w", pady=(10, 0))
        self.entry_user = tk.Entry(self.gist_frame, width=50, font=("Arial", 10))
        self.entry_user.pack(pady=(0, 5))
        self.entry_user.insert(0, self.config.get("github_username", ""))

        tk.Label(self.gist_frame, text="Personal Access Token (Gist Scope):", font=("Arial", 9)).pack(anchor="w")
        self.entry_token = tk.Entry(self.gist_frame, width=50, font=("Arial", 10), show="*")
        self.entry_token.pack(pady=(0, 5))
        self.entry_token.insert(0, self.config.get("github_token", ""))

        tk.Label(self.gist_frame, text="Gist ID:", font=("Arial", 9)).pack(anchor="w")
        self.entry_gist = tk.Entry(self.gist_frame, width=50, font=("Arial", 10))
        self.entry_gist.pack(pady=(0, 10))
        self.entry_gist.insert(0, self.config.get("gist_id", ""))

        # KV Frame
        self.kv_frame = tk.Frame(self.root)
        tk.Label(self.kv_frame, text="CF Account ID:", font=("Arial", 9)).pack(anchor="w", pady=(10, 0))
        self.entry_account = tk.Entry(self.kv_frame, width=50, font=("Arial", 10))
        self.entry_account.pack(pady=(0, 5))
        self.entry_account.insert(0, self.config.get("cf_account_id", ""))

        tk.Label(self.kv_frame, text="KV Namespace ID:", font=("Arial", 9)).pack(anchor="w")
        self.entry_namespace = tk.Entry(self.kv_frame, width=50, font=("Arial", 10))
        self.entry_namespace.pack(pady=(0, 5))
        self.entry_namespace.insert(0, self.config.get("cf_namespace_id", ""))

        tk.Label(self.kv_frame, text="API Token (Edit KV Scope):", font=("Arial", 9)).pack(anchor="w")
        self.entry_cf_token = tk.Entry(self.kv_frame, width=50, font=("Arial", 10), show="*")
        self.entry_cf_token.pack(pady=(0, 5))
        self.entry_cf_token.insert(0, self.config.get("cf_token", ""))

        tk.Label(self.kv_frame, text="Your Worker URL (For JS Snippet):", font=("Arial", 9)).pack(anchor="w")
        self.entry_worker = tk.Entry(self.kv_frame, width=50, font=("Arial", 10))
        self.entry_worker.pack(pady=(0, 10))
        self.entry_worker.insert(0, self.config.get("cf_worker_url", ""))
        
        # Generator Button for JS Snippet
        self.btn_generate = tk.Button(self.root, text="< / > Generate Integration Code", command=self.generate_code, bg="#f0f0f0")
        
        self.toggle_frames()

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=20, side=tk.BOTTOM)
        tk.Button(btn_frame, text="✅ Start System", command=self.on_confirm, bg="#4CAF50", fg="white", width=15, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=10)
        
        self.root.mainloop()

    def toggle_frames(self):
        """Dynamically switch inputs based on the selected mode."""
        mode = self.mode_var.get()
        self.gist_frame.pack_forget()
        self.kv_frame.pack_forget()
        self.btn_generate.pack_forget()

        if mode == "gist":
            self.gist_frame.pack(pady=5, fill="x", padx=40)
            self.btn_generate.pack(pady=10)
        elif mode == "kv":
            self.kv_frame.pack(pady=5, fill="x", padx=40)
            self.btn_generate.pack(pady=10)

    def generate_code(self):
        """Generates JS snippet for React/Vue/JS dynamically based on selected mode."""
        mode = self.mode_var.get()
        code = ""

        if mode == "gist":
            user = self.entry_user.get().strip()
            gist = self.entry_gist.get().strip()
            if not user or not gist:
                messagebox.showwarning("Warning", "Please enter GitHub Username and Gist ID.")
                return
            code = f"""// --- GitHub Gist Integration ---
const GITHUB_USERNAME = "{user}";
const GIST_ID = "{gist}";

export async function getActiveBackendUrl() {{
    try {{
        const cacheBuster = new Date().getTime();
        const RAW_URL = `https://gist.githubusercontent.com/${{GITHUB_USERNAME}}/${{GIST_ID}}/raw/backend_url.json?t=${{cacheBuster}}`;
        const response = await fetch(RAW_URL);
        const data = await response.json();
        return data.url; 
    }} catch (error) {{
        console.error("Fetch error:", error);
        return null;
    }}
}}"""
        elif mode == "kv":
            worker_url = self.entry_worker.get().strip()
            if not worker_url:
                messagebox.showwarning("Warning", "Please enter your Worker URL to generate the snippet.")
                return
            
            code = f"""/* 
--- Cloudflare KV Integration ---

STEP 1: Deploy this code to your Cloudflare Worker:
export default {{
  async fetch(request, env) {{
    const url = await env.YOUR_KV_BINDING.get("ACTIVE_BACKEND_URL");
    return new Response(JSON.stringify({{ url }}), {{
      headers: {{ "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }}
    }});
  }}
}}

STEP 2: Use this snippet in your Frontend:
*/

const WORKER_URL = "{worker_url}";

export async function getActiveBackendUrl() {{
    try {{
        // KV has eventual consistency, but no aggressive browser caching needed
        const response = await fetch(WORKER_URL);
        const data = await response.json();
        return data.url; 
    }} catch (error) {{
        console.error("Fetch error:", error);
        return null;
    }}
}}"""
            
        code_win = tk.Toplevel(self.root)
        code_win.title("Integration Code")
        txt = scrolledtext.ScrolledText(code_win, wrap="word", height=25, width=80, font=("Courier", 10))
        txt.pack(padx=10, pady=10)
        txt.insert("1.0", code)
        txt.config(state="disabled")

    def on_confirm(self):
        selected_mode = self.mode_var.get()
                
        self.user_data = {
            "mode": selected_mode,
            "github_username": self.entry_user.get().strip(),
            "github_token": self.entry_token.get().strip(),
            "gist_id": self.entry_gist.get().strip(),
            "cf_account_id": self.entry_account.get().strip(),
            "cf_namespace_id": self.entry_namespace.get().strip(),
            "cf_token": self.entry_cf_token.get().strip(),
            "cf_worker_url": self.entry_worker.get().strip()
        }
        save_config(self.user_data)
        self.root.destroy()

class MonitorUI:
    def __init__(self, root):
        self.root = root
        self.root.title("System Monitor - Cloudflare Sync")
        self.root.geometry("600x400")
        self.root.configure(bg="#1e1e1e")
        
        mode_label = tk.Label(root, text=f"Mode: {app_config['mode'].upper()}", bg="#1e1e1e", fg="#4CAF50", font=("Arial", 12, "bold"))
        mode_label.pack(pady=10)

        self.console = scrolledtext.ScrolledText(root, state='disabled', bg="#000000", fg="#00FF00", font=("Consolas", 10), wrap=tk.WORD)
        self.console.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def append_log(self, msg):
        self.root.after(0, self._insert_text, msg)

    def _insert_text(self, msg):
        self.console.config(state='normal')
        self.console.insert(tk.END, msg + "\n")
        self.console.see(tk.END)
        self.console.config(state='disabled')

    def on_closing(self):
        self.append_log("\n[!] Shutting down system...")
        global cloudflared_process
        if cloudflared_process:
            cloudflared_process.terminate()
        self.root.destroy()
        sys.exit()

if __name__ == "__main__":
    setup = SetupUI()
    if not setup.user_data:
        sys.exit()
        
    app_config.update(setup.user_data)

    root = tk.Tk()
    monitor_app = MonitorUI(root)
    
    worker_thread = threading.Thread(target=watchdog_loop, daemon=True)
    worker_thread.start()

    root.mainloop()