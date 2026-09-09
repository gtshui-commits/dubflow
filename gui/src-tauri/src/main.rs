// DubFlow GUI shell.
// Dev workflow: start engine first (see README), then `npm run tauri dev`.
// MVP note: the GUI talks to the engine over http://127.0.0.1:8741 directly.
// Production packaging will launch the engine as a Tauri sidecar (tauri.conf.json
// "bundle.externalBin") and shut it down on exit.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running DubFlow");
}
