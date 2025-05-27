import os, time, socket, logging, paramiko, subprocess, yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(CONFIG_PATH, encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

def log(msg):
    logging.info(msg)
    print(msg)

def setup_logging():
    log_file = CONFIG["rapportfil"]
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

def start_vm(vm):
    exe = CONFIG["vmrun_exe"]
    log(f"Startar VM: {vm['name']}")
    if not os.path.exists(exe):
        log("❌ vmrun.exe inte hittad.")
        return False
    subprocess.Popen([exe, "start", vm["vmx_path"], "gui"])
    time.sleep(5)
    return True

def shutdown_vm(vm):
    exe = CONFIG["vmrun_exe"]
    if os.path.exists(exe):
        subprocess.call([exe, "stop", vm["vmx_path"], "soft"])
        log(f"🔻 VM {vm['name']} stängd.")

def wait_for_ssh(host, port=22, timeout=60):
    log(f"Väntar på SSH {host}:{port} …")
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            socket.create_connection((host, port), timeout=5).close()
            log("✅ SSH svarar!")
            return True
        except:
            time.sleep(2)
    log("❌ SSH-timeout.")
    return False

def connect_ssh(vm, password=None):
    pw = password
    if pw is None:
        import getpass
        pw = getpass.getpass(f"Lösenfras för {vm['ssh_user']}@{vm['ssh_host']}: ")

    try:
        key = None
        try:
            key = paramiko.Ed25519Key.from_private_key_file(vm["ssh_key_path"], password=pw)
        except Exception:
            key = paramiko.RSAKey.from_private_key_file(vm["ssh_key_path"], password=pw)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(vm["ssh_host"], username=vm["ssh_user"], pkey=key)
        log(f"✅ Ansluten via SSH till {vm['ssh_host']}")
        return ssh
    except Exception as e:
        log(f"❌ SSH-fel: {e}")
        return None

def deploy(ssh, vm):
    cmds = [
        "df -h /",
        "free -h",
        "uptime",
        "sudo apt update",
        "sudo apt install -y htop iftop net-tools",
        "top -bn1 | head -n 10",
        "ip -c a"
    ]
    for cmd in cmds:
        log(f"Kör: {cmd}")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        log(f"STDOUT:\n{out}")
        if err:
            log(f"STDERR:\n{err}")
        # Om något kommando misslyckas, returnera False för rollback
        if "fel" in out.lower() or "error" in out.lower() or "failed" in out.lower():
            return False
    return True

def test_ssh(vm, password=None):
    if wait_for_ssh(vm["ssh_host"]):
        ssh = connect_ssh(vm, password=password)
        if ssh:
            log("✅ SSH-test lyckades.")
            ssh.close()
            return True
    return False 

def get_system_status(ssh):
    cmds = [
        ("Diskanvändning (df -h /):", "df -h /"),
        ("Minne (free -h):", "free -h"),
        ("Uptime:", "uptime"),
        ("Topp 10 processer:", "top -bn1 | head -n 12"),
        ("IP-adresser:", "ip -c a"),
        ("Senaste systemlogg (tail -n 20 /var/log/syslog):", "tail -n 20 /var/log/syslog || tail -n 20 /var/log/messages"),
    ]
    result = ""
    for title, cmd in cmds:
        result += f"--- {title}\n"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        result += stdout.read().decode(errors="replace") + "\n"
    return result

def upload_file(ssh, local_path, remote_path):
    try:
        sftp = ssh.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()
        log(f"Uppladdad {local_path} → {remote_path}")
        return True
    except Exception as e:
        log(f"❌ Upload-fel: {e}")
        return False

def download_file(ssh, remote_path, local_path):
    try:
        sftp = ssh.open_sftp()
        sftp.get(remote_path, local_path)
        sftp.close()
        log(f"Nedladdad {remote_path} → {local_path}")
        return True
    except Exception as e:
        log(f"❌ Download-fel: {e}")
        return False

def manage_service(ssh, service, action):
    cmd = f"sudo systemctl {action} {service}"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    log(f"Tjänst [{service}] {action}:\nSTDOUT:\n{out}\nSTDERR:\n{err}")
    return out, err

# VM snapshot-funktioner
def auto_snapshot(vm):
    exe = CONFIG["vmrun_exe"]
    snap_name = "auto_snapshot_" + time.strftime("%Y%m%d_%H%M%S")
    cmd = [exe, "snapshot", vm["vmx_path"], snap_name]
    try:
        subprocess.check_call(cmd)
        log(f"Snapshot skapad: {snap_name}")
        return snap_name
    except Exception as e:
        log(f"❌ Fel vid snapshot: {e}")
        return None

def latest_snapshot(vm):
    exe = CONFIG["vmrun_exe"]
    cmd = [exe, "listSnapshots", vm["vmx_path"]]
    try:
        out = subprocess.check_output(cmd, universal_newlines=True)
        snaps = [l.strip() for l in out.splitlines() if l.strip() and "Total snapshots" not in l]
        if snaps:
            return snaps[-1]
        else:
            return None
    except Exception as e:
        log(f"❌ Kunde ej lista snapshots: {e}")
        return None

def rollback_snapshot(vm, snapshot_name):
    exe = CONFIG["vmrun_exe"]
    cmd = [exe, "revertToSnapshot", vm["vmx_path"], snapshot_name]
    try:
        subprocess.check_call(cmd)
        log(f"Återställde snapshot: {snapshot_name}")
        return True
    except Exception as e:
        log(f"❌ Fel vid rollback: {e}")
        return False

def open_webpage(ssh, url=None):
    # Om ingen URL anges, öppna Google
    if not url:
        url = "https://www.google.com/"
    cmd = f'DISPLAY=:0 firefox "{url}" &'
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    log(f"Öppnar webbsida: {url}\nstdout: {out}\nstderr: {err}")
    return out, err