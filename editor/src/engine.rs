use serde_json::Value;
use std::{
    io::{self, BufRead, BufReader, Write},
    path::Path,
    process::{Command as ProcessCommand, Stdio},
    sync::mpsc::{self, Receiver, RecvTimeoutError, Sender},
    thread,
    time::{Duration, Instant},
};

pub struct Engine {
    commands: Sender<Command>,
    pub output: Receiver<Value>,
}

enum Command {
    Build(Value),
    Ready,
    Close,
}

// Debounce off the UI thread. Keep one build in progress and only the newest
// pending edit, even while GPUI is laying out a long source file.
fn write_requests(mut writer: impl Write, commands: Receiver<Command>) {
    let mut pending: Option<(Instant, Value)> = None;
    let mut busy = false;
    loop {
        let command = if let Some((due, _)) = pending.as_ref().filter(|_| !busy) {
            match commands.recv_timeout(due.saturating_duration_since(Instant::now())) {
                Ok(command) => command,
                Err(RecvTimeoutError::Disconnected) => break,
                Err(RecvTimeoutError::Timeout) => {
                    let (_, request) = pending.take().unwrap();
                    if writeln!(writer, "{request}").is_err() {
                        break;
                    }
                    busy = true;
                    continue;
                }
            }
        } else if let Ok(command) = commands.recv() {
            command
        } else {
            break;
        };
        match command {
            Command::Build(request) => {
                pending = Some((Instant::now() + Duration::from_millis(18), request));
            }
            Command::Ready => busy = false,
            Command::Close => break,
        }
    }
}

impl Drop for Engine {
    fn drop(&mut self) {
        let _ = self.commands.send(Command::Close);
    }
}

pub fn python_module(module: &str) -> io::Result<ProcessCommand> {
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
    let mut command = ProcessCommand::new(python);
    command.args(["-I", "-X", "utf8", "-m", module]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    Ok(command)
}

impl Engine {
    pub fn schedule(&self, request: Value) -> bool {
        self.commands.send(Command::Build(request)).is_ok()
    }

    pub fn open(config: &Path, wake: smol::channel::Sender<()>) -> io::Result<Self> {
        let mut command = python_module("pysocha.editor_engine")?;
        let mut child = command
            .arg(config)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()?;
        let stdin = child.stdin.take().unwrap();
        let stdout = child.stdout.take().unwrap();
        let (commands, requests) = mpsc::channel();
        let feedback = commands.clone();
        let (events, output) = mpsc::channel();
        thread::spawn(move || {
            // EOF lets the helper remove its temporary site and stop its server.
            write_requests(stdin, requests);
            let _ = child.wait();
        });
        thread::spawn(move || {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                if let Ok(event) = serde_json::from_str::<Value>(&line) {
                    if event["revision"].is_u64() {
                        let _ = feedback.send(Command::Ready);
                    }
                    if events.send(event).is_err() {
                        return;
                    }
                    let _ = wake.try_send(());
                }
            }
            let _ = feedback.send(Command::Close);
            let _ = events.send(serde_json::json!({"stopped":true}));
            let _ = wake.try_send(());
        });
        Ok(Self { commands, output })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn edits_coalesce_before_and_during_a_build() {
        let (commands, requests) = mpsc::channel();
        let (read, write) = io::pipe().unwrap();
        let (sent, lines) = mpsc::channel();
        let reader = thread::spawn(move || {
            for line in BufReader::new(read).lines() {
                sent.send(line.unwrap()).unwrap();
            }
        });
        let build = |n| commands.send(Command::Build(Value::from(n))).unwrap();
        build(1);
        build(2);
        let writer = thread::spawn(move || write_requests(write, requests));
        let timeout = Duration::from_secs(2);
        assert_eq!(lines.recv_timeout(timeout).unwrap(), "2");
        build(3);
        build(4);
        assert_eq!(
            lines.recv_timeout(Duration::from_millis(60)),
            Err(RecvTimeoutError::Timeout)
        );
        commands.send(Command::Ready).unwrap();
        assert_eq!(lines.recv_timeout(timeout).unwrap(), "4");
        commands.send(Command::Close).unwrap();
        writer.join().unwrap();
        reader.join().unwrap();
    }
}
