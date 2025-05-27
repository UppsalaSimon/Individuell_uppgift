import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import threading
import core_deploy

core_deploy.setup_logging()
vm = core_deploy.CONFIG["vms"][0]
user_password = ""

def set_password(pw):
    global user_password
    user_password = pw

def ask_password():
    global user_password
    pw = simpledialog.askstring("Lösenfras", "Ange lösenfras för SSH-nyckel:", show="*")
    if pw is not None:
        set_password(pw)

def start_deployment():
    def deploy_thread():
        core_deploy.log("🛠️ Startar deployment …")
        # Snapshot före deployment
        snapshot_name = core_deploy.auto_snapshot(vm)
        if not core_deploy.start_vm(vm):
            return
        if core_deploy.wait_for_ssh(vm["ssh_host"]):
            ssh = core_deploy.connect_ssh(vm, password=user_password)
            if ssh:
                ok = core_deploy.deploy(ssh, vm)
                ssh.close()
                if not ok:
                    rollback_snapshot(snapshot_name)
    threading.Thread(target=deploy_thread).start()

def rollback_snapshot(snapshot_name=None):
    def rollback_thread():
        if not snapshot_name:
            snap = core_deploy.latest_snapshot(vm)
        else:
            snap = snapshot_name
        if snap:
            core_deploy.rollback_snapshot(vm, snap)
            messagebox.showinfo("Rollback", f"Återställde snapshot: {snap}")
        else:
            messagebox.showerror("Rollback", "Ingen snapshot hittades att återställa.")
    threading.Thread(target=rollback_thread).start()

def test_ssh():
    core_deploy.log("🔌 Testar SSH …")
    if core_deploy.test_ssh(vm, password=user_password):
        messagebox.showinfo("SSH", "SSH fungerar!")
    else:
        messagebox.showerror("SSH", "SSH misslyckades.")

def install_tools():
    core_deploy.log("🔧 Installationsfunktion är under uppbyggnad.")
    messagebox.showinfo("Installera verktyg", "Funktionen kommer i framtiden!")

def shutdown_vm():
    core_deploy.log("🛑 Försöker stänga av VM …")
    core_deploy.shutdown_vm(vm)

def show_logs():
    path = core_deploy.CONFIG["rapportfil"]
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin1") as f:
            content = f.read()
    except Exception as e:
        messagebox.showerror("Fel vid loggläsning", str(e))
        return
    top = tk.Toplevel()
    top.title("Loggfil")
    text = tk.Text(top, wrap="word", width=100, height=30)
    text.insert("1.0", content)
    text.pack()

def get_system_status():
    def thread():
        ssh = core_deploy.connect_ssh(vm, password=user_password)
        if not ssh:
            messagebox.showerror("Systemstatus", "Kunde inte ansluta till VM via SSH.")
            return
        sysinfo = core_deploy.get_system_status(ssh)
        ssh.close()
        top = tk.Toplevel()
        top.title("Systemstatus/Loggar")
        text = tk.Text(top, wrap="word", width=100, height=30)
        text.insert("1.0", sysinfo)
        text.pack()
    threading.Thread(target=thread).start()

def upload_file():
    local_path = filedialog.askopenfilename(title="Välj fil att ladda upp")
    if not local_path:
        return
    remote_path = simpledialog.askstring("Fjärrsökväg", "Ange fjärrsökväg (t.ex. /home/user/fil.txt):")
    if not remote_path:
        return
    def thread():
        ssh = core_deploy.connect_ssh(vm, password=user_password)
        if not ssh:
            messagebox.showerror("Upload", "Kunde inte ansluta till VM via SSH.")
            return
        ok = core_deploy.upload_file(ssh, local_path, remote_path)
        ssh.close()
        if ok:
            messagebox.showinfo("Upload", f"Uppladdning klar: {local_path} → {remote_path}")
        else:
            messagebox.showerror("Upload", "Fel vid uppladdning.")
    threading.Thread(target=thread).start()

