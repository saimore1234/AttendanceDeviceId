# Attendance Device Integration - Local Agent

Use this when ERPNext is **not** on the same network as the attendance
device (e.g. the device is at a branch office, ERPNext is hosted
elsewhere). Install this on any PC that IS on the same network as the
device - it relays the connection so ERPNext never needs direct access
to the device's local IP.

## Install (on the PC at the device's location)

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Configure

```bash
copy config.example.json config.json
```

Edit `config.json` and set a long random `token`.

## Run

```bash
python agent.py --config config.json
```

Leave this running. For it to be reachable from your ERPNext server
(which is somewhere else on the internet), you need ONE of:
- Port-forward this PC's `8585` on the office router to a port on the
  office's public IP, or
- Run this behind a reverse-tunnel service (e.g. Cloudflare Tunnel,
  ngrok, Tailscale) if you don't control the office router, or
- A VPN connecting the ERPNext server's network to this one.

Whichever you choose, you end up with a URL ERPNext can reach - e.g.
`http://<office-public-ip>:8585` or `https://your-tunnel-name.example.com`.

## Configure in ERPNext

On the **Attendance Device** record:
- Connection Mode: **Local Agent**
- Local Agent URL: the URL from above
- IP Address / Port: still the device's LOCAL IP (e.g. `192.168.0.56:4370`)
  - this is what the agent itself uses to reach the device, not what
    ERPNext uses to reach the agent.

On the **Attendance Device Credential** record for this device:
- Bearer Token: the same token you put in `config.json`

Then Test Connection from the Attendance Device form works exactly as
if the device were local - ERPNext calls the agent, the agent calls the
device, the result comes back through the same chain.

## Run as a Windows service (optional)

Simplest approach: [NSSM](https://nssm.cc/) -
`nssm install AttendanceAgent "C:\path\to\venv\Scripts\python.exe" "C:\path\to\agent.py --config C:\path\to\config.json"`

## Security notes

- Always set a `token` - without one, anyone who can reach this agent's
  port can query/command the device.
- Prefer a tunnel service with TLS (Cloudflare Tunnel, Tailscale) over
  plain port-forwarding if the device/network is sensitive - this agent
  itself serves plain HTTP.
- The agent never logs passwords/tokens.
