"""Offline country lookup. Raw addresses are never persisted or sent to a service."""

import ipaddress
import os
from pathlib import Path

try:
    import maxminddb
except ImportError:
    maxminddb = None


def client_address(request):
    try:
        address = ipaddress.ip_address(request.client.host) if request.client else None
        trusted = [ipaddress.ip_network(item.strip()) for item in os.environ.get(
            "RAMANCLOUD_ANALYTICS_TRUSTED_PROXIES", "127.0.0.1/32,::1/128").split(",") if item.strip()]
        # Walk from the trusted edge inward; never accept a forwarded address from an untrusted peer.
        if address and any(address in network for network in trusted):
            forwarded = request.headers.get("x-forwarded-for", "")
            for item in reversed(forwarded.split(",")):
                if not item.strip():
                    continue
                address = ipaddress.ip_address(item.strip())
                if not any(address in network for network in trusted):
                    break
        return address
    except ValueError:
        return None


class CountryLookup:
    def __init__(self, directory):
        self.path = Path(os.environ.get("RAMANCLOUD_GEOIP_DATABASE", Path(directory) / "geo" / "country.mmdb"))

    @property
    def enabled(self):
        return maxminddb is not None and self.path.is_file()

    def lookup(self, request):
        address = client_address(request)
        if not address or not address.is_global or not self.enabled:
            return "ZZ"
        try:
            with maxminddb.open_database(str(self.path)) as reader:
                code = (reader.get(str(address)) or {}).get("country", {}).get("iso_code", "ZZ")
                return code if isinstance(code, str) and len(code) == 2 and code.isalpha() and code.isupper() else "ZZ"
        except (OSError, ValueError, maxminddb.InvalidDatabaseError):
            return "ZZ"
