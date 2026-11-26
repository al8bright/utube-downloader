"""PyInstaller 진입점: `uv run utube`과 같은 명령줄(앱은 `utube-backend serve ...`로 띄운다). (공통 파일)"""

import sys

from utube import main

if __name__ == "__main__":
    sys.exit(main())
