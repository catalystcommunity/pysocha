use crate::{Layout, OpenMode, Studio, engine::python_module, explorer::create_file};
use gpui_kit::{
    component::{
        ActiveTheme, WindowExt,
        button::{Button, ButtonVariants},
        dialog::{DialogAction, DialogClose, DialogFooter},
        input::{Input, InputState},
    },
    *,
};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs, io,
    path::{Path, PathBuf},
    process::Stdio,
};

pub fn supports(path: &Path) -> bool {
    path.extension()
        .and_then(|s| s.to_str())
        .is_some_and(|ext| {
            ["md", "markdown", "txt"]
                .iter()
                .any(|accepted| ext.eq_ignore_ascii_case(accepted))
        })
}

fn template_request(request: Value) -> io::Result<Value> {
    let mut child = python_module("pysocha.editor_template")?
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()?;
    let write = serde_json::to_writer(child.stdin.take().unwrap(), &request);
    let output = child.wait_with_output()?;
    write?;
    if !output.status.success() {
        return Err(io::Error::other(
            "The template helper stopped. Check the editor's Python runtime.",
        ));
    }
    let result: Value = serde_json::from_slice(&output.stdout)?;
    if let Some(message) = result["error"].as_str() {
        return Err(io::Error::other(message.to_owned()));
    }
    Ok(result)
}

struct TemplateForm {
    source: String,
    path: PathBuf,
    title: Entity<InputState>,
    fields: Vec<(String, Entity<InputState>)>,
    error: Option<String>,
}

impl TemplateForm {
    fn create(&self, root: &Path, cx: &App) -> io::Result<PathBuf> {
        let values: BTreeMap<_, _> = self
            .fields
            .iter()
            .map(|(name, state)| (name, state.read(cx).value().to_string()))
            .collect();
        let draft = template_request(json!({
            "source": self.source, "title": self.title.read(cx).value().as_str(), "fields": values
        }))?;
        let (Some(name), Some(text)) = (draft["filename"].as_str(), draft["text"].as_str()) else {
            return Err(io::Error::other(
                "The template helper did not return a draft.",
            ));
        };
        create_file(
            root,
            self.path.parent().unwrap(),
            name,
            Some(&self.path),
            Some(text),
        )
        .map_err(|e| {
            if e.kind() == io::ErrorKind::AlreadyExists {
                io::Error::other(format!("{name} already exists. Choose a different title."))
            } else {
                e
            }
        })
    }
}

impl Render for TemplateForm {
    fn render(&mut self, _: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let field = |name: String, state: &Entity<InputState>| {
            div()
                .flex()
                .flex_col()
                .gap_1()
                .child(name.clone())
                .child(Input::new(state).aria_label(name))
        };
        let mut inputs = div()
            .id("template-fields")
            .overflow_y_scroll()
            .flex()
            .flex_col()
            .max_h(px(340.))
            .gap_3()
            .child(field("Title".into(), &self.title));
        for (name, state) in &self.fields {
            inputs = inputs.child(field(name.clone(), state));
        }
        let mut form = div().flex().flex_col().gap_3().child(inputs);
        if let Some(error) = &self.error {
            form = form.child(div().text_color(cx.theme().danger).child(error.clone()));
        }
        form
    }
}

impl Studio {
    pub(super) fn start_template(
        &mut self,
        path: PathBuf,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let Some(root) = self.root().map(Path::to_path_buf) else {
            return;
        };
        let read = || -> io::Result<(String, Vec<String>)> {
            let resolved = path.canonicalize()?;
            if !resolved.starts_with(&root) {
                return Err(io::Error::other(
                    "Select a template inside the site folder.",
                ));
            }
            let source = match self.files.get(&resolved).filter(|doc| doc.dirty) {
                Some(doc) => doc.state.read(cx).value().to_string(),
                None => fs::read_to_string(&resolved)?,
            };
            let response = template_request(json!({"source": source}))?;
            Ok((source, serde_json::from_value(response["fields"].clone())?))
        };
        let (source, names) = match read() {
            Ok(data) => data,
            Err(e) => {
                self.status = format!("Could not open the template. {e}");
                cx.notify();
                return;
            }
        };
        let title = cx.new(|cx| InputState::new(window, cx).placeholder("Title for the new file"));
        let fields = names
            .into_iter()
            .map(|name| (name, cx.new(|cx| InputState::new(window, cx))))
            .collect();
        let heading = format!(
            "New draft from {}",
            path.file_name().unwrap().to_string_lossy()
        );
        let form = cx.new(|_| TemplateForm {
            source,
            path,
            title: title.clone(),
            fields,
            error: None,
        });
        if let Some(web) = &self.web {
            web.update(cx, |view, _| view.hide());
        }
        let studio = cx.weak_entity();
        window.open_dialog(cx, move |dialog, _, _| {
            let submit = form.clone();
            let owner = studio.clone();
            let restore = studio.clone();
            let root = root.clone();
            dialog
                .title(heading.clone())
                .centered()
                .w(px(450.))
                .child(form.clone())
                .footer(
                    DialogFooter::new()
                        .child(DialogClose::new().trigger(|b| b.label("Cancel")))
                        .child(
                            DialogAction::new()
                                .child(Button::new("create-draft").primary().label("Create file")),
                        ),
                )
                .on_ok(move |_, window, cx| {
                    let created = submit.read(cx).create(&root, cx);
                    match created {
                        Ok(p) => {
                            let _ = owner.update(cx, |s, cx| {
                                s.open_file(p, OpenMode::Keep, window, cx);
                                s.schedule(cx);
                            });
                            true
                        }
                        Err(e) => {
                            submit.update(cx, |f, cx| {
                                f.error = Some(e.to_string());
                                cx.notify();
                            });
                            false
                        }
                    }
                })
                .on_close(move |_, _, cx| {
                    let _ = restore.update(cx, |s, cx| {
                        if s.layout != Layout::Source {
                            if let Some(web) = &s.web {
                                web.update(cx, |view, _| view.show());
                            }
                        }
                    });
                })
        });
        title.update(cx, |input, cx| input.focus(window, cx));
    }
}
