import argparse
from .extract_core import run_extraction


def main():
    parser = argparse.ArgumentParser(
        description="Extract spectra and background from Omnic SRS files (Rapid Scan / Realtime)"
    )
    parser.add_argument("srs", help="Path to .srs file")
    parser.add_argument("--mode", choices=["fast", "realtime"], required=True,
                        help="Specify SRS format: 'fast' (Omnic Rapid Scan) or 'realtime'")
    parser.add_argument("--outdir", default="output", help="Output directory for results")
    parser.add_argument("--start", type=float, help="Wavenumber start (cm⁻¹)")
    parser.add_argument("--end", type=float, help="Wavenumber end (cm⁻¹)")
    args = parser.parse_args()

    run_extraction(args.srs, mode=args.mode, outdir=args.outdir,
                   start_wn=args.start, end_wn=args.end)


if __name__ == "__main__":
    main()

