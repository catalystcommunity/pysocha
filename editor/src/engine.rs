use serde_json::Value;
use std::{
    io::{self, BufRead, BufReader, Write},
    path::Path,
    process::{Command, Stdio},
    sync::mpsc::{self, Receiver, Sender},
    thread,
};

pub struct Engine {
    pub input: Sender<Value>,
    pub output: Receiver<Value>,
}

impl Engine {
    pub fn open(config: &Path) -> io::Result<Self> {
        let runtime = std::env::current_exe()?.with_file_name("runtime");
        let bundled = runtime.join(if cfg!(windows) {
            "python.exe"
        } else {
            "bin/python3"
        });
        let python = if bundled.is_file() {
            bundled.into_os_string()
        } else {
            std::env::var_os("PYSOCHA_PYTHON")
                .unwrap_or_else(|| if cfg!(windows) { "python" } else { "python3" }.into())
        };
        let mut command = Command::new(python);
        command.args(["-I", "-X", "utf8", "-m", "pysocha.editor_engine"]);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000); // CREATE_NO_WINDOW
        }
        let mut child = command
            .arg(config)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()?;
        let mut stdin = child.stdin.take().unwrap();
        let stdout = child.stdout.take().unwrap();
        let (input, requests) = mpsc::channel::<Value>();
        let (events, output) = mpsc::channel();
        thread::spawn(move || {
            while let Ok(mut request) = requests.recv() {
                for newer in requests.try_iter() {
                    request = newer;
                }
                if writeln!(stdin, "{request}").is_err() {
                    break;
                }
            }
            // EOF lets the helper remove its temporary site and stop its server.
            drop(stdin);
            let _ = child.wait();
        });
        thread::spawn(move || {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                if let Ok(event) = serde_json::from_str(&line) {
                    if events.send(event).is_err() {
                        return;
                    }
                }
            }
            let _ = events.send(serde_json::json!({"stopped":true}));
        });
        Ok(Self { input, output })
    }
}
