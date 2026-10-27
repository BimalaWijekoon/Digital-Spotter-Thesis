from __future__ import annotations

import base64
import json
import msgpack
import pytest

from digital_spotter.cli import main
from digital_spotter.imu.control import load_device_key
from digital_spotter.imu.provisioning import (
    CLAIM_PREFIX,
    ProvisioningError,
    WearableClaim,
    decode_claim,
    encode_claim,
    import_claim,
    issue_claim_bundle,
    read_confidential_claim_file,
)


CLAIM = WearableClaim(
    device_id="dsimu-001122aabbcc",
    device_key=bytes(range(32)),
    claim_nonce=bytes(reversed(range(16))),
)


def test_claim_round_trip_and_atomic_owner_only_import(tmp_path):
    encoded = encode_claim(CLAIM)
    assert decode_claim(encoded) == CLAIM

    identity = tmp_path / "identity"
    receipt = import_claim(encoded, identity)

    assert receipt.device_id == CLAIM.device_id
    assert len(receipt.claim_fingerprint) == 64
    assert (identity.stat().st_mode & 0o777) == 0o700
    assert (identity / "wearable-device-id").read_text() == CLAIM.device_id + "\n"
    assert load_device_key(identity / "wearable-device-key") == CLAIM.device_key
    assert (identity / "wearable-claim-receipt").read_text().startswith("version=1\n")
    assert all((path.stat().st_mode & 0o777) == 0o600 for path in identity.iterdir())

    with pytest.raises(ProvisioningError, match="already claimed"):
        import_claim(encoded, identity)


def test_claim_rejects_noncanonical_tampered_and_unbounded_data():
    encoded = encode_claim(CLAIM)
    tamper_at = len(CLAIM_PREFIX) + 20
    replacement = "A" if encoded[tamper_at] != "A" else "B"
    with pytest.raises(ProvisioningError):
        decode_claim(encoded[:tamper_at] + replacement + encoded[tamper_at + 1 :])
    with pytest.raises(ProvisioningError, match="prefix or length"):
        decode_claim("wrong:" + encoded)

    reordered = msgpack.packb(
        {
            "device_id": CLAIM.device_id,
            "version": 1,
            "device_key": CLAIM.device_key,
            "claim_nonce": CLAIM.claim_nonce,
            "claim_tag": bytes(16),
        },
        use_bin_type=True,
    )
    token = base64.urlsafe_b64encode(reordered).rstrip(b"=").decode("ascii")
    with pytest.raises(ProvisioningError, match="reordered"):
        decode_claim(CLAIM_PREFIX + token)

    with pytest.raises(ProvisioningError, match="all zero"):
        encode_claim(WearableClaim(CLAIM.device_id, bytes(32), CLAIM.claim_nonce))


def test_import_rejects_insecure_or_symlink_destination(tmp_path):
    insecure = tmp_path / "insecure"
    insecure.mkdir(mode=0o755)
    with pytest.raises(ProvisioningError, match="group or other"):
        import_claim(encode_claim(CLAIM), insecure)

    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "identity-link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ProvisioningError, match="non-symlink"):
        import_claim(encode_claim(CLAIM), link)


def test_claim_file_and_cli_require_owner_only_input_without_echoing_secret(tmp_path, capsys):
    claim_text = encode_claim(CLAIM)
    claim_file = tmp_path / "wearable.claim"
    claim_file.write_text(claim_text, encoding="ascii")
    claim_file.chmod(0o600)
    assert read_confidential_claim_file(claim_file) == claim_text

    identity = tmp_path / "identity"
    assert main(
        [
            "wearable",
            "provision",
            "--claim-file",
            str(claim_file),
            "--identity-dir",
            str(identity),
        ]
    ) == 0
    output = capsys.readouterr()
    summary = json.loads(output.out)
    assert summary["device_id"] == CLAIM.device_id
    assert claim_text not in output.out
    assert claim_text not in output.err

    insecure = tmp_path / "insecure.claim"
    insecure.write_text(claim_text, encoding="ascii")
    insecure.chmod(0o644)
    with pytest.raises(ProvisioningError, match="group or other"):
        read_confidential_claim_file(insecure)

    link = tmp_path / "claim-link"
    link.symlink_to(claim_file)
    with pytest.raises(ProvisioningError, match="owner-only regular file"):
        read_confidential_claim_file(link)


def test_issue_claim_bundle_is_unique_owner_only_and_cli_does_not_echo_key(tmp_path, capsys):
    bundle = tmp_path / "bundle"
    receipt = issue_claim_bundle("dsimu-001122aabbcc", bundle)
    claim_text = read_confidential_claim_file(bundle / "wearable.claim")
    claim = decode_claim(claim_text)

    assert receipt.device_id == claim.device_id
    assert len(receipt.claim_fingerprint) == 64
    assert (bundle.stat().st_mode & 0o777) == 0o700
    assert all((path.stat().st_mode & 0o777) == 0o600 for path in bundle.iterdir())
    nvs_csv = (bundle / "provisioning-nvs.csv").read_text(encoding="ascii")
    assert f"device_key,data,hex2bin,{claim.device_key.hex()}" in nvs_csv
    assert claim_text not in receipt.claim_fingerprint

    with pytest.raises(ProvisioningError, match="already issued"):
        issue_claim_bundle(claim.device_id, bundle)

    cli_bundle = tmp_path / "cli-bundle"
    assert main(
        [
            "wearable",
            "issue-claim",
            "--device-id",
            "dsimu-aabbccddeeff",
            "--output-dir",
            str(cli_bundle),
        ]
    ) == 0
    output = capsys.readouterr()
    cli_claim = read_confidential_claim_file(cli_bundle / "wearable.claim")
    cli_key = decode_claim(cli_claim).device_key.hex()
    assert cli_claim not in output.out
    assert cli_key not in output.out
    assert cli_claim not in output.err
    assert cli_key not in output.err
