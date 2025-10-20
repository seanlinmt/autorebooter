#!/usr/bin/env python3
import argparse
import logging
import os
import socket
import subprocess
import sys
import time

LOGFILE = "/var/log/autorebooter.log"

def has_internet(host: str, port: int, timeout: float) -> bool:
    """
    Check internet connectivity by sending a single ICMP ping to `host` using the system
    `ping` command. The `port` argument is kept for compatibility but is ignored by the
    ping check. If `ping` is not installed, fall back to a TCP connect to the given port.
    """
    # Convert timeout to an integer number of seconds for the ping utility (minimum 1s)
    try:
        wait_secs = max(1, int(round(timeout)))
    except Exception:
        wait_secs = 1

    # Use Linux-style ping: send 1 packet and wait up to wait_secs for a reply
    cmd = ["ping", "-c", "1", "-W", str(wait_secs), host]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0
    except FileNotFoundError:
        # ping binary not available; fall back to TCP socket to provided port (or 53)
        try:
            probe_port = port or 53
            with socket.create_connection((host, probe_port), timeout=timeout):
                return True
        except OSError:
            return False

def reboot_now(dry_run: bool):
    msg = "No internet detected — initiating reboot"
    logging.warning(msg)
    if dry_run:
        print("[dry-run]", msg)
        return
    # Prefer systemctl reboot; fall back to reboot -f
    try:
        subprocess.run(["systemctl", "reboot", "--force"], check=True)
    except Exception:
        subprocess.run(["reboot", "-f"])

def main():
    parser = argparse.ArgumentParser(description="Reboot if no internet detected")
    parser.add_argument("--host", default="1.1.1.1", help="Host to test (default 1.1.1.1)")
    parser.add_argument("--port", type=int, default=53, help="Port to test (default 53)")
    parser.add_argument("--tries", type=int, default=3, help="Number of attempts before reboot")
    parser.add_argument("--timeout", type=float, default=3.0, help="Connection timeout (seconds)")
    parser.add_argument("--wait", type=float, default=5.0, help="Seconds between attempts")
    parser.add_argument("--dry-run", action="store_true", help="Do not actually reboot; just log/print")
    args = parser.parse_args()

    logging.basicConfig(filename=LOGFILE, level=logging.INFO,
                        format="%(asctime)s %(levelname)s: %(message)s")

    # Determine whether we're running as root in a portable, linter-friendly way.
    # Use getattr to avoid static analyzer complaints about os.geteuid on non-POSIX.
    is_root = False
    euid_func = getattr(os, "geteuid", None) or getattr(os, "getuid", None)
    if callable(euid_func):
        try:
            is_root = (euid_func() == 0)
        except Exception:
            is_root = False

    if not is_root and not args.dry_run:
        print("This script must be run as root to perform a reboot. Use --dry-run to test.")
        sys.exit(2)

    logging.info("Starting internet check: host=%s port=%d tries=%d", args.host, args.port, args.tries)

    for attempt in range(1, args.tries + 1):
        if has_internet(args.host, args.port, args.timeout):
            logging.info("Internet available on attempt %d", attempt)
            print("Internet available; no action needed.")
            return 0
        logging.warning("Internet not reachable (attempt %d/%d).", attempt, args.tries)
        if attempt < args.tries:
            time.sleep(args.wait)

    reboot_now(args.dry_run)
    return 0

if __name__ == "__main__":
    sys.exit(main())
