from zeroconf import ServiceInfo, Zeroconf
import socket
from typing import Optional


def _get_lan_ip() -> str:
    """
    Best-effort LAN IP (not 127.0.0.1).
    """
    try:
        # Connect to a public address without sending packets; OS picks the right NIC
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    return "127.0.0.1"


def start_mdns(port: int = 8000) -> Optional[Zeroconf]:
    """
    Advertise this device on the local network.
    Keep the returned Zeroconf object alive for the process lifetime.
    """
    try:
        local_ip = _get_lan_ip()
        print(f"mDNS using IP: {local_ip}")

        info = ServiceInfo(
            type_="_http._tcp.local.",
            name="ASPIREknowledge._http._tcp.local.",
            addresses=[socket.inet_aton(local_ip)],
            port=port,
            properties={
                b"path": b"/",
                b"name": b"ASPIREknowledge",
            },
            server="aspire-knowledge.local.",
        )

        zeroconf = Zeroconf()
        zeroconf.register_service(info)
        print(f"mDNS started → http://aspire-knowledge.local:{port}")
        print(f"Also try → http://{local_ip}:{port}")
        return zeroconf
    except Exception as e:
        print(f"mDNS failed to start (non-fatal): {e}")
        print("Devices can still connect via IP address.")
        return None