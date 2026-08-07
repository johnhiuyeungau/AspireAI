from zeroconf import ServiceInfo, Zeroconf
import socket

def start_mdns(port: int = 8000):
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    info = ServiceInfo(
        "_http._tcp.local.",
        "ASPIREknowledge._http._tcp.local.",
        addresses=[socket.inet_aton(local_ip)],
        port=port,
        properties={"path": "/", "name": "ASPIREknowledge"},
        server="aspire-knowledge.local.",
    )

    zeroconf = Zeroconf()
    zeroconf.register_service(info)
    print(f"mDNS started → http://aspire-knowledge.local:{port}")
    return zeroconf