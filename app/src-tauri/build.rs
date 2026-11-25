fn main() {
    // tauri.conf.json bundles ../../backend/dist/utube-backend/ and tauri-build refuses to run
    // when that folder is missing. It only exists after a PyInstaller build, so dev builds
    // (which run the backend from source) get an empty one. scripts/build_app.ps1 fills it
    // and checks the executable is there before bundling.
    let _ = std::fs::create_dir_all("../../backend/dist/utube-backend");
    tauri_build::build()
}
