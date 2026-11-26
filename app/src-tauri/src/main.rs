// 릴리스 빌드에서 콘솔 창이 따로 뜨지 않게 한다. 지우지 말 것
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    app_lib::run();
}
