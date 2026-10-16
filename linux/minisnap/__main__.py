"""Entry point: `python3 -m minisnap [options]` (run from the linux/ directory or an installed share dir)."""

import sys


def main():
    from . import app
    return app.main(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
