"""Server-side geo resolution (Issue #68) — IP -> country, zero cost.

country_for_request precedence: trusted proxy header (`CF-IPCountry`, or
whatever `settings.geo_country_header` names) > a GeoIP db lookup on the
REAL client IP (X-Forwarded-For's first hop, else the socket peer) > `None`
(the caller — services/payments/plans — maps a miss to USD, the safe
default). Never throws. The db-path tests mock the reader rather than
shipping a binary `.mmdb` fixture (acceptance criterion 2 explicitly allows
either); test_pricing_final.py exercises a REAL render under a header.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import Request

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services.geo import resolver


def _request(headers: dict[str, str] | None = None, client_ip: str | None = None) -> Request:
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "headers": hdrs,
        "client": (client_ip, 1234) if client_ip else None,
        "method": "GET",
        "path": "/",
    }
    return Request(scope)


class TestHeaderPath:
    def test_cf_ipcountry_in_resolves_in(self, settings: Settings) -> None:
        assert resolver.country_for_request(_request({"CF-IPCountry": "IN"}), settings) == "IN"

    def test_cf_ipcountry_us_resolves_us(self, settings: Settings) -> None:
        assert resolver.country_for_request(_request({"CF-IPCountry": "US"}), settings) == "US"

    def test_no_header_no_db_returns_none(self, settings: Settings) -> None:
        assert resolver.country_for_request(_request(), settings) is None

    def test_cloudflare_unknown_sentinel_is_a_miss(self, settings: Settings) -> None:
        """Cloudflare sends "XX" when it cannot geolocate (e.g. a Tor exit
        node) — that is no signal, not a real country code."""
        assert resolver.country_for_request(_request({"CF-IPCountry": "XX"}), settings) is None

    def test_header_name_is_configurable(self, settings: Settings) -> None:
        custom = settings.model_copy(update={"geo_country_header": "X-Geo-Country"})
        assert resolver.country_for_request(_request({"X-Geo-Country": "IN"}), custom) == "IN"
        # the default header name is ignored once a custom one is configured
        assert resolver.country_for_request(_request({"CF-IPCountry": "IN"}), custom) is None


class TestGeoipDbPath:
    def test_db_lookup_resolves_country(
        self, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_file = tmp_path / "test.mmdb"
        db_file.write_bytes(b"not a real mmdb, reader is mocked below")
        cfg = settings.model_copy(update={"geoip_db_path": str(db_file)})

        class FakeReader:
            def get(self, ip: str) -> dict[str, object] | None:
                return {"country": {"iso_code": "IN"}} if ip == "1.2.3.4" else None

        monkeypatch.setattr(resolver, "_reader", lambda path: FakeReader())
        assert resolver.country_for_request(_request(client_ip="1.2.3.4"), cfg) == "IN"

    def test_xff_first_hop_wins_over_client_host(
        self, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """We run behind a proxy that forwards the real client IP via
        X-Forwarded-For (--proxy-headers); the socket peer would otherwise
        be the proxy itself."""
        db_file = tmp_path / "test.mmdb"
        db_file.write_bytes(b"not a real mmdb, reader is mocked below")
        cfg = settings.model_copy(update={"geoip_db_path": str(db_file)})
        mapping = {
            "10.0.0.1": {"country": {"iso_code": "IN"}},
            "203.0.113.9": {"country": {"iso_code": "US"}},
        }

        class FakeReader:
            def get(self, ip: str) -> dict[str, object] | None:
                return mapping.get(ip)

        monkeypatch.setattr(resolver, "_reader", lambda path: FakeReader())
        req = _request(
            headers={"X-Forwarded-For": "10.0.0.1, 203.0.113.9"}, client_ip="203.0.113.9"
        )
        assert resolver.country_for_request(req, cfg) == "IN"

    def test_header_wins_over_db(
        self, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_file = tmp_path / "test.mmdb"
        db_file.write_bytes(b"not a real mmdb, reader is mocked below")
        cfg = settings.model_copy(update={"geoip_db_path": str(db_file)})

        class FakeReader:
            def get(self, ip: str) -> dict[str, object]:
                return {"country": {"iso_code": "US"}}

        monkeypatch.setattr(resolver, "_reader", lambda path: FakeReader())
        req = _request(headers={"CF-IPCountry": "IN"}, client_ip="1.2.3.4")
        assert resolver.country_for_request(req, cfg) == "IN"

    def test_configured_but_missing_db_file_is_a_miss(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        cfg = settings.model_copy(update={"geoip_db_path": str(tmp_path / "nope.mmdb")})
        assert resolver.country_for_request(_request(client_ip="1.2.3.4"), cfg) is None

    def test_malformed_ip_from_reader_is_a_miss_not_a_crash(
        self, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_file = tmp_path / "test.mmdb"
        db_file.write_bytes(b"not a real mmdb, reader is mocked below")
        cfg = settings.model_copy(update={"geoip_db_path": str(db_file)})

        class FakeReader:
            def get(self, ip: str) -> dict[str, object]:
                raise ValueError("bad ip")

        monkeypatch.setattr(resolver, "_reader", lambda path: FakeReader())
        assert resolver.country_for_request(_request(client_ip="not-an-ip"), cfg) is None

    def test_no_client_and_no_xff_is_a_miss(self, settings: Settings, tmp_path: Path) -> None:
        db_file = tmp_path / "test.mmdb"
        db_file.write_bytes(b"not a real mmdb")
        cfg = settings.model_copy(update={"geoip_db_path": str(db_file)})
        assert resolver.country_for_request(_request(), cfg) is None

    def test_db_open_failure_is_a_miss_not_a_crash(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        """A file that exists but isn't a valid mmdb (corrupt download,
        wrong format) must degrade to no-signal, never crash the request."""
        db_file = tmp_path / "corrupt.mmdb"
        db_file.write_bytes(b"this is not a maxmind db")
        cfg = settings.model_copy(update={"geoip_db_path": str(db_file)})
        assert resolver.country_for_request(_request(client_ip="1.2.3.4"), cfg) is None
