from __future__ import annotations

import argparse

from prediction_core.server import build_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prediction-core", description="prediction_core Python service controls")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Run the local prediction_core HTTP service")
    serve.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    serve.add_argument("--port", default=8080, type=int, help="TCP port to bind")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command != "serve":
        parser.print_help()
        return 0

    server = build_server(host=args.host, port=args.port)
    print(f"prediction_core server listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
