#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

mod engine;
mod toast;

use base64::Engine as _;
use engine::Engine;
use gpui_kit::{
    component::{
        ActiveTheme, Selectable, Theme, ThemeMode,
        button::{Button, ButtonVariants},
        input::{Editor, EditorState, InputEvent},
    },
    prelude::FluentBuilder as _,
    *,
};
use gpui_webview::WebView;
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    collections::BTreeMap,
    fs,
    io::Write,
    path::{Path, PathBuf},
    rc::Rc,
    sync::Arc,
    time::{Duration, Instant},
};
use toast::Toast;

gpui_kit::actions!(studio, [SaveFile, OpenFile]);

#[derive(Clone, Copy, PartialEq)]
enum Layout {
    Source,
    Preview,
    Columns,
    Rows,
}

struct Document {
    state: Entity<EditorState>,
    saved: String,
    dirty: bool,
    _subscription: Subscription,
}

struct Studio {
    focus: FocusHandle,
    config: Option<PathBuf>,
    files: BTreeMap<PathBuf, Document>,
    active: Option<PathBuf>,
    engine: Option<Engine>,
    web: Option<Entity<WebView>>,
    browser_error: Option<String>,
    origin: Rc<RefCell<String>>,
    metadata: Rc<RefCell<Option<Value>>>,
    url: String,
    title: String,
    icon: Option<Arc<Image>>,
    layout: Layout,
    dark: bool,
    template: Option<PathBuf>,
    toast: Toast,
    status: String,
    revision: u64,
    due: Option<Instant>,
    in_flight: bool,
    follow_file: bool,
}

impl Studio {
    fn new(window: &mut Window, cx: &mut Context<Self>) -> Self {
        let metadata = Rc::new(RefCell::new(None));
        let inbox = Rc::clone(&metadata);
        let origin = Rc::new(RefCell::new(String::new()));
        let allowed = Rc::clone(&origin);
        let builder = wry::WebViewBuilder::new()
            .with_visible(false)
            .with_navigation_handler(move |url| {
                url == "about:blank" || url.starts_with(&format!("{}/", allowed.borrow()))
            })
            .with_new_window_req_handler(|_, _| wry::NewWindowResponse::Deny)
            .with_initialization_script(include_str!("tab.js"))
            .with_ipc_handler(move |request| {
                if request.body().len() < 32_768 {
                    *inbox.borrow_mut() = serde_json::from_str(request.body()).ok();
                }
            });
        let (web, status) = match WebView::build(builder, window, cx) {
            Ok(view) => (
                Some(cx.new(|_| view)),
                "Open the YAML configuration for your site.".into(),
            ),
            Err(e) => (None, format!("The browser preview could not start: {e}")),
        };
        let this = cx.weak_entity();
        window.on_window_should_close(cx, move |_, cx| {
            this.upgrade()
                .is_none_or(|studio| studio.read(cx).confirm_discard())
        });
        cx.spawn(async move |studio, cx| {
            loop {
                cx.background_executor()
                    .timer(Duration::from_millis(100))
                    .await;
                if studio.update(cx, |this, cx| this.tick(cx)).is_err() {
                    break;
                }
            }
        })
        .detach();
        Self {
            focus: cx.focus_handle(),
            config: None,
            files: BTreeMap::new(),
            active: None,
            engine: None,
            browser_error: web.is_none().then(|| status.clone()),
            web,
            origin,
            metadata,
            url: String::new(),
            title: "Preview".into(),
            icon: None,
            layout: Layout::Columns,
            dark: cx.theme().mode.is_dark(),
            template: None,
            toast: Toast::default(),
            status,
            revision: 0,
            due: None,
            in_flight: false,
            follow_file: false,
        }
    }

    fn confirm_discard(&self) -> bool {
        !self.files.values().any(|f| f.dirty)
            || rfd::MessageDialog::new()
                .set_title("Discard unsaved changes?")
                .set_description(
                    "Your edits are still open. Save each changed file to keep your work.",
                )
                .set_buttons(rfd::MessageButtons::YesNo)
                .show()
                == rfd::MessageDialogResult::Yes
    }