def download_file():
    remote_path = simpledialog.askstring("Ladda ner fil", "Ange fjärrsökväg att ladda ner (t.ex. /home/user/fil.txt):")
    if not remote_path:
        return
    local_path = filedialog.asksaveasfilename(title="Spara fil som")
    if not local_path:
        return
    def thread():
        ssh = core_deploy.connect_ssh(vm, password=user_password)
        if not ssh:
            messagebox.showerror("Download", "Kunde inte ansluta till VM via SSH.")
            return
        ok = core_deploy.download_file(ssh, remote_path, local_path)
        ssh.close()
        if ok:
            messagebox.showinfo("Download", f"Nedladdning klar: {remote_path} → {local_path}")
        else:
            messagebox.showerror("Download", "Fel vid nedladdning.")
    threading.Thread(target=thread).start()

def manage_service():
    service = simpledialog.askstring("Tjänsthantering", "Ange tjänstnamn (t.ex. apache2):")
    if not service:
        return
    action = simpledialog.askstring("Åtgärd", "Ange åtgärd (start, stop, restart, status):")
    if not action:
        return
    def thread():
        ssh = core_deploy.connect_ssh(vm, password=user_password)
        if not ssh:
            messagebox.showerror("Tjänsthantering", "Kunde inte ansluta till VM via SSH.")
            return
        out, err = core_deploy.manage_service(ssh, service, action)
        ssh.close()
        messagebox.showinfo("Tjänsthantering", f"STDOUT:\n{out}\n\nSTDERR:\n{err}")
    threading.Thread(target=thread).start()

def open_google():
    def thread():
        ssh = core_deploy.connect_ssh(vm, password=user_password)
        if not ssh:
            messagebox.showerror("Webbsida", "Kunde inte ansluta till VM via SSH.")
            return
        out, err = core_deploy.open_webpage(ssh)
        ssh.close()
        if err.strip() == "":
            messagebox.showinfo("Webbsida", f"Försökte öppna Google.\nResultat: {out}")
        else:
            messagebox.showwarning("Webbsida", f"Fel/varning: {err}\nResultat: {out}")
    threading.Thread(target=thread).start()

def create_gui():
    core_deploy.logging.debug("🧪 GUI: create_gui() körs...")
    window = tk.Tk()
    window.title("🖥️ Deployment GUI ver8")

    pw_label = tk.Label(window, text="Lösenfras för SSH-nyckel:")
    pw_label.pack()
    pw_entry = tk.Entry(window, show="*")
    pw_entry.pack()
    pw_entry.insert(0, user_password)

    def update_password(*args):
        set_password(pw_entry.get())
    pw_entry.bind("<KeyRelease>", update_password)

    tk.Button(window, text="🚀 Starta Deployment", width=30, command=start_deployment).pack(pady=5)
    tk.Button(window, text="🔌 Testa SSH", width=30, command=test_ssh).pack(pady=5)
    tk.Button(window, text="🔧 Installera Verktyg", width=30, command=install_tools).pack(pady=5)
    tk.Button(window, text="📖 Visa Loggar", width=30, command=show_logs).pack(pady=5)
    tk.Button(window, text="🗃️ Systemstatus/Loggar", width=30, command=get_system_status).pack(pady=5)
    tk.Button(window, text="⬆️ Ladda upp fil", width=30, command=upload_file).pack(pady=5)
    tk.Button(window, text="⬇️ Ladda ner fil", width=30, command=download_file).pack(pady=5)
    tk.Button(window, text="🔄 Hantera tjänst", width=30, command=manage_service).pack(pady=5)
    tk.Button(window, text="🌐 Öppna Google på VM", width=30, command=open_google).pack(pady=5)
    tk.Button(window, text="💾 Rollback (återställ snapshot)", width=30, command=rollback_snapshot).pack(pady=5)
    tk.Button(window, text="⏹️ Stäng av VM", width=30, command=shutdown_vm).pack(pady=5)
    tk.Button(window, text="❌ Avsluta", width=30, command=window.quit).pack(pady=5)
    window.mainloop()

if __name__ == "__main__":
    create_gui()