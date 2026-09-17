# rpi-videohub-control

A Python-based bridge that transforms a legacy, USB-only Blackmagic Design Studio Videohub into a modern, network-accessible routing matrix.

By reverse-engineering the proprietary USB control transfers and emulating the official Blackmagic Ethernet Videohub Protocol (TCP Port 9990), this bridge allows you to control your legacy hardware over the network.

## Features

- Full Network Emulation: Exposes TCP port 9990, mimicking a modern Blackmagic Ethernet Videohub.
- Plug & Play Client Support: Works seamlessly with the official Blackmagic Videohub Control app (Windows/Mac) and Bitfocus Companion.
- Real-Time Broadcast: If one client (or Companion) routes a signal, all other connected clients update their UI instantly.
- Lightweight: Runs perfectly on any Raspberry Pi (Zero, 3, 4, or 5).

## Hardware Requirements

- Raspberry Pi (running Raspberry Pi OS / Debian)
- Legacy Blackmagic Studio Videohub (USB interface, Vendor ID: 0x1edb, Product ID: 0xbd25)

## Installation & Raspberry Pi Setup

### 1. Install Dependencies

The script relies on `pyusb` to communicate with the hardware. Install the system package to avoid Python environment conflicts:

```bash
sudo apt update
sudo apt install python3-usb git -y
```

### 2. Configure USB Permissions (udev Rules)

By default, Linux requires root privileges to send raw USB commands. To allow the script to run as a standard user, create a udev rule for the Blackmagic Videohub:

```bash
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="1edb", ATTR{idProduct}=="bd25", MODE="0666"' | sudo tee /etc/udev/rules.d/99-blackmagic-usb.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Note: You may need to physically unplug and replug the USB cable once for the new permissions to apply.

### 3. Clone the Repository

```bash
cd ~
git clone https://github.com/floriandobler/rpi-videohub-control.git
cd rpi-videohub-control
```

### 4. Test the Bridge

Run the script manually to ensure everything is working:

```bash
python3 videohub_bridge.py
```

You should see:

```text
[USB INFO] Videohub erfolgreich initialisiert.
[SERVER] Blackmagic Bridge läuft auf Port 9990...
```

Open the Blackmagic Videohub Control app on your computer, enter the Raspberry Pi's IP address, and verify that the matrix loads and routes correctly.

## Run as a Background Service (Autostart)

To ensure the bridge starts automatically whenever the Raspberry Pi boots, set it up as a `systemd` service.

Create a new service file:

```bash
sudo nano /etc/systemd/system/videohub.service
```

Paste the following configuration (adjust `/home/pi/rpi-videohub-control` if your path or username is different):

```ini
[Unit]
Description=Blackmagic USB to Ethernet Videohub Bridge
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/rpi-videohub-control/videohub_bridge.py
WorkingDirectory=/home/pi/rpi-videohub-control
StandardOutput=inherit
StandardError=inherit
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable videohub.service
sudo systemctl start videohub.service
```

You can check the background logs at any time using:

```bash
sudo journalctl -u videohub.service -f
```

## Under the Hood: The USB Protocol

Legacy Videohubs do not use bulk endpoint payloads for routing. Instead, the routing command is encoded directly into the USB Control Transfer header (Endpoint 0).

The bridge translates the 0-based `VIDEO OUTPUT ROUTING` TCP commands into the following USB Control Transfer:

- `bmRequestType`: `0xc0` (Device to Host, Vendor, Device)
- `bRequest`: `215` (`0xd7`)
- `wValue`: Input Index (`0-15`)
- `wIndex`: Output Index (`16-31` for Outputs 1-16)
- `wLength`: `1 byte` (Status return)