    fn open_site(&mut self, path: PathBuf, window: &mut Window, cx: &mut Context<Self>) {
        if !self.confirm_discard() {
            return;
        }
        let result = path
            .canonicalize()
            .and_then(|p| Engine::open(&p).map(|e| (p, e)));
        match result {
            Ok((p, engine)) => {
                self.engine = Some(engine);
                self.config = Some(p.clone());
                self.files.clear();
                self.active = None;
                self.template = None;
                self.url.clear();
                self.origin.borrow_mut().clear();
                self.metadata.borrow_mut().take();
                self.title = "Preview".into();
                self.icon = None;
                if let Some(web) = &self.web {
                    web.update(cx, |w, _| {
                        w.load_url("about:blank");
                        if self.layout != Layout::Source {
                            w.show();
                        }
                    });
                }
                self.toast.clear();
                self.in_flight = false;
                self.status = "Building preview…".into();
                self.open_file(p, window, cx);
                self.schedule();
            }
            Err(e) => self.status = format!("Could not open the preview engine. {e}"),
        }
        cx.notify();
    }

    fn root(&self) -> Option<&Path> {
        self.config.as_deref()?.parent()
    }

    fn open_file(&mut self, path: PathBuf, window: &mut Window, cx: &mut Context<Self>) {
        let Some(root) = self.root() else { return };
        let Ok(path) = path.canonicalize() else {
            self.status = "This file no longer exists.".into();
            return;
        };
        if !path.starts_with(root) {
            self.status = "Select a file inside the open site folder.".into();
            cx.notify();
            return;
        }
        if !self.files.contains_key(&path) {
            let saved = match fs::read_to_string(&path) {
                Ok(text) => text,
                Err(e) => {
                    self.status = format!("Could not open this text file. {e}");
                    cx.notify();
                    return;
                }
            };
            let language = match path.extension().and_then(|e| e.to_str()).unwrap_or("") {
                "md" => "markdown",
                "jinja2" | "jinja" | "j2" => "Jinja2",
                "yml" => "yaml",
                "js" => "javascript",
                other => other,
            };
            let state = cx.new(|cx| {
                EditorState::new(window, cx)
                    .language(language.to_owned())
                    .default_value(saved.clone())
            });
            let key = path.clone();
            let subscription = cx.subscribe(&state, move |this, input, event: &InputEvent, cx| {
                if matches!(event, InputEvent::Change) {
                    if let Some(doc) = this.files.get_mut(&key) {
                        doc.dirty = input.read(cx).value().as_str() != doc.saved;
                    }
                    this.schedule();
                    cx.notify();
                }
            });
            self.files.insert(
                path.clone(),
                Document {
                    state,
                    saved,
                    dirty: false,
                    _subscription: subscription,
                },
            );
        }
        self.active = Some(path);
        self.follow_file = true;
        self.schedule();
        if self.layout == Layout::Preview {
            self.set_layout(Layout::Source, cx);
        }
        cx.notify();
    }

    fn close_active(&mut self, cx: &mut Context<Self>) {
        let Some(path) = &self.active else {
            return;
        };
        if self.files[path].dirty
            && rfd::MessageDialog::new()
                .set_title("Discard changes to this file?")
                .set_description(format!("Close {} without saving?", path.display()))
                .set_buttons(rfd::MessageButtons::YesNo)
                .show()
                != rfd::MessageDialogResult::Yes
        {
            return;
        }
        self.files.remove(path);
        self.active = self.files.keys().next_back().cloned();
        self.follow_file = true;
        self.schedule();
        cx.notify();
    }

    fn pick_file(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        if let Some(root) = self.root() {
            if let Some(path) = rfd::FileDialog::new().set_directory(root).pick_file() {
                self.open_file(path, window, cx);
            }
        }
    }

    fn new_file(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        let Some(root) = self.root() else { return };
        let Some(path) = rfd::FileDialog::new()
            .set_directory(root)
            .set_file_name("page.md")
            .save_file()
        else {
            return;
        };
        if !path
            .parent()
            .and_then(|p| p.canonicalize().ok())
            .is_some_and(|p| p.starts_with(root))
        {
            self.status = "Create the file inside the open site folder.".into();
        } else {
            match fs::File::create_new(&path) {
                Ok(_) => self.open_file(path, window, cx),
                Err(e) => self.status = format!("Could not create the file. {e}"),
            }
        }
        cx.notify();
    }

