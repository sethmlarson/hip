import hip
import pytest


@pytest.mark.trio
async def test_name_resolution_error():
    with pytest.raises(hip.NameResolutionError):
        await hip.a.request("GET", "https://this.name.doesnt.exist")


@pytest.mark.trio
async def test_self_signed_certificate():
    with pytest.raises(hip.SelfSignedCertificate):
        await hip.a.request("GET", "https://self-signed.badssl.com")


@pytest.mark.trio
async def test_expired_certificate():
    with pytest.raises(hip.ExpiredCertificate):
        await hip.a.request("GET", "https://expired.badssl.com")


@pytest.mark.trio
async def test_certificate_hostname_mismatch():
    with pytest.raises(hip.CertificateHostnameMismatch):
        await hip.a.request("GET", "https://wrong.host.badssl.com")
