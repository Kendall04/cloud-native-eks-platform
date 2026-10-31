"""Deterministic Lambda packaging/checking; no provider, install, network or AWS."""
import argparse
import io
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def package(source):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
        info = zipfile.ZipInfo("recovery.py", (1980, 1, 1, 0, 0, 0))
        info.external_attr = 0o100644 << 16
        info.create_system = 3
        archive.writestr(info, source.replace(b"\r\n", b"\n"))
    return target.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    directory = ROOT / "infra/modules/nat-egress/lambda"
    expected = package((directory / "recovery.py").read_bytes())
    path = directory / "recovery.zip"
    if args.check:
        if not path.exists() or path.read_bytes() != expected:
            raise SystemExit("NAT Lambda ZIP is stale; regenerate with package_nat_recovery.py")
        print("NAT Lambda deterministic ZIP matches source")
    else:
        path.write_bytes(expected)
        print("Generated NAT recovery ZIP from reviewed source")


if __name__ == "__main__": main()