    fn save(&mut self, cx: &mut Context<Self>) {
        let Some(path) = self.active.as_ref() else {
            return;
        };
        let doc = self.files.get_mut(path).unwrap();
        let write = || -> std::io::Result<String> {
            if fs::read_to_string(path)? != doc.saved {
                return Err(std::io::Error::other(
                    "The file changed on disk. Copy your edits before reopening it.",
                ));
            }
            let text = doc.state.read(cx).value().to_string();
            let mut temp = tempfile::NamedTempFile::new_in(path.parent().unwrap())?;
            temp.as_file()
                .set_permissions(fs::metadata(path)?.permissions())?;
            temp.write_all(text.as_bytes())?;
            temp.persist(path)?;
            Ok(text)
        };
        match write() {
            Ok(text) => {
                doc.saved = text;
                doc.dirty = false;
                self.status = "Saved".into();
                self.schedule();
            }
            Err(e) => self.status = format!("Could not save the file. {e}"),
        }
        cx.notify();
    }

    fn schedule(&mut self) {
        self.revision += 1;
        self.due = Some(Instant::now() + Duration::from_millis(400));
    }

    fn tick(&mut self, cx: &mut Context<Self>) {
        let now = Instant::now();
        if self.toast.tick(now) {
            cx.notify();
        }
        let events: Vec<_> = self
            .engine
            .iter()
            .flat_map(|engine| engine.output.try_iter())
            .collect();
        for event in events {
            if let Some(origin) = event["origin"].as_str() {
                *self.origin.borrow_mut() = origin.to_owned();
            } else if event["stopped"] == true {
                self.engine = None;
                self.status = "The preview engine stopped. Reopen the site to restart it.".into();
            } else {
                self.in_flight = false;
                if event["revision"].as_u64() != Some(self.revision) {
                    continue;
                }
                if let Some(error) = event["error"].as_str() {
                    self.toast.error(error.into(), now);
                    self.status =
                        "Build failed. The preview shows the last successful build.".into();
                } else if let Some(start) = event["start"].as_str() {
                    self.toast.clear();
                    self.status = "Preview up to date".into();
                    let page = event["page"].as_str();
                    let first = self.url.is_empty() || (self.follow_file && page.is_some());
                    self.follow_file = false;
                    if first {
                        self.url = format!("{}{}", self.origin.borrow(), page.unwrap_or(start));
                    }
                    if let Some(web) = &self.web {
                        web.update(cx, |view, _| {
                            if first {
                                view.load_url(&self.url);
                            } else {
                                let _ = view.raw().reload();
                            }
                        });
                    }
                }
            }
            cx.notify();
        }
        if let Some(meta) = self.metadata.borrow_mut().take() {
            if let Some(url) = meta["page"]
                .as_str()
                .filter(|u| u.starts_with(&format!("{}/", self.origin.borrow())))
            {
                self.url = url.into();
                self.title = meta["title"]
                    .as_str()
                    .filter(|s| !s.is_empty())
                    .unwrap_or("Preview")
                    .chars()
                    .take(160)
                    .collect();
                self.icon = meta["png"]
                    .as_str()
                    .filter(|s| !s.is_empty())
                    .and_then(|s| base64::engine::general_purpose::STANDARD.decode(s).ok())
                    .map(|buf| Arc::new(Image::from_bytes(ImageFormat::Png, buf)));
                cx.notify();
            }
        }
        if !self.in_flight && self.due.is_some_and(|due| due <= now) {
            self.due = None;
            if let (Some(engine), Some(root)) = (&self.engine, self.root()) {
                let edits: BTreeMap<_, _> = self
                    .files
                    .iter()
                    .filter(|(_, f)| f.dirty)
                    .map(|(p, f)| {
                        (
                            p.strip_prefix(root).unwrap(),
                            f.state.read(cx).value().to_string(),
                        )
                    })
                    .collect();
                self.in_flight = engine
                    .input
                    .send(json!({
                        "revision": self.revision, "edits": edits, "templates": self.template,
                        "active": self.active.as_ref().and_then(|p| p.strip_prefix(root).ok())
                    }))
                    .is_ok();
                self.status = "Building preview…".into();
                cx.notify();
            }
        }
    }

    fn set_layout(&mut self, layout: Layout, cx: &mut Context<Self>) {
        if layout == Layout::Source {
            self.toast.hover(false, Instant::now());
        }
        self.layout = layout;
        if let Some(web) = &self.web {
            web.update(cx, |view, _| {
                if layout == Layout::Source {
                    view.hide();
                } else {
                    view.show();
                }
            });
        }
        cx.notify();
    }
}

