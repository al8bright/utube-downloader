"""utube: YouTube Music Downloader 백엔드."""

__version__ = "2.0.0"


def main() -> None:
    from utube.cli import main as cli_main

    cli_main()
