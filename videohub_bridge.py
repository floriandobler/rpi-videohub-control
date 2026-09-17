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

# Global client list for broadcast feedback
active_clients = []
clients_lock = threading.Lock()

def init_usb():
    global dev
    with usb_lock:
        try:
            dev = usb.core.find(idVendor=USB_VID, idProduct=USB_PID)
            if dev is None:
                print("[USB ERROR] Videohub not found via USB.")
                return False

            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)

            dev.set_configuration()
            usb.util.claim_interface(dev, 0)
            print("[USB INFO] Videohub successfully initialized.")
            return True
        except Exception as e:
            print(f"[USB ERROR] Initialization failed: {e}")
            dev = None
            return False

def send_to_hardware(output_idx, input_idx):
    global dev
    with usb_lock:
        if dev is None:
            if not init_usb():
                return False
        try:
            dev.ctrl_transfer(0xc0, 215, input_idx, output_idx + 16, 1, timeout=1000)
            print(f"[ROUTING] Output {output_idx + 1} <- Input {input_idx + 1} switched.")
            return True
        except Exception as e:
            print(f"[USB WRITE ERROR] {e} -> Resetting USB.")
            try:
                usb.util.dispose_resources(dev)
            except:
                pass
            dev = None
            return False

def broadcast_routing_update(out_idx, in_idx):
    """Push the new state to all connected clients (Companion and software)."""
    update_msg = f"VIDEO OUTPUT ROUTING:\n{out_idx} {in_idx}\n\n".encode('ascii')
    with clients_lock:
        for client in active_clients:
            try:
                client.sendall(update_msg)
            except Exception:
                pass  # problematic sockets are cleaned up in their own thread


def handle_client(client_socket, addr):
    print(f"[TCP] Client connected: {addr[0]}")

    with clients_lock:
        active_clients.append(client_socket)

    try:
        # Preamble (strictly following the Blackmagic Ethernet Protocol specification)
        preamble = (
            "PROTOCOL: Videohub\n"
            "VERSION: 2.8\n\n"
            "VIDEOHUB DEVICE:\n"
            "Device present: true\n"
            "Model name: Pi USB Bridge\n"
            f"Video inputs: {NUM_INPUTS}\n"
            "Video processing units: 0\n"
            f"Video outputs: {NUM_OUTPUTS}\n"
            "Video monitoring outputs: 16\n"
            "Serial ports: 0\n\n"
            "INPUT LABELS:\n"
        )
        for i in range(NUM_INPUTS):
            preamble += f"{i} Input {i+1}\n"
        preamble += "\nOUTPUT LABELS:\n"

        for i in range(NUM_OUTPUTS):
            preamble += f"{i} Output {i+1}\n"
        preamble += "\nVIDEO OUTPUT ROUTING:\n"

        for i in range(NUM_OUTPUTS):
            preamble += f"{i} {i}\n"
        preamble += "\nVIDEO OUTPUT LOCKS:\n"

        for i in range(NUM_OUTPUTS):
            preamble += f"{i} U\n"
        preamble += "\n"

        client_socket.sendall(preamble.encode('utf-8'))

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
                                    # Send formal ACK to the sender
                                    client_socket.sendall(b"ACK\n\n")
                                    # Flash the new routing to all other clients (and the sender)
                                    broadcast_routing_update(out_idx, in_idx)
                                else:
                                    client_socket.sendall(b"NAK\n\n")
                            except ValueError:
                                pass
                elif header == "PING:":
                    client_socket.sendall(b"ACK\n\n")

    except Exception as e:
        print(f"[TCP ERROR] {addr[0]}: {e}")
    finally:
        with clients_lock:
            if client_socket in active_clients:
                active_clients.remove(client_socket)
        client_socket.close()
        print(f"[TCP] Connection closed: {addr[0]}")


def main():
    init_usb()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", TCP_PORT))
    server.listen(10)
    print(f"[SERVER] Blackmagic bridge running on port {TCP_PORT}...")

    while True:
        try:
            client, addr = server.accept()
            threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()
        except KeyboardInterrupt:
            print("\n[SERVER] Stopped manually.")
            break


if __name__ == "__main__":
    main()