impl Render for Studio {
    fn render(&mut self, _: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let panel = || div().flex_1().min_w_0().min_h_0().overflow_hidden();
        let bar = || {
            div()
                .flex()
                .flex_row()
                .items_center()
                .gap_1()
                .px_2()
                .py_1()
                .border_b_1()
                .border_color(cx.theme().border)
        };
        let open =
            Button::new("site")
                .label("Open site")
                .on_click(cx.listener(|this, _, w, cx| {
                    if let Some(p) = rfd::FileDialog::new()
                        .add_filter("Site configuration", &["yaml", "yml"])
                        .pick_file()
                    {
                        this.open_site(p, w, cx);
                    }
                }));
        let mut tools = bar().child(open);
        if self.config.is_some() {
            tools = tools
                .child(
                    Button::new("file")
                        .ghost()
                        .label("Open file")
                        .on_click(cx.listener(|s, _, w, c| s.pick_file(w, c))),
                )
                .child(
                    Button::new("new")
                        .ghost()
                        .label("New file")
                        .on_click(cx.listener(|s, _, w, c| s.new_file(w, c))),
                )
                .child(
                    Button::new("save")
                        .ghost()
                        .label("Save")
                        .on_click(cx.listener(|s, _, _, c| s.save(c))),
                )
                .child(
                    Button::new("templates")
                        .ghost()
                        .label("Site theme…")
                        .on_click(cx.listener(|s, _, _, cx| {
                            if let Some(root) = s.root() {
                                if let Some(p) = rfd::FileDialog::new()
                                    .set_directory(root)
                                    .set_title("Select a site template folder")
                                    .pick_folder()
                                {
                                    if let Ok(rel) = p.strip_prefix(root) {
                                        s.template = Some(rel.to_owned());
                                        s.schedule();
                                    } else {
                                        s.status =
                                            "Select a template folder inside the site.".into();
                                    }
                                    cx.notify();
                                }
                            }
                        })),
                );
            if self.active.is_some() {
                tools = tools.child(
                    Button::new("close-file")
                        .ghost()
                        .label("Close file")
                        .on_click(cx.listener(|s, _, _, cx| s.close_active(cx))),
                );
            }
            if self.template.is_some() {
                tools = tools.child(
                    Button::new("reset-theme")
                        .ghost()
                        .label("Use site default")
                        .on_click(cx.listener(|s, _, _, cx| {
                            s.template = None;
                            s.schedule();
                            cx.notify();
                        })),
                );
            }
        }
        tools = tools.child(div().flex_1()).child(
            Button::new("theme")
                .ghost()
                .label(if self.dark {
                    "Light appearance"
                } else {
                    "Dark appearance"
                })
                .on_click(cx.listener(|s, _, w, cx| {
                    s.dark = !s.dark;
                    Theme::change(
                        if s.dark {
                            ThemeMode::Dark
                        } else {
                            ThemeMode::Light
                        },
                        Some(w),
                        cx,
                    );
                    if let Some(web) = &s.web {
                        let _ = web.read(cx).set_theme(if s.dark {
                            wry::Theme::Dark
                        } else {
                            wry::Theme::Light
                        });
                    }
                    cx.notify();
                })),
        );
        let mut tabs = bar().id("tabs").overflow_x_scroll();
        for (i, (path, doc)) in self.files.iter().enumerate() {
            let p = path.clone();
            let name = p.strip_prefix(self.root().unwrap()).unwrap_or(&p).display();
            let label = format!("{}{}", name, if doc.dirty { " •" } else { "" });
            tabs = tabs.child(
                Button::new(("doc", i))
                    .ghost()
                    .selected(self.active.as_ref() == Some(path) && self.layout != Layout::Preview)
                    .label(label)
                    .on_click(cx.listener(move |s, _, _, cx| {
                        s.active = Some(p.clone());
                        s.follow_file = true;
                        s.schedule();
                        if s.layout == Layout::Preview {
                            s.set_layout(Layout::Source, cx);
                        }
                        cx.notify();
                    })),
            );
        }
        let preview_tab = Button::new("preview")
            .when_some(self.icon.clone(), |b, icon| b.child(img(icon).size_4()))
            .ghost()
            .selected(self.layout == Layout::Preview)
            .label(self.title.clone())
            .on_click(cx.listener(|s, _, _, cx| s.set_layout(Layout::Preview, cx)));
        tabs = tabs.child(preview_tab);
        let mut layouts = bar();
        for (id, label, layout) in [
            ("source", "Editor", Layout::Source),
            ("columns", "Side by side", Layout::Columns),
            ("rows", "Stacked", Layout::Rows),
        ] {
            layouts = layouts.child(
                Button::new(id)
                    .ghost()
                    .selected(self.layout == layout)
                    .label(label)
                    .on_click(cx.listener(move |s, _, _, cx| s.set_layout(layout, cx))),
            );
        }
        layouts = layouts.child(
            Button::new("back")
                .ghost()
                .label("Back")
                .on_click(cx.listener(|s, _, _, cx| {
                    if let Some(web) = &s.web {
                        let _ = web.update(cx, |v, _| v.back());
                    }
                })),
        );
        let mut panes = panel()
            .flex()
            .when(self.layout == Layout::Rows, |d| d.flex_col());
        if self.layout != Layout::Preview {
            if let Some(file) = self.active.as_ref().and_then(|p| self.files.get(p)) {
                panes = panes.child(
                    panel().child(
                        Editor::new(&file.state)
                            .h(relative(1.))
                            .aria_label("Site source"),
                    ),
                );
            }
        }
        if self.layout != Layout::Source {
            let mut preview = panel()
                .flex()
                .flex_col()
                .border_1()
                .border_color(cx.theme().border);
            if let Some(reason) = &self.browser_error {
                preview = preview.child(div().p_3().child(reason.clone()));
            }
            if let Some(message) = self.toast.message() {
                preview = preview.child(
                    div()
                        .id("build-error")
                        .p_3()
                        .bg(cx.theme().popover)
                        .text_color(cx.theme().popover_foreground)
                        .border_l_4()
                        .border_color(cx.theme().warning)
                        .on_hover(
                            cx.listener(|s, inside, _, _| s.toast.hover(*inside, Instant::now())),
                        )
                        .child(
                            div()
                                .font_weight(FontWeight::SEMIBOLD)
                                .child("Hover over this messsage to prevent it disappearing"),
                        )
                        .child(div().child(message.to_owned())),
                );
            }
            preview = preview.when_some(self.web.clone(), |p, web| p.child(panel().child(web)));
            panes = panes.child(preview);
        }
        div()
            .size_full()
            .flex()
            .flex_col()
            .track_focus(&self.focus)
            .bg(cx.theme().background)
            .text_color(cx.theme().foreground)
            .on_action(cx.listener(|s, _: &SaveFile, _, cx| s.save(cx)))
            .on_action(cx.listener(|s, _: &OpenFile, w, cx| s.pick_file(w, cx)))
            .child(tools)
            .when(self.config.is_some(), |v| {
                v.child(tabs).child(layouts).child(panes)
            })
            .child(div().px_3().py_2().text_sm().child(self.status.clone()))
    }
}

