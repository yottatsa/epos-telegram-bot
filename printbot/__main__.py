import argparse
import json
import logging

from .main import POSBot


def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    parser = argparse.ArgumentParser(description="POSBot")
    parser.add_argument("config", type=argparse.FileType("r"))
    args = parser.parse_args()
    config = json.load(args.config)
    POSBot(**config).start()


if __name__ == "__main__":
    main()
