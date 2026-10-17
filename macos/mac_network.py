"""Use actual macOS interface netmasks, without changing network or proxy settings."""
import ipaddress
import re
import subprocess

PRIVATE = tuple(ipaddress.IPv4Network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def parse_broadcasts(text):
    result = {'255.255.255.255'}
    enabled = False
    for line in text.splitlines():
        header = re.match(r'^([\w.]+):.*<([^>]+)>', line)
        if header:
            flags = set(header[2].split(','))
            enabled = {'UP', 'BROADCAST'} <= flags and not {'LOOPBACK', 'POINTOPOINT'} & flags
            continue
        if not enabled:
            continue
        match = re.search(r'\binet (\d+(?:\.\d+){3}) netmask (0x[\da-fA-F]+|[\d.]+)', line)
        if not match:
            continue
        try:
            address = ipaddress.IPv4Address(match[1])
            if not any(address in n for n in PRIVATE):
                continue
            mask = str(ipaddress.IPv4Address(int(match[2], 16))) if match[2].startswith('0x') else match[2]
            network = ipaddress.IPv4Network(f'{address}/{mask}', strict=False)
            if network.prefixlen < 31:
                result.add(str(network.broadcast_address))
        except (ValueError, ipaddress.AddressValueError):
            continue
    return sorted(result)


def broadcast_targets(port):
    try:
        result = subprocess.run(['/sbin/ifconfig'], capture_output=True, text=True, timeout=3, check=True)
        addresses = parse_broadcasts(result.stdout)
    except (OSError, subprocess.SubprocessError):
        addresses = ['255.255.255.255']
    return [(a, port) for a in addresses]
