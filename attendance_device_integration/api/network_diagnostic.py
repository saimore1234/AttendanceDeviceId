import socket
import frappe

@frappe.whitelist()
def test_mantra_connection():
    device_ip = "192.168.0.2"
    device_port = 5005

    try:
        with socket.create_connection(
            (device_ip, device_port), timeout=5
        ):
            return {
                "status": "Connected",
                "message": f"ERPNext server can reach {device_ip}:{device_port}"
            }

    except Exception as e:
        return {
            "status": "Failed",
            "message": str(e)
        }