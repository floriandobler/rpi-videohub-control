# rpi-videohub-control

A lightweight Python bridge that turns a legacy Blackmagic Design Studio Videohub with a USB control interface into a network-accessible, Blackmagic-compatible routing matrix.

This project reverse-engineers the proprietary USB control transfers used by older Videohub models and emulates the Blackmagic Ethernet Videohub protocol on TCP port 9990. The result is that modern Blackmagic control software can talk to the device as if it were a standard Ethernet-enabled Videohub.

## Why this exists

Many older Blackmagic Videohub hardware units feature a USB control interface but no built-in Ethernet controller. That makes them awkward to integrate into modern broadcast workflows, especially when you want to use the standard Blackmagic Videohub control software or Bitfocus Companion from a networked environment.

`rpi-videohub-control` solves that by exposing the same protocol a modern Blackmagic Ethernet Videohub would expose, while translating routing commands to the USB control messages the hardware expects.

## Features

- Full network emulation of the Blackmagic Ethernet Videohub protocol on port 9990
- Compatibility with the official Blackmagic Videohub Control app
- Compatibility with Bitfocus Companion
- Real-time routing feedback across connected clients
- Lightweight enough to run on a Raspberry Pi Zero, 3, 4, or 5
- Works with legacy USB-only Studio Videohub hardware

## Supported hardware

This project targets legacy Blackmagic Studio Videohub devices using the USB control interface with the following identifiers:

- Vendor ID: `0x1edb`
- Product ID: `0xbd25`

## Requirements

- Raspberry Pi running Raspberry Pi OS / Debian
- Blackmagic Studio Videohub with USB interface
- Python 3
- `pyusb`

## Installation

### 1. Install system dependencies

```bash
sudo apt update
sudo apt install python3-usb git -y
```

### 2. Configure USB permissions

Linux usually requires elevated permissions for raw USB access. Create a udev rule so the device can be accessed without root:

```bash
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="1edb", ATTR{idProduct}=="bd25", MODE="0666"' | sudo tee /etc/udev/rules.d/99-blackmagic-usb.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

If the device was already connected, unplug and reconnect it once so the new permission rules take effect.

### 3. Clone the repository

```bash
cd ~
git clone https://github.com/floriandobler/rpi-videohub-control.git
cd rpi-videohub-control
```

### 4. Install Python dependencies

```bash
python3 -m pip install -r requirements.txt
```

### 5. Run the bridge

```bash
python3 videohub_bridge.py
```

Expected startup output:

```text
[USB INFO] Videohub successfully initialized.
[SERVER] Blackmagic bridge running on port 9990...
```

Open the Blackmagic Videohub Control app on your computer, connect to the Raspberry Pi's IP address, and verify that the matrix loads and routing works as expected.

## Running as a background service

To make the bridge start automatically on boot, install it as a `systemd` service.

Create a service file:

```bash
sudo nano /etc/systemd/system/videohub.service
```

Use the following configuration:

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

Then enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable videohub.service
sudo systemctl start videohub.service
```

Check logs with:

```bash
sudo journalctl -u videohub.service -f
```

## How it works

The bridge listens on TCP port 9990 and speaks the Blackmagic Ethernet Videohub protocol. When a client sends routing information, the script converts the requested output/input mapping into the corresponding USB control transfer used by the hardware.

The bridge also broadcasts routing updates to all connected clients so the state remains synchronized across multiple control surfaces.

## Protocol details

Legacy Videohub hardware does not use bulk endpoint payloads for routing. Instead, the routing change is encoded directly into the USB control transfer header.

This project translates the standard Blackmagic routing protocol into the equivalent USB request:

- `bmRequestType`: `0xc0` (Device to Host, Vendor, Device)
- `bRequest`: `215` (`0xd7`)
- `wValue`: Input index (`0-15`)
- `wIndex`: Output index (`16-31` for Outputs 1-16)
- `wLength`: `1 byte` (status return)

## Troubleshooting

### Device not found over USB

Check that:

- the Videohub is connected via USB
- the correct USB IDs are being used
- the udev rule was applied correctly
- the device was unplugged and reconnected after the rule was created

### Permission denied

Re-run the udev rule installation and unplug/reconnect the device.

### Control application cannot connect

Verify that:

- the Raspberry Pi is on the same network as the control machine
- the bridge is listening on port 9990
- the service is running if you are using the systemd setup

### Bridge starts but routing does not work

Check the Python output for USB initialization or transfer errors. The script logs failures to the terminal and resets the USB device if a transfer fails.

## Security note

The provided udev rule uses `MODE="0666"` for simplicity. This is suitable for a dedicated Raspberry Pi used as a single-purpose bridge, but a more restrictive group-based permission model may be preferable in shared or multi-user environments.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Notes

This project is intended for legacy Blackmagic Studio Videohub hardware that exposes a USB interface but lacks a native Ethernet control port. It is designed to let standard Blackmagic control clients operate the device as if it were a modern network-enabled Videohub.
