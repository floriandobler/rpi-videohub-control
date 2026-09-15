#!/usr/bin/env python3
"""
Blackmagic Studio Videohub 16x32 USB-to-LAN Bridge
Emuliert das Blackmagic Videohub Ethernet Protocol auf TCP Port 9990.
"""

import sys
import time
import serial
import threading
import socketserver

# --- CONFIGURATION ---
TCP_HOST = "0.0.0.0"
TCP_PORT = 9990
SERIAL_PORT = "/dev/ttyACM0"  # Oder /dev/ttyUSB0
BAUDRATE = 115200

NUM_INPUTS = 16
NUM_OUTPUTS = 32  # 16 Main + 16 Monitor Outputs

# Default Routing Table (Output -> Input)
routing_state = {out: out % NUM_INPUTS for out in range(NUM_OUTPUTS)}
labels_in = {i: f"Input {i+1}" for i in range(NUM_INPUTS)}
labels_out = {o: f"Output {o+1}" if o < 16 else f"Monitor {o-15}" for o in range(NUM_OUTPUTS)}

lock = threading.Lock()
clients = []
serial_conn = None

# --- SERIAL HANDLING ---
import usb.core
import usb.util

dev = None

def init_bm_usb():
    global dev
    # Sucht den Blackmagic Studio Videohub anhand von VendorID und ProductID
    dev = usb.core.find(idVendor=0x1edb, idProduct=0xbd25)
    if dev is None:
        print("[USB WARNING] Videohub nicht per USB gefunden!")
        return False
    
    try:
        # Falls der Kernel-Treiber aktiv ist, diesen kurz trennen
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except Exception:
        pass

    try:
        dev.set_configuration()
        print("[USB INFO] Videohub erfolgreich initialisiert.")
        return True
    except Exception as e:
        print(f"[USB ERROR] Konnte Konfiguration nicht setzen: {e}")
        return False
        
# Videohub initialisieren
dev = usb.core.find(idVendor=0x1edb, idProduct=0xbd25)
if dev:
    try:
        dev.set_configuration()
    except Exception:
        pass

def send_to_hardware(output_idx, input_idx):
    if dev is None:
        print("[USB ERROR] Kein Videohub verbunden!")
        return

    try:
        # Sicherstellen, dass wir im gültigen Bereich bleiben (mindestens 0)
        hw_input = max(0, input_idx - 1)
        hw_output = max(0, output_idx - 1)

        packet = bytearray([
            0x1c, 0x00, 0x20, 0x07, 0x1e, 0x10, 0x02, 0xc8, 
            0xff, 0xff, 0x00, 0x00, 0x00, 0x00, 0x17, 0x00,
            0x00, 0x01, 0x00, 0x08, 0x00, 0x80, 0x02, 0x08, 
            0x00, 0x00, 0x00, 0x00, 0xc0, 0xd7, hw_input, 0x00,
            0x10, 0x00, 0x01, 0x00
        ])

        # Befehl senden
        dev.write(0x02, packet, timeout=1000)
        
        # WICHTIG: Puffer / Antwort kurz abholen (Endpoint 0x86 IN), 
        # damit der USB-Controller des Hubs nicht in den Timeout läuft!
        try:
            dev.read(0x86, 64, timeout=100)
        except Exception:
            pass # Timeout beim Lesen ist hier egal, Hauptsache der Puffer ist frei

        print(f"[USB HARDWARE CUT] Output {output_idx} <- Input {input_idx} (Hex-Input: {hw_input:02x})")
        
    except Exception as e:
        print(f"[USB WRITE ERROR] {e}")

# --- PROTOCOL EMULATION ---
def build_initial_dump():
    """Generiert den initialen Status-Dump für neu verbundene TCP-Clients."""
    lines = [
        "PROTOCOL PREAMBLE:",
        "Version: 2.4",
        "",
        "VIDEOHUB DEVICE:",
        "Device present: true",
        "Model name: Blackmagic Studio Videohub",
        f"Video inputs: {NUM_INPUTS}",
        f"Video processing units: 0",
        f"Video outputs: {NUM_OUTPUTS}",
        f"Video monitoring outputs: 0",
        "Serial ports: 0",
        "",
        "INPUT LABELS:"
    ]
    for i in range(NUM_INPUTS):
        lines.append(f"{i} {labels_in[i]}")
    lines.append("")

    lines.append("OUTPUT LABELS:")
    for o in range(NUM_OUTPUTS):
        lines.append(f"{o} {labels_out[o]}")
    lines.append("")

    lines.append("VIDEO OUTPUT ROUTING:")
    with lock:
        for o in range(NUM_OUTPUTS):
            lines.append(f"{o} {routing_state[o]}")
    lines.append("")
    lines.append("") # Protokoll verlangt Doppel-Blankline am Ende des Blocks
    return "\n".join(lines).encode('ascii')

def broadcast_update(message):
    """Sendet Routing-Änderungen an alle verbundenen TCP-Clients (z.B. Companion)."""
    with lock:
        to_remove = []
        for client in clients:
            try:
                client.sendall(message.encode('ascii'))
            except Exception:
                to_remove.append(client)
        for client in to_remove:
            if client in clients:
                clients.remove(client)

# --- TCP HANDLER ---
class VideohubTCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        print(f"[TCP] Client verbunden: {self.client_address[0]}")
        with lock:
            clients.append(self.request)

        # Initialen Dump senden
        self.request.sendall(build_initial_dump())

        buffer = ""
        while True:
            try:
                data = self.request.recv(1024)
                if not data:
                    break
                buffer += data.decode('ascii', errors='ignore')

                # Befehlsblöcke verarbeiten (getrennt durch doppeltes Linebreak)
                while "\n\n" in buffer:
                    block, buffer = buffer.split("\n\n", 1)
                    self.parse_block(block)

            except Exception as e:
                print(f"[TCP ERROR] {e}")
                break

        print(f"[TCP] Client getrennt: {self.client_address[0]}")
        with lock:
            if self.request in clients:
                clients.remove(self.request)

    def parse_block(self, block):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            return

        header = lines[0]
        if header == "VIDEO OUTPUT ROUTING:":
            updates = []
            for line in lines[1:]:
                parts = line.split()
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    out_idx = int(parts[0])
                    in_idx = int(parts[1])

                    if 0 <= out_idx < NUM_OUTPUTS and 0 <= in_idx < NUM_INPUTS:
                        with lock:
                            routing_state[out_idx] = in_idx
                        send_to_hardware(out_idx, in_idx)
                        updates.append(f"{out_idx} {in_idx}")

            if updates:
                # Broadcast an alle anderen Netzwerk-Teilnehmer
                broadcast_msg = "VIDEO OUTPUT ROUTING:\n" + "\n".join(updates) + "\n\n"
                broadcast_update(broadcast_msg)

# Threaded TCP Server
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

# --- MAIN ---
if __name__ == "__main__":
    init_bm_usb()
    
    server = ThreadedTCPServer((TCP_HOST, TCP_PORT), VideohubTCPHandler)
    print(f"[SERVER] Blackmagic Videohub Bridge läuft auf Port {TCP_PORT}...")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SERVER] Beenden...")
        if serial_conn and serial_conn.is_open:
            serial_conn.close()
        server.shutdown()
        sys.exit(0)
