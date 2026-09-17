import socket
import threading
import usb.core
import usb.util

USB_VID = 0x1edb
USB_PID = 0xbd25
TCP_PORT = 9990

NUM_INPUTS = 16
NUM_OUTPUTS = 16

dev = None
usb_lock = threading.Lock()

def init_usb():
    global dev
    with usb_lock:
        try:
            dev = usb.core.find(idVendor=USB_VID, idProduct=USB_PID)
            if dev is None:
                print("[USB ERROR] Videohub per USB nicht gefunden.")
                return False
            
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
                
            dev.set_configuration()
            usb.util.claim_interface(dev, 0)
            print("[USB INFO] Videohub erfolgreich initialisiert.")
            return True
        except Exception as e:
            print(f"[USB ERROR] Init fehlgeschlagen: {e}")
            dev = None
            return False

def send_to_hardware(output_idx, input_idx):
    global dev
    with usb_lock:
        if dev is None:
            if not init_usb():
                return False
        try:
            # Ethernet Protocol nutzt 0-basierte Indizes (0 = Port 1).
            # USB Mapping: Inputs = 0-15, Outputs = 16-31.
            hw_input = input_idx
            hw_output = output_idx + 16

            # Der entschlüsselte Control-Transfer
            dev.ctrl_transfer(0xc0, 215, hw_input, hw_output, 1, timeout=1000)
            print(f"[ROUTING] Output {output_idx + 1} <- Input {input_idx + 1} geschaltet.")
            return True
            
        except Exception as e:
            print(f"[USB WRITE ERROR] {e} -> Setze USB zurück.")
            try:
                usb.util.dispose_resources(dev)
            except:
                pass
            dev = None
            return False

def handle_client(client_socket, addr):
    print(f"[TCP] Control Software verbunden: {addr[0]}")
    try:
        # 1. Preamble als reinen Text aufbauen
        preamble = (
            "PROTOCOL: Videohub\n"
            "VERSION: 2.8\n"
            "DEVICENAME: Pi USB Bridge\n"
            f"VIDEO INPUTS: {NUM_INPUTS}\n"
            f"VIDEO OUTPUTS: {NUM_OUTPUTS}\n\n"
        )
        
        preamble += "INPUT LABELS:\n"
        for i in range(NUM_INPUTS):
            preamble += f"{i} Input {i+1}\n"
        preamble += "\n"
        
        preamble += "OUTPUT LABELS:\n"
        for i in range(NUM_OUTPUTS):
            preamble += f"{i} Output {i+1}\n"
        preamble += "\n"
        
        preamble += "VIDEO OUTPUT ROUTING:\n"
        for i in range(NUM_OUTPUTS):
            preamble += f"{i} {i}\n"
        preamble += "\n"
        
        preamble += "VIDEO OUTPUT LOCKS:\n"
        for i in range(NUM_OUTPUTS):
            preamble += f"{i} U\n"
        preamble += "\n"

        # Alles auf einmal in Bytes umwandeln und senden
        client_socket.sendall(preamble.encode('utf-8'))

        # 2. Befehle empfangen
        buffer = b""
        while True:
            data = client_socket.recv(1024)
            if not data:
                break
            buffer += data
            
            while b"\n\n" in buffer:
                block, buffer = buffer.split(b"\n\n", 1)
                lines = block.decode('utf-8', errors='ignore').strip().split('\n')
                
                if not lines:
                    continue
                    
                header = lines[0].strip()
                
                if header == "VIDEO OUTPUT ROUTING:":
                    for line in lines[1:]:
                        parts = line.split()
                        if len(parts) == 2:
                            try:
                                out_idx = int(parts[0])
                                in_idx = int(parts[1])
                                if send_to_hardware(out_idx, in_idx):
                                    client_socket.sendall(b"ACK\n\n")
                                else:
                                    client_socket.sendall(b"NAK\n\n")
                            except ValueError:
                                pass
                elif header == "PING:":
                    client_socket.sendall(b"ACK\n\n")

    except Exception as e:
        print(f"[TCP ERROR] {addr[0]}: {e}")
    finally:
        client_socket.close()
        print(f"[TCP] Verbindung getrennt: {addr[0]}")

def main():
    init_usb()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", TCP_PORT))
    server.listen(5)
    print(f"[SERVER] Blackmagic Bridge läuft auf Port {TCP_PORT}...")

    while True:
        client, addr = server.accept()
        threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()

if __name__ == "__main__":
    main()
