//! Tauri shell: starts the Python backend (sidecar), hands its URL + token to the web UI,
//! and stops it when the app exits.
//!
//! Backend command, first match wins:
//!   1. UTUBE_BACKEND_URL set      -> use an already running backend (no spawn)
//!   2. release build and <resources>/backend/utube-backend.exe exists (bundle)
//!   3. otherwise (always in dev): `uv run --project <repo>/backend utube serve`
//! The backend gets `--port 0 --parent-pid <our pid>` and UTUBE_TOKEN=<random>; it prints
//! `UTUBE_LISTENING <url>` once ready and exits by itself if this process dies.

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
    let (guard, timeout) = cvar
        .wait_timeout_while(guard, Duration::from_secs(60), |s| s.info.is_none() && s.error.is_none())
        .map_err(|e| e.to_string())?;
    if let Some(info) = &guard.info {
        return Ok(info.clone());
    }
    if let Some(err) = &guard.error {
        return Err(err.clone());
    }
    if timeout.timed_out() {
        return Err("백엔드가 60초 안에 시작하지 않았습니다.".into());
    }
    Err("백엔드를 쓸 수 없습니다.".into())
}

const SIDECAR: &str = if cfg!(windows) { "utube-backend.exe" } else { "utube-backend" };

fn backend_command(app: &tauri::AppHandle) -> Command {
    let pid = std::process::id().to_string();
    let bundled = app
        .path()
        .resource_dir()
        .ok()
        .map(|d| d.join("backend").join(SIDECAR))
        // dev builds always run the backend from source: a stale PyInstaller copy can sit in
        // target/debug/backend after an installer build and would lack newer endpoints
        .filter(|p| !cfg!(debug_assertions) && p.exists());
    let mut cmd = match bundled {
        Some(exe) => Command::new(exe),
        None => {
            let project = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("backend");
            let mut c = Command::new("uv");
            c.arg("run").arg("--project").arg(project).arg("utube");
            c
        }
    };
    cmd.args(["serve", "--port", "0", "--parent-pid", &pid]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // CREATE_NO_WINDOW: the backend and the ffmpeg it starts share one hidden console
        cmd.creation_flags(0x0800_0000);
    }
    cmd
}

fn start_backend(app: &tauri::AppHandle) {
    let backend = app.state::<Backend>();
    let state = backend.state.clone();

    if let Ok(url) = std::env::var("UTUBE_BACKEND_URL") {
        let token = std::env::var("UTUBE_TOKEN").unwrap_or_default();
        let (lock, cvar) = &*state;
        lock.lock().unwrap().info = Some(BackendInfo { url, token });
        cvar.notify_all();
        return;
    }

    let token = uuid::Uuid::new_v4().simple().to_string();
    let mut cmd = backend_command(app);
    cmd.env("UTUBE_TOKEN", &token)
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8")
        // a VIRTUAL_ENV left over from another project makes `uv run` warn on every start
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

    // stderr: keep the tail for error reporting
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
        std::thread::spawn(move || {
            let (lock, cvar) = &*state;
            for line in BufReader::new(out).lines().map_while(Result::ok) {
                log::info!("[backend] {line}");
                if let Some(url) = line.strip_prefix("UTUBE_LISTENING ") {
                    lock.lock().unwrap().info = Some(BackendInfo { url: url.trim().to_string(), token: token.clone() });
                    cvar.notify_all();
                }
            }
            // stdout closed: the backend exited
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
