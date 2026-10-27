from digital_spotter.observability.network import LinuxWiFiProbe


def test_wifi_probe_reports_only_local_connectivity_without_exposing_address():
    probe = LinuxWiFiProbe(
        interface="wlan0",
        operstate_reader=lambda _interface: "up",
        address_reader=lambda _interface: True,
    )

    assert probe.sample() == {
        "state": "connected",
        "interface": "wlan0",
        "has_local_address": True,
    }


def test_wifi_probe_distinguishes_disconnected_and_unavailable():
    disconnected = LinuxWiFiProbe(
        interface="wlan0",
        operstate_reader=lambda _interface: "down",
        address_reader=lambda _interface: False,
    )
    unavailable = LinuxWiFiProbe(
        interface="wlan0",
        operstate_reader=lambda _interface: None,
        address_reader=lambda _interface: False,
    )

    assert disconnected.sample()["state"] == "disconnected"
    assert unavailable.sample()["state"] == "unavailable"
