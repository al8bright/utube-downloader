//! Tauri 셸: 파이썬 백엔드를 띄우고, 주소와 토큰을 화면에 넘기고, 앱이 끝날 때 백엔드를 끝낸다.
//! (공통 파일: 네 앱이 같은 내용을 쓴다. 앱마다 다른 값은 app_info.rs. docs/STRUCTURE.md)
//!
//! 백엔드 명령은 위에서부터 먼저 맞는 것을 쓴다.
//!   1. `<ENV>_BACKEND_URL`이 있으면 이미 떠 있는 백엔드에 붙는다(띄우지 않음)
//!   2. 릴리스 빌드이고 <resources>/backend/<SIDECAR>가 있으면 그것(설치본)
//!   3. 그 밖(개발 실행은 항상): `uv run --project <저장소>/backend <CLI> serve`
//! 백엔드는 `--port 0 --parent-pid <이 프로세스>`와 `<ENV>_TOKEN=<임의 값>`을 받아, 준비되면
//! `<ENV>_LISTENING <주소>`를 출력하고, 이 프로세스가 사라지면 스스로 끝난다.

mod app_info;

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Condvar, Mutex};
use std::time::Duration;

use serde::Serialize;
use tauri::{Manager, RunEvent};

#[derive(Clone, Serialize)]
struct BackendInfo {
    url: String,
    token: String,
}

#[derive(Default)]
struct Shared {
    info: Option<BackendInfo>,
    error: Option<String>,
}

#[derive(Default)]
struct Backend {
    child: Mutex<Option<Child>>,
    state: Arc<(Mutex<Shared>, Condvar)>,
}

#[tauri::command]
fn backend_info(backend: tauri::State<'_, Backend>) -> Result<BackendInfo, String> {
    let (lock, cvar) = &*backend.state;
    let guard = lock.lock().map_err(|e| e.to_string())?;
    let wait = Duration::from_secs(app_info::STARTUP_SECS);
    let (guard, timeout) = cvar
        .wait_timeout_while(guard, wait, |s| s.info.is_none() && s.error.is_none())
        .map_err(|e| e.to_string())?;
    if let Some(info) = &guard.info {
        return Ok(info.clone());
    }
    if let Some(err) = &guard.error {
        return Err(err.clone());
    }
    if timeout.timed_out() {
        return Err(format!("백엔드가 {}초 안에 시작하지 않았습니다.", app_info::STARTUP_SECS));
    }
    Err("백엔드를 쓸 수 없습니다.".into())
}

fn env_name(suffix: &str) -> String {
    format!("{}_{suffix}", app_info::ENV)
}

fn backend_command(app: &tauri::AppHandle) -> Command {
    let pid = std::process::id().to_string();
    let bundled = app
        .path()
        .resource_dir()
        .ok()
        .map(|d| d.join("backend").join(app_info::SIDECAR))
        // 개발 빌드는 항상 소스로 띄운다. 설치 파일을 만든 뒤 target/debug/backend에 남은
        // 옛 PyInstaller 사본은 새 API가 없을 수 있다
        .filter(|p| !cfg!(debug_assertions) && p.exists());
    let mut cmd = match bundled {
        Some(exe) => Command::new(exe),
        None => {
            let project = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("backend");
            let mut c = Command::new("uv");
            c.arg("run").arg("--project").arg(project).arg(app_info::CLI);
            c
        }
    };
    cmd.args(["serve", "--port", "0", "--parent-pid", &pid]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // CREATE_NO_WINDOW: 백엔드와 백엔드가 띄우는 프로세스(FFmpeg 등)가 숨은 콘솔 하나를 같이 쓴다
        cmd.creation_flags(0x0800_0000);
    }
    cmd
}

fn start_backend(app: &tauri::AppHandle) {
    let backend = app.state::<Backend>();
    let state = backend.state.clone();

    if let Ok(url) = std::env::var(env_name("BACKEND_URL")) {
        let token = std::env::var(env_name("TOKEN")).unwrap_or_default();
        let (lock, cvar) = &*state;
        lock.lock().unwrap().info = Some(BackendInfo { url, token });
        cvar.notify_all();
        return;
    }

    let token = uuid::Uuid::new_v4().simple().to_string();
    let mut cmd = backend_command(app);
    cmd.env(env_name("TOKEN"), &token)
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8")
        // 다른 프로젝트에서 남은 VIRTUAL_ENV가 있으면 `uv run`이 시작할 때마다 경고한다
        .env_remove("VIRTUAL_ENV")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            let (lock, cvar) = &*state;
            lock.lock().unwrap().error = Some(format!("백엔드를 시작하지 못했습니다: {e}"));
            cvar.notify_all();
            return;
        }
    };
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    *backend.child.lock().unwrap() = Some(child);

    // stderr: 시작하다 멈췄을 때 보여 주려고 마지막 30줄을 남긴다
    let tail = Arc::new(Mutex::new(Vec::<String>::new()));
    if let Some(err) = stderr {
        let tail = tail.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(err).lines().map_while(Result::ok) {
                log::info!("[backend] {line}");
                let mut t = tail.lock().unwrap();
                t.push(line);
                if t.len() > 30 {
                    t.remove(0);
                }
            }
        });
    }

    if let Some(out) = stdout {
        let ready = format!("{} ", env_name("LISTENING"));
        std::thread::spawn(move || {
            let (lock, cvar) = &*state;
            for line in BufReader::new(out).lines().map_while(Result::ok) {
                log::info!("[backend] {line}");
                if let Some(url) = line.strip_prefix(ready.as_str()) {
                    lock.lock().unwrap().info = Some(BackendInfo { url: url.trim().to_string(), token: token.clone() });
                    cvar.notify_all();
                }
            }
            // stdout이 닫혔다: 백엔드가 끝났다
            let mut s = lock.lock().unwrap();
            if s.info.is_none() {
                std::thread::sleep(Duration::from_millis(200));
                let detail = tail.lock().unwrap().join("\n");
                s.error = Some(format!("백엔드가 시작하다 멈췄습니다.\n{detail}"));
                cvar.notify_all();
            }
        });
    }
}

fn stop_backend(app: &tauri::AppHandle) {
    if let Some(backend) = app.try_state::<Backend>() {
        if let Some(mut child) = backend.child.lock().unwrap().take() {
            if cfg!(unix) {
                // macOS에는 Job Object가 없어, 바로 죽이면 백엔드가 띄운 프로세스가 남는다.
                // SIGTERM으로 먼저 정리하게 하고, 3초 안에 끝나지 않으면 아래에서 강제로 끝낸다
                let _ = Command::new("kill").args(["-TERM", &child.id().to_string()]).status();
                for _ in 0..30 {
                    if let Ok(Some(_)) = child.try_wait() {
                        return;
                    }
                    std::thread::sleep(Duration::from_millis(100));
                }
            }
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_log::Builder::default().level(log::LevelFilter::Info).build())
        .manage(Backend::default())
        .invoke_handler(tauri::generate_handler![backend_info])
        .setup(|app| {
            start_backend(app.handle());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_backend(app);
            }
        });
}
