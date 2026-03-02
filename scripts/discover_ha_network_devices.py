#!/usr/bin/env python3

"""Discover network devices similarly to Home Assistant network discovery.

Methods implemented:
- SSDP (active M-SEARCH)
- mDNS/Zeroconf (service discovery + service details)
- DHCP (optional passive sniff; requires scapy and elevated privileges)

Usage examples:
    python3 scripts/discover_ha_network_devices.py --timeout 8
    python3 scripts/discover_ha_network_devices.py --json
    sudo python3 scripts/discover_ha_network_devices.py --dhcp --timeout 20
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass, field
import json
import re
import socket
import subprocess
import sys
import time
from typing import Any

from zeroconf import IPVersion, ServiceBrowser, ServiceInfo, ServiceListener, Zeroconf

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SSDP_ST = "ssdp:all"

MDNS_SERVICES_ENUM = "_services._dns-sd._udp.local."


@dataclass
class SSDPDevice:
    usn: str
    st: str
    server: str | None
    location: str | None
    cache_control: str | None
    ext: str | None
    raw_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class MdnsService:
    service_type: str
    name: str
    server: str | None
    addresses: list[str]
    port: int | None
    properties: dict[str, str]


@dataclass
class DhcpObservation:
    mac: str
    hostname: str | None
    vendor_class: str | None
    yiaddr: str | None


def _normalize_mac(raw: str) -> str:
    return raw.strip().lower().replace("-", ":")


def _extract_mac_candidates(
    mdns: list[MdnsService], dhcp: list[DhcpObservation]
) -> set[str]:
    macs: set[str] = set()
    mac_re = re.compile(r"([0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}")

    for item in dhcp:
        if item.mac:
            macs.add(_normalize_mac(item.mac))

    for item in mdns:
        for text in (item.name, item.server or ""):
            for match in mac_re.findall(text):
                macs.add(_normalize_mac(match))
            full_matches = re.finditer(
                r"([0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}",
                text,
            )
            for fm in full_matches:
                macs.add(_normalize_mac(fm.group(0)))

    return macs


def _read_arp_table() -> dict[str, str]:
    table: dict[str, str] = {}
    commands = (["arp", "-an"], ["arp", "-a"])
    output = ""
    for cmd in commands:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.stdout:
                output = proc.stdout
                break
        except OSError:
            continue

    if not output:
        return table

    ip_re = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")
    mac_re = re.compile(r"([0-9a-fA-F]{2}(?:[:\-][0-9a-fA-F]{2}){5})")
    for line in output.splitlines():
        ip_m = ip_re.search(line)
        mac_m = mac_re.search(line)
        if not ip_m or not mac_m:
            continue
        table[_normalize_mac(mac_m.group(1))] = ip_m.group(1)

    return table


def _parse_ssdp_response(data: bytes) -> dict[str, str]:
    text = data.decode("utf-8", errors="ignore")
    lines = [line.strip() for line in text.split("\r\n") if line.strip()]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def discover_ssdp(timeout: float) -> list[SSDPDevice]:
    message = (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 3\r\n"
        f"ST: {SSDP_ST}\r\n"
        "\r\n"
    ).encode()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.settimeout(timeout)
    sock.sendto(message, (SSDP_ADDR, SSDP_PORT))

    found: dict[tuple[str, str], SSDPDevice] = {}
    start = time.monotonic()

    while time.monotonic() - start < timeout:
        try:
            data, _addr = sock.recvfrom(65535)
        except TimeoutError:
            break
        except OSError:
            break

        headers = _parse_ssdp_response(data)
        usn = headers.get("usn", "")
        st = headers.get("st", "")
        if not usn and not st:
            continue

        key = (usn, st)
        found[key] = SSDPDevice(
            usn=usn,
            st=st,
            server=headers.get("server"),
            location=headers.get("location"),
            cache_control=headers.get("cache-control"),
            ext=headers.get("ext"),
            raw_headers=headers,
        )

    sock.close()
    return list(found.values())


class _MdnsListener(ServiceListener):
    def __init__(self, zc: Zeroconf, results: dict[tuple[str, str], MdnsService]) -> None:
        self._zc = zc
        self._results = results

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:  # noqa: ARG002
        return

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:  # noqa: ARG002
        self._add_or_update(type_, name)

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:  # noqa: ARG002
        self._add_or_update(type_, name)

    def _add_or_update(self, type_: str, name: str) -> None:
        info: ServiceInfo | None = self._zc.get_service_info(type_, name, timeout=2000)
        if info is None:
            return

        properties: dict[str, str] = {}
        for key, value in info.properties.items():
            key_s = key.decode("utf-8", errors="ignore") if isinstance(key, bytes) else str(key)
            if isinstance(value, bytes):
                val_s = value.decode("utf-8", errors="ignore")
            else:
                val_s = str(value)
            properties[key_s.lower()] = val_s

        addresses = info.parsed_addresses(version=IPVersion.V4Only)
        addresses.extend(info.parsed_addresses(version=IPVersion.V6Only))

        key = (type_, name)
        self._results[key] = MdnsService(
            service_type=type_,
            name=name,
            server=info.server,
            addresses=addresses,
            port=info.port,
            properties=properties,
        )


class _ServiceTypeListener(ServiceListener):
    def __init__(self, discovered_types: set[str]) -> None:
        self.discovered_types = discovered_types

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:  # noqa: ARG002
        return

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:  # noqa: ARG002
        self._record(name)

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:  # noqa: ARG002
        self._record(name)

    def _record(self, name: str) -> None:
        n = name.rstrip(".")
        if n:
            if not n.endswith(".local"):
                n += ".local."
            elif not n.endswith("."):
                n += "."
            self.discovered_types.add(n)


def discover_mdns(timeout: float) -> list[MdnsService]:
    zc = Zeroconf()
    try:
        discovered_types: set[str] = set()
        type_listener = _ServiceTypeListener(discovered_types)
        enum_browser = ServiceBrowser(zc, MDNS_SERVICES_ENUM, type_listener)

        time.sleep(max(1.0, timeout / 2))

        results: dict[tuple[str, str], MdnsService] = {}
        listeners: list[_MdnsListener] = []
        browsers: list[ServiceBrowser] = [enum_browser]

        for service_type in sorted(discovered_types):
            listener = _MdnsListener(zc, results)
            listeners.append(listener)
            browsers.append(ServiceBrowser(zc, service_type, listener))

        time.sleep(max(2.0, timeout / 2))

        return sorted(results.values(), key=lambda x: (x.service_type, x.name))
    finally:
        zc.close()


def discover_dhcp(timeout: float) -> list[DhcpObservation]:
    try:
        from scapy.all import BOOTP, DHCP, Ether, sniff  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("DHCP sniffing requires scapy (`pip install scapy`) and root privileges") from exc

    found: dict[str, DhcpObservation] = {}

    def _mac_norm(mac: str) -> str:
        return mac.lower().replace("-", ":")

    def _packet_handler(pkt: Any) -> None:
        if DHCP not in pkt or BOOTP not in pkt:
            return
        mac = _mac_norm(pkt[Ether].src) if Ether in pkt else ""
        if not mac:
            return

        hostname = None
        vendor_class = None
        yiaddr = getattr(pkt[BOOTP], "yiaddr", None)

        options = pkt[DHCP].options
        if isinstance(options, list):
            for opt in options:
                if not isinstance(opt, tuple) or len(opt) < 2:
                    continue
                key, value = opt[0], opt[1]
                if key == "hostname":
                    hostname = value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else str(value)
                elif key == "vendor_class_id":
                    vendor_class = value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else str(value)

        found[mac] = DhcpObservation(
            mac=mac,
            hostname=hostname,
            vendor_class=vendor_class,
            yiaddr=yiaddr,
        )

    sniff(
        filter="udp and (port 67 or port 68)",
        prn=_packet_handler,
        store=False,
        timeout=timeout,
    )

    return list(found.values())


def _extract_possible_ave_hits(
    mdns: list[MdnsService], ssdp: list[SSDPDevice], dhcp: list[DhcpObservation]
) -> dict[str, list[dict[str, Any]]]:
    hits: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ave_pat = re.compile(r"ave|domina|dominaplus", re.IGNORECASE)

    for item in mdns:
        haystack = " ".join(
            [
                item.name,
                item.service_type,
                item.server or "",
                " ".join(f"{k}={v}" for k, v in item.properties.items()),
            ]
        )
        if ave_pat.search(haystack):
            hits["mdns"].append(asdict(item))

    for item in ssdp:
        haystack = " ".join(
            [
                item.usn,
                item.st,
                item.server or "",
                item.location or "",
                " ".join(f"{k}={v}" for k, v in item.raw_headers.items()),
            ]
        )
        if ave_pat.search(haystack):
            hits["ssdp"].append(asdict(item))

    for item in dhcp:
        haystack = " ".join([item.mac, item.hostname or "", item.vendor_class or "", item.yiaddr or ""])
        if ave_pat.search(haystack):
            hits["dhcp"].append(asdict(item))

    return hits


def _extract_ipv4_candidates(
    mdns: list[MdnsService], dhcp: list[DhcpObservation]
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    arp_table = _read_arp_table()
    if not arp_table:
        return candidates

    macs = _extract_mac_candidates(mdns, dhcp)
    for mac in sorted(macs):
        ipv4 = arp_table.get(mac)
        if ipv4:
            candidates.append({"mac": mac, "ipv4": ipv4, "source": "arp"})

    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover devices similarly to HA network discovery helpers")
    parser.add_argument("--timeout", type=float, default=8.0, help="Discovery timeout in seconds per phase")
    parser.add_argument("--dhcp", action="store_true", help="Also sniff DHCP traffic (requires scapy + root)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    print(f"[*] SSDP discovery ({args.timeout:.1f}s)...")
    ssdp = discover_ssdp(args.timeout)
    print(f"    Found {len(ssdp)} SSDP responses")

    print(f"[*] mDNS/Zeroconf discovery ({args.timeout:.1f}s)...")
    mdns = discover_mdns(args.timeout)
    print(f"    Found {len(mdns)} mDNS services")

    dhcp: list[DhcpObservation] = []
    if args.dhcp:
        print(f"[*] DHCP sniff ({args.timeout:.1f}s)...")
        try:
            dhcp = discover_dhcp(args.timeout)
            print(f"    Found {len(dhcp)} DHCP observations")
        except Exception as exc:  # noqa: BLE001
            print(f"    DHCP sniff unavailable: {exc}")

    summary = {
        "ssdp_count": len(ssdp),
        "mdns_count": len(mdns),
        "dhcp_count": len(dhcp),
        "possible_ave_hits": _extract_possible_ave_hits(mdns, ssdp, dhcp),
        "ipv4_candidates": _extract_ipv4_candidates(mdns, dhcp),
        "ssdp": [asdict(d) for d in ssdp],
        "mdns": [asdict(d) for d in mdns],
        "dhcp": [asdict(d) for d in dhcp],
    }

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    print("\n=== Summary ===")
    print(f"SSDP devices: {summary['ssdp_count']}")
    print(f"mDNS services: {summary['mdns_count']}")
    print(f"DHCP observations: {summary['dhcp_count']}")

    ave_hits = summary["possible_ave_hits"]
    total_hits = sum(len(v) for v in ave_hits.values())
    print(f"Possible AVE-related hits: {total_hits}")

    ipv4_candidates = summary["ipv4_candidates"]
    print(f"IPv4 candidates: {len(ipv4_candidates)}")
    for cand in ipv4_candidates:
        print(f"  • {cand['ipv4']} (mac {cand['mac']}, via {cand['source']})")

    if total_hits:
        print("\n=== Possible AVE hits ===")
        for source, entries in ave_hits.items():
            if not entries:
                continue
            print(f"- {source}: {len(entries)}")
            for entry in entries[:20]:
                print(f"  • {json.dumps(entry, ensure_ascii=False)}")

    print("\nTip: use --json to inspect full discovery output.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
