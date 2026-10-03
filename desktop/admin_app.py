import argparse, os, tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
import requests

class AdminApp:
    def __init__(self, root, server, token):
        self.root = root
        self.root.title("Print Admin")
        self.root.geometry("1000x620")
        self.server = server.rstrip("/")
        self.jobs = {}
        top = ttk.Frame(root, padding=10); top.pack(fill="x")
        ttk.Label(top, text="Server URL").pack(side="left")
        self.server_var = tk.StringVar(value=self.server)
        ttk.Entry(top, textvariable=self.server_var, width=36).pack(side="left", padx=5)
        ttk.Label(top, text="Admin token").pack(side="left")
        self.token_var = tk.StringVar(value=token)
        ttk.Entry(top, textvariable=self.token_var, width=24, show="*").pack(side="left", padx=5)
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="left", padx=5)
        cols = ("id", "name", "status", "pages", "orientation", "duplex", "copies", "created")
        self.tree = ttk.Treeview(root, columns=cols, show="headings", selectmode="browse")
        labels = {"id":"ID","name":"Document","status":"Status","pages":"Pages/sheet","orientation":"Orientation","duplex":"Duplex","copies":"Copies","created":"Submitted"}
        widths = {"id":50,"name":240,"status":100,"pages":90,"orientation":90,"duplex":70,"copies":60,"created":150}
        for col in cols:
            self.tree.heading(col, text=labels[col]); self.tree.column(col, width=widths[col], anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        bar = ttk.Frame(root, padding=10); bar.pack(fill="x")
        ttk.Button(bar, text="Approve", command=self.approve).pack(side="left", padx=4)
        ttk.Button(bar, text="Reject", command=self.reject).pack(side="left", padx=4)
        ttk.Button(bar, text="Download / Print", command=self.print_selected).pack(side="left", padx=4)
        ttk.Button(bar, text="Mark completed & delete server file", command=self.complete).pack(side="left", padx=4)
        self.status = tk.StringVar(value="Ready")
        ttk.Label(root, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", side="bottom")
        self.refresh()
        self.root.after(15000, self.periodic_refresh)

    def request(self, method, path, **kwargs):
        return requests.request(method, self.server_var.get().rstrip("/") + path,
            headers={"X-Admin-Token": self.token_var.get()}, timeout=30, **kwargs)

    def refresh(self):
        try:
            r = self.request("GET", "/api/admin/requests"); r.raise_for_status()
            jobs = r.json(); self.jobs = {j["id"]: j for j in jobs}
            for item in self.tree.get_children(): self.tree.delete(item)
            for j in jobs:
                self.tree.insert("", "end", iid=str(j["id"]), values=(
                    j["id"], j["original_name"], j["status"], j.get("pages_per_sheet", j.get("pages", 1)),
                    j["orientation"], "Yes" if j["duplex"] else "No", j["copies"], j.get("created_at", "")))
            self.status.set(f"{len(jobs)} request(s) loaded")
        except Exception as e:
            self.status.set("Connection error: " + str(e))

    def selected(self):
        ids = self.tree.selection()
        if not ids:
            messagebox.showinfo("Select request", "Please select a request first.")
            return None
        return int(ids[0])

    def approve(self):
        jid = self.selected()
        if jid is None: return
        try:
            r = self.request("POST", f"/api/admin/requests/{jid}/approve"); r.raise_for_status()
            self.refresh()
        except Exception as e: messagebox.showerror("Approve failed", str(e))

    def reject(self):
        jid = self.selected()
        if jid is None: return
        reason = simpledialog.askstring("Reject request", "Reason (optional):", parent=self.root) or "Rejected by admin"
        try:
            r = self.request("POST", f"/api/admin/requests/{jid}/reject", data={"reason": reason}); r.raise_for_status()
            self.refresh()
        except Exception as e: messagebox.showerror("Reject failed", str(e))

    def print_selected(self):
        jid = self.selected()
        if jid is None: return
        job = self.jobs.get(jid, {})
        if job.get("status") != "approved":
            messagebox.showwarning("Not approved", "Approve this request before printing.")
            return
        queue = Path.home() / "PrintingClient" / "offline_queue"
        queue.mkdir(parents=True, exist_ok=True)
        target = queue / (f"job_{jid}_" + Path(job.get("original_name", "document")).name)
        try:
            if not target.exists():
                r = self.request("GET", f"/api/desktop/jobs/{jid}/file"); r.raise_for_status()
                target.write_bytes(r.content)
            if os.name == "nt":
                os.startfile(str(target), "print")
                messagebox.showinfo("Print command sent", "Sent to the default application. Verify the physical print before marking completed.")
            else:
                messagebox.showinfo("Downloaded", f"File saved for manual printing: {target}")
        except Exception as e: messagebox.showerror("Print failed", str(e))

    def complete(self):
        jid = self.selected()
        if jid is None: return
        if not messagebox.askyesno("Confirm", "Only continue after verifying physical printing is complete. Mark completed and delete the server file?"):
            return
        try:
            r = self.request("POST", f"/api/desktop/jobs/{jid}/complete"); r.raise_for_status()
            self.refresh()
        except Exception as e: messagebox.showerror("Complete failed", str(e))

    def periodic_refresh(self):
        self.refresh()
        self.root.after(15000, self.periodic_refresh)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default=os.getenv("ADMIN_TOKEN", "change-me-now"))
    args = parser.parse_args()
    root = tk.Tk()
    AdminApp(root, args.server, args.token)
    root.mainloop()

if __name__ == "__main__":
    main()
