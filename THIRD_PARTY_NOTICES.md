# Third-party notices

이 저장소의 소스 코드는 [MIT 라이선스](LICENSE)입니다.
배포하는 **설치 파일**에는 아래의 다른 프로젝트가 함께 들어 있고, 각각 자기 라이선스를 따릅니다.
설치 폴더의 `backend\licenses\` 에 각 라이선스 전문이 들어 있습니다.

The source code in this repository is licensed under the [MIT License](LICENSE).
The Windows **installer** also ships the third-party software below, each under its own license.
Full license texts are installed in `backend\licenses\` next to the app.

## 별도 실행 파일 · Separate programs

앱은 아래 프로그램을 별도 프로세스로 실행합니다(코드를 섞어 빌드하지 않습니다).

| 구성 요소 | 라이선스 | 소스 |
| :--- | :--- | :--- |
| **FFmpeg** (`ffmpeg.exe`, gyan.dev Windows 빌드) | **GPL-3.0-or-later** (`--enable-gpl --enable-version3` 빌드) | https://ffmpeg.org · 빌드에 쓴 정확한 소스 커밋은 설치 폴더의 `backend\licenses\FFmpeg-README.txt` 에 적혀 있습니다 · 빌드 정보 https://www.gyan.dev/ffmpeg/builds/ |
| **Deno** (`deno.exe`) | MIT | https://github.com/denoland/deno |

FFmpeg 는 GPL 로 배포됩니다. 설치 파일과 함께 받은 FFmpeg 의 해당 소스 코드는 위 주소에서 받을 수 있으며,
요청하시면 이 저장소의 이슈로 같은 버전의 소스를 안내해 드립니다.

## 백엔드 · Backend (`utube-backend.exe`, PyInstaller)

| 구성 요소 | 라이선스 |
| :--- | :--- |
| Python 3.13 | PSF-2.0 |
| yt-dlp · yt-dlp-ejs | Unlicense (ejs: Unlicense AND MIT AND ISC) |
| **mutagen** (yt-dlp 의 메타데이터 처리) | **GPL-2.0-or-later** |
| FastAPI · Starlette · uvicorn · pydantic · websockets 등 | MIT · BSD-3-Clause |
| requests · opentelemetry-api | Apache-2.0 |
| certifi | MPL-2.0 |
| pycryptodomex | BSD-2-Clause · Public Domain |
| PyInstaller 부트로더 | GPL-2.0 with bootloader exception (만든 프로그램의 라이선스에 제약 없음) |

전체 목록과 전문: `backend\licenses\python-packages.txt` (빌드 때 `scripts/collect_licenses.py` 가 만듭니다).

mutagen 이 GPL 이므로 `utube-backend.exe` **실행 파일**은 GPL 조건으로 배포됩니다.
이 실행 파일을 만든 소스는 모두 이 저장소(MIT, GPL 과 호환)와 위 패키지들의 공개 저장소에 있습니다.

## 앱 · App window (`youtube-downloader.exe`)

| 구성 요소 | 라이선스 |
| :--- | :--- |
| Tauri 와 Rust 크레이트 | 대부분 MIT OR Apache-2.0 (일부 BSD-3-Clause · MPL-2.0 · Unicode-3.0 · Zlib) |
| React · React DOM | MIT |
| @tauri-apps/api · plugin-dialog | MIT OR Apache-2.0 |
| Noto Sans KR · Chakra Petch · JetBrains Mono (`@fontsource`) | SIL Open Font License 1.1 |

전체 목록과 전문: `backend\licenses\rust-crates.txt`, `backend\licenses\js-packages.txt`.

## 상표 · Trademarks

YouTube 는 Google LLC 의 상표입니다. 이 프로젝트는 YouTube · Google 과 관련이 없고, 그들의 승인이나 후원을 받지 않았습니다.
YouTube is a trademark of Google LLC. This project is not affiliated with, endorsed or sponsored by YouTube or Google.
