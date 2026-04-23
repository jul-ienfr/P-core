use std::env;
use std::path::PathBuf;
use std::process::Command;

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("xtask crate should live under prediction_core/rust")
        .to_path_buf()
}

fn usage() -> &'static str {
    "usage: cargo run -p xtask -- pm-storage-runtime [rust_test_name ...]"
}

fn run_pm_storage_runtime(selected_tests: &[String]) -> Result<(), String> {
    let script_name = if selected_tests.is_empty() {
        "check_pm_storage_runtime.sh"
    } else {
        "run_pm_storage_runtime_test.sh"
    };
    let script_path = repo_root().join("scripts").join(script_name);

    let mut command = Command::new(&script_path);
    command.current_dir(repo_root());
    if !selected_tests.is_empty() {
        command.args(selected_tests);
    }

    let status = command
        .status()
        .map_err(|error| format!("failed to launch {}: {error}", script_path.display()))?;

    if status.success() {
        Ok(())
    } else {
        Err(format!("{} exited with status {status}", script_path.display()))
    }
}

fn main() {
    let mut args = env::args().skip(1);
    let Some(command) = args.next() else {
        eprintln!("{}", usage());
        std::process::exit(1);
    };

    let result = match command.as_str() {
        "pm-storage-runtime" => {
            let selected_tests: Vec<String> = args.collect();
            run_pm_storage_runtime(&selected_tests)
        }
        _ => Err(format!("unknown xtask command: {command}\n{}", usage())),
    };

    if let Err(error) = result {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
