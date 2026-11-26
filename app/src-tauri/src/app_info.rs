//! 앱마다 다른 값. 공통 파일 lib.rs는 이름과 시간을 여기서 읽는다. (docs/STRUCTURE.md)

/// 환경 변수 접두사: UTUBE_BACKEND_URL, UTUBE_TOKEN, 준비 신호 UTUBE_LISTENING
pub const ENV: &str = "UTUBE";
/// 개발 실행 때 `uv run`에 넘기는 명령 이름
pub const CLI: &str = "utube";
/// PyInstaller 결과 실행 파일 이름(Windows는 .exe, macOS는 확장자 없음)
pub const SIDECAR: &str = if cfg!(windows) { "utube-backend.exe" } else { "utube-backend" };
/// 백엔드가 준비될 때까지 기다리는 시간(초)
pub const STARTUP_SECS: u64 = 60;