fn main() {
    #[cfg(target_os = "windows")]
    unsafe {
        std::env::set_var("GPUI_DISABLE_DIRECT_COMPOSITION", "true");
    }
    #[cfg(target_os = "linux")]
    let app = gpui_kit::platform::linux(WindowingModes::X11);
    #[cfg(not(target_os = "linux"))]
    let app = gpui_kit::application();
    let config = std::env::args_os().nth(1).map(PathBuf::from);
    app.with_assets(gpui_kit::assets::Assets).run(move |cx| {
        gpui_kit::init(cx);
        cx.bind_keys([
            KeyBinding::new(
                if cfg!(target_os = "macos") {
                    "cmd-s"
                } else {
                    "ctrl-s"
                },
                SaveFile,
                None,
            ),
            KeyBinding::new(
                if cfg!(target_os = "macos") {
                    "cmd-o"
                } else {
                    "ctrl-o"
                },
                OpenFile,
                None,
            ),
        ]);
        let options = WindowOptions {
            titlebar: Some(TitlebarOptions {
                title: Some("Pysocha Editor".into()),
                ..Default::default()
            }),
            ..Default::default()
        };
        gpui_kit::open_window(options, cx, move |w, cx| {
            cx.new(|cx| {
                let mut studio = Studio::new(w, cx);
                if let Some(path) = config {
                    studio.open_site(path, w, cx);
                }
                studio
            })
        })
        .expect("Open the desktop window");
        cx.on_window_closed(|cx, _| {
            if cx.windows().is_empty() {
                cx.quit();
            }
        })
        .detach();
        cx.activate(true);
    });
}
