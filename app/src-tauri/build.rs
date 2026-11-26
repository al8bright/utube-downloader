// tauri.conf.json의 bundle.resources가 PyInstaller 결과 폴더(../../backend/dist/<이름>-backend/)를
// 가리키는데, tauri-build는 그 폴더가 없으면 멈춘다. 그 폴더는 설치 파일을 만들 때만 생기므로
// 개발 빌드(백엔드를 소스로 띄움)를 위해 빈 폴더를 만들어 둔다. scripts/build_app이 채우고 검사한다.
// (공통 파일: 네 앱이 같은 내용을 쓴다. docs/STRUCTURE.md)

fn main() {
    println!("cargo:rerun-if-changed=tauri.conf.json");
    let conf = std::fs::read_to_string("tauri.conf.json").unwrap_or_default();
    let mut rest = conf.as_str();
    while let Some(i) = rest.find("\"../../backend/dist/") {
        let path = &rest[i + 1..];
        if let Some(end) = path.find('"') {
            let _ = std::fs::create_dir_all(&path[..end]);
        }
        rest = &rest[i + 1..];
    }
    tauri_build::build()
}
