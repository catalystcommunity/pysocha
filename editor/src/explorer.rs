use crate::{OpenMode, Studio};
use gpui_kit::{
    component::{
        ActiveTheme, Disableable, Icon, IconName, Sizable,
        button::{Button, ButtonVariants},
        input::{Escape, Input, InputEvent, InputState},
        menu::{ContextMenuExt, PopupMenuItem},
        scroll::ScrollableElement,
    },
    prelude::FluentBuilder as _,
    *,
};
use std::{
    collections::BTreeSet,
    fs,
    io::{self, Write},
    path::{Path, PathBuf},
};

struct Entry {
    path: PathBuf,
    depth: usize,
    folder: bool,
    error: Option<String>,
}

struct NamePrompt {
    folder: PathBuf,
    source: Option<PathBuf>,
    input: Entity<InputState>,
    error: Option<String>,
    _subscription: Subscription,
}

#[derive(Default)]
pub(super) struct Explorer {
    collapsed: bool,
    expanded: BTreeSet<PathBuf>,
    rows: Vec<Entry>,
    selected: Option<PathBuf>,
    scroll: UniformListScrollHandle,
    prompt: Option<NamePrompt>,
}

impl Explorer {
    pub(super) fn reset(&mut self) {
        *self = Self {
            collapsed: self.collapsed,
            ..Self::default()
        };
    }

    fn refresh(&mut self, root: &Path) {
        self.rows.clear();
        self.append(root, 0, true);
    }

    fn append(&mut self, path: &Path, depth: usize, folder: bool) {
        let index = self.rows.len();
        self.rows.push(Entry {
            path: path.to_owned(),
            depth,
            folder,
            error: None,
        });
        if !folder || !self.expanded.contains(path) {
            return;
        }
        match folder_entries(path) {
            Ok(children) => {
                for (folder, child) in children {
                    self.append(&child, depth + 1, folder);
                }
            }
            Err(error) => {
                self.rows[index].error =
                    Some(format!("Could not read {}. {error}", path.display()));
            }
        }
    }

    pub(super) fn reveal(&mut self, root: &Path, path: &Path) {
        if !self.rows.iter().any(|row| row.path == path) {
            self.expanded.extend(
                path.ancestors()
                    .skip(1)
                    .take_while(|ancestor| ancestor.starts_with(root))
                    .map(Path::to_owned),
            );
            self.refresh(root);
        }
        self.selected = Some(path.to_owned());
        if let Some(index) = self.rows.iter().position(|row| row.path == path) {
            self.scroll.scroll_to_item(index, ScrollStrategy::Nearest);
        }
    }

    fn selected_entry(&self) -> Option<&Entry> {
        self.rows
            .iter()
            .find(|row| Some(&row.path) == self.selected.as_ref())
    }
}

fn folder_entries(path: &Path) -> io::Result<Vec<(bool, PathBuf)>> {
    let mut children = Vec::new();
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        let kind = entry.file_type()?;
        if entry.file_name() != ".git" && (kind.is_file() || kind.is_dir()) {
            children.push((kind.is_dir(), entry.path()));
        }
    }
    children.sort_by(|(dir_a, a), (dir_b, b)| dir_b.cmp(dir_a).then_with(|| a.cmp(b)));
    Ok(children)
}

fn copy_name(path: &Path) -> String {
    let stem = path.file_stem().unwrap_or_default().to_string_lossy();
    match path.extension() {
        Some(ext) => format!("{stem} copy.{}", ext.to_string_lossy()),
        None => format!("{stem} copy"),
    }
}

// The destination only becomes visible once the whole copy has been written.
pub(super) fn create_file(
    root: &Path,
    folder: &Path,
    name: &str,
    source: Option<&Path>,
    edits: Option<&str>,
) -> io::Result<PathBuf> {
    if name.trim().is_empty() || Path::new(name).file_name() != Some(name.as_ref()) {
        return Err(io::Error::other("Enter a file name without a folder path."));
    }
    let folder = folder.canonicalize()?;
    if !folder.starts_with(root) {
        return Err(io::Error::other("Choose a folder inside this site."));
    }
    let path = folder.join(name);
    if let Some(source) = source {
        let source = source.canonicalize()?;
        if !source.starts_with(root) || !source.is_file() {
            return Err(io::Error::other("Choose a file inside this site."));
        }
        let mut copy = tempfile::NamedTempFile::new_in(folder)?;
        match edits {
            Some(text) => copy.write_all(text.as_bytes())?,
            None => {
                io::copy(&mut fs::File::open(&source)?, &mut copy)?;
            }
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = fs::metadata(&source)?.permissions().mode() & 0o777;
            copy.as_file()
                .set_permissions(fs::Permissions::from_mode(mode))?;
        }
        copy.persist_noclobber(&path).map_err(|e| e.error)?;
    } else {
        fs::File::create_new(&path)?;
    }
    Ok(path)
}

impl Studio {
    fn start_name(&mut self, duplicate: bool, window: &mut Window, cx: &mut Context<Self>) {
        let Some(root) = self.root() else { return };
        let selected = self.explorer.selected_entry();
        let folder = selected
            .and_then(|entry| {
                if entry.folder {
                    Some(entry.path.as_path())
                } else {
                    entry.path.parent()
                }
            })
            .unwrap_or(root)
            .to_owned();
        let source = if duplicate {
            let Some(file) = selected.filter(|entry| !entry.folder) else {
                return;
            };
            Some(file.path.clone())
        } else {
            None
        };
        let name = source
            .as_deref()
            .map(copy_name)
            .unwrap_or_else(|| "page.md".into());
        let input = cx.new(|cx| InputState::new(window, cx).default_value(name));
        let subscription = cx.subscribe_in(&input, window, |this, _, event: &InputEvent, w, cx| {
            if matches!(event, InputEvent::PressEnter { .. }) {
                this.finish_name(w, cx);
            }
        });
        input.update(cx, |input, cx| {
            input.focus(window, cx);
            input.select_all(window, cx);
        });
        self.explorer.collapsed = false;
        self.explorer.prompt = Some(NamePrompt {
            folder,
            source,
            input,
            error: None,
            _subscription: subscription,
        });
        cx.notify();
    }

    fn finish_name(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        let Some(prompt) = &self.explorer.prompt else {
            return;
        };
        let source = prompt.source.as_deref();
        let edits = source
            .and_then(|p| self.files.get(p))
            .filter(|doc| doc.dirty)
            .map(|doc| doc.state.read(cx).value().to_string());
        let root = self.root().unwrap();
        let result = create_file(
            root,
            &prompt.folder,
            prompt.input.read(cx).value().as_str(),
            source,
            edits.as_deref(),
        );
        match result {
            Ok(path) => {
                self.explorer.prompt = None;
                self.open_file(path, OpenMode::Keep, window, cx);
                self.schedule(cx);
            }
            Err(error) => {
                self.explorer.prompt.as_mut().unwrap().error =
                    Some(if error.kind() == io::ErrorKind::AlreadyExists {
                        "That name is already in use. Choose another name.".into()
                    } else {
                        error.to_string()
                    });
            }
        }
        cx.notify();
    }

    fn choose_entry(
        &mut self,
        index: usize,
        mode: OpenMode,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let row = &self.explorer.rows[index];
        let path = row.path.clone();
        self.explorer.prompt = None;
        if row.folder {
            if !self.explorer.expanded.remove(&path) {
                self.explorer.expanded.insert(path.clone());
            }
            self.explorer.selected = Some(path);
            self.explorer
                .refresh(self.config.as_deref().unwrap().parent().unwrap());
        } else {
            self.open_file(path, mode, window, cx);
        }
        cx.notify();
    }

    fn tree_key(&mut self, event: &KeyDownEvent, window: &mut Window, cx: &mut Context<Self>) {
        let rows = &self.explorer.rows;
        if rows.is_empty() || event.keystroke.modifiers != Modifiers::default() {
            return;
        }
        let index = rows
            .iter()
            .position(|r| Some(&r.path) == self.explorer.selected.as_ref())
            .unwrap_or(0);
        let row = &rows[index];
        let expanded = self.explorer.expanded.contains(&row.path);
        let next = match event.keystroke.key.as_str() {
            "up" => index.saturating_sub(1),
            "down" => (index + 1).min(rows.len() - 1),
            "left" if !expanded => rows[..index]
                .iter()
                .rposition(|r| r.depth < row.depth)
                .unwrap_or(index),
            "right" if expanded => {
                if rows.get(index + 1).is_some_and(|r| r.depth > row.depth) {
                    index + 1
                } else {
                    index
                }
            }
            "enter" | "space" => {
                self.choose_entry(index, OpenMode::Keep, window, cx);
                return;
            }
            "right" | "left" if row.folder => {
                self.choose_entry(index, OpenMode::Keep, window, cx);
                return;
            }
            _ => return,
        };
        self.explorer.selected = Some(rows[next].path.clone());
        self.explorer
            .scroll
            .scroll_to_item(next, ScrollStrategy::Nearest);
        cx.notify();
    }

    fn tree_row(&self, index: usize, cx: &Context<Self>) -> impl IntoElement + use<> {
        let row = &self.explorer.rows[index];
        let path = row.path.clone();
        let folder = row.folder;
        let expanded = self.explorer.expanded.contains(&path);
        let selected = self.explorer.selected.as_ref() == Some(&path);
        let dirty = self.files.get(&path).is_some_and(|doc| doc.dirty);
        let label = path
            .file_name()
            .unwrap_or(path.as_os_str())
            .to_string_lossy()
            .into_owned();
        let highlight = cx.theme().sidebar_accent;
        let entry = div()
            .id(("entry", index))
            .w_full()
            .role(Role::TreeItem)
            .aria_label(label.clone())
            .aria_selected(selected)
            .flex()
            .items_center()
            .h_7()
            .pr_2()
            .gap_1()
            .pl(px(8. + 12. * row.depth as f32))
            .cursor_pointer()
            .text_sm()
            .hover(|s| s.bg(highlight))
            .when(selected, |d| {
                d.bg(highlight).font_weight(FontWeight::SEMIBOLD)
            })
            .when(folder, |d| d.aria_expanded(expanded))
            .child(div().w_3().flex_shrink_0().when(folder, |d| {
                d.child(
                    Icon::new(if expanded {
                        IconName::ChevronDown
                    } else {
                        IconName::ChevronRight
                    })
                    .size_3(),
                )
            }))
            .child(
                Icon::new(if !folder {
                    IconName::File
                } else if expanded {
                    IconName::FolderOpen
                } else {
                    IconName::Folder
                })
                .size_4(),
            )
            .child(div().min_w_0().truncate().child(label))
            .when(dirty, |d| d.child(self.unsaved_dot()))
            .on_click(cx.listener(move |s, e: &ClickEvent, w, cx| {
                if folder && e.click_count() > 1 {
                    return;
                }
                let mode = if e.click_count() == 2 {
                    OpenMode::Keep
                } else {
                    OpenMode::Temporary
                };
                s.choose_entry(index, mode, w, cx)
            }));
        if folder || !crate::template::supports(&path) {
            return entry.into_any_element();
        }
        let studio = cx.weak_entity();
        entry
            .context_menu(move |menu, _, _| {
                let studio = studio.clone();
                let path = path.clone();
                menu.item(
                    PopupMenuItem::new("Use as template…").on_click(move |_, window, cx| {
                        let path = path.clone();
                        let studio = studio.clone();
                        window.defer(cx, move |window, cx| {
                            let _ = studio.update(cx, |s, cx| s.start_template(path, window, cx));
                        });
                    }),
                )
            })
            .into_any_element()
    }

    pub(super) fn render_explorer(&self, cx: &Context<Self>) -> impl IntoElement {
        let compact = self.explorer.collapsed;
        let button = |id, label: &'static str, icon| {
            Button::new(id)
                .ghost()
                .small()
                .icon(icon)
                .accessibility_label(label)
                .tooltip(label)
        };
        let toggle = if compact { "Show files" } else { "Hide files" };
        let controls = div()
            .flex()
            .items_center()
            .gap_1()
            .p_1()
            .when(compact, |d| d.flex_col())
            .when(!compact, |d| {
                d.child(
                    div()
                        .flex_1()
                        .pl_2()
                        .text_sm()
                        .font_weight(FontWeight::SEMIBOLD)
                        .child("Files"),
                )
            })
            .child(
                button(
                    "tree-toggle",
                    toggle,
                    if compact {
                        IconName::PanelLeftOpen
                    } else {
                        IconName::PanelLeftClose
                    },
                )
                .on_click(cx.listener(|s, _, _, cx| {
                    s.explorer.collapsed = !s.explorer.collapsed;
                    if !s.explorer.collapsed {
                        s.explorer
                            .refresh(s.config.as_deref().unwrap().parent().unwrap());
                    }
                    cx.notify();
                })),
            )
            .child(
                button("tree-new", "New file", IconName::Plus)
                    .on_click(cx.listener(|s, _, w, c| s.start_name(false, w, c))),
            )
            .child(
                button("tree-copy", "Duplicate file", IconName::Copy)
                    .disabled(!self.explorer.selected_entry().is_some_and(|e| !e.folder))
                    .on_click(cx.listener(|s, _, w, c| s.start_name(true, w, c))),
            );
        let mut sidebar = div()
            .flex()
            .flex_col()
            .flex_shrink_0()
            .min_h_0()
            .w(px(if compact { 40. } else { 228. }))
            .bg(cx.theme().sidebar)
            .text_color(cx.theme().sidebar_foreground)
            .border_r_1()
            .border_color(cx.theme().sidebar_border)
            .child(controls);
        if compact {
            return sidebar;
        }
        if let Some(prompt) = &self.explorer.prompt {
            let parent = prompt
                .folder
                .strip_prefix(self.root().unwrap())
                .unwrap_or(&prompt.folder);
            let dir = if parent.as_os_str().is_empty() {
                self.root()
                    .unwrap()
                    .file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
            } else {
                parent.to_string_lossy()
            };
            let action = if prompt.source.is_some() {
                "Duplicate"
            } else {
                "Create"
            };
            sidebar = sidebar.child(
                div()
                    .flex()
                    .flex_col()
                    .gap_1()
                    .p_2()
                    .on_action(cx.listener(|s, _: &Escape, _, cx| {
                        s.explorer.prompt = None;
                        cx.notify();
                    }))
                    .child(div().text_xs().child(format!("{action} in {dir}")))
                    .child(Input::new(&prompt.input).small().aria_label("File name"))
                    .when_some(prompt.error.clone(), |d, message| {
                        d.child(div().text_xs().text_color(cx.theme().danger).child(message))
                    })
                    .child(
                        div()
                            .flex()
                            .gap_1()
                            .child(
                                Button::new("submit-name")
                                    .small()
                                    .label(action)
                                    .on_click(cx.listener(|s, _, w, c| s.finish_name(w, c))),
                            )
                            .child(
                                Button::new("cancel-name")
                                    .ghost()
                                    .small()
                                    .label("Cancel")
                                    .on_click(cx.listener(|s, _, _, c| {
                                        s.explorer.prompt = None;
                                        c.notify();
                                    })),
                            ),
                    ),
            );
        }
        let list = uniform_list(
            "site-files",
            self.explorer.rows.len(),
            cx.processor(|s, range: std::ops::Range<usize>, _, cx| {
                range.map(|i| s.tree_row(i, cx)).collect()
            }),
        )
        .size_full()
        .track_scroll(&self.explorer.scroll);
        sidebar = sidebar.child(
            div()
                .id("file-tree")
                .focusable()
                .tab_index(0)
                .on_key_down(cx.listener(|s, e, w, c| s.tree_key(e, w, c)))
                .role(Role::Tree)
                .aria_label("Site files")
                .relative()
                .flex_1()
                .min_h_0()
                .child(list)
                .vertical_scrollbar(&self.explorer.scroll),
        );
        if let Some(message) = self.explorer.rows.iter().find_map(|row| row.error.as_ref()) {
            sidebar = sidebar.child(div().text_xs().p_2().child(message.clone()));
        }
        sidebar
    }
}

#[cfg(test)]
mod tests {
    use super::{Explorer, copy_name, create_file};
    use std::{fs, io, path::Path};

    #[test]
    fn reveal_expands_only_ancestors_and_reset_drops_the_previous_site() {
        let site = tempfile::tempdir().unwrap();
        let root = site.path().canonicalize().unwrap();
        let pages = root.join("content/pages");
        fs::create_dir_all(&pages).unwrap();
        fs::create_dir(root.join("templates")).unwrap();
        fs::create_dir(root.join(".git")).unwrap();
        let config = root.join("site.yml");
        let page = pages.join("one.md");
        fs::write(&config, "").unwrap();
        fs::write(&page, "").unwrap();

        let mut tree = Explorer::default();
        tree.reveal(&root, &config);
        let visible: Vec<_> = tree
            .rows
            .iter()
            .map(|r| r.path.strip_prefix(&root).unwrap())
            .collect();
        assert_eq!(
            visible,
            ["", "content", "templates", "site.yml"].map(Path::new)
        );
        tree.reveal(&root, &page);
        assert_eq!(tree.selected_entry().unwrap().depth, 3);
        assert!(!tree.expanded.contains(&root.join("templates")));
        tree.collapsed = true;
        tree.reset();
        assert!(tree.collapsed && tree.rows.is_empty() && tree.expanded.is_empty());
        assert!(tree.selected.is_none());
    }

    #[test]
    fn named_copies_preserve_edits_and_binary_files_without_overwriting() {
        let site = tempfile::tempdir().unwrap();
        let root = site.path().canonicalize().unwrap();
        let original = create_file(&root, &root, "page.md", None, None).unwrap();
        fs::write(&original, b"saved").unwrap();
        let copy = create_file(
            &root,
            &root,
            &copy_name(&original),
            Some(&original),
            Some("edited"),
        )
        .unwrap();
        assert_eq!(fs::read(&copy).unwrap(), b"edited");
        #[cfg(unix)]
        assert_eq!(
            fs::metadata(&original).unwrap().permissions(),
            fs::metadata(&copy).unwrap().permissions()
        );
        assert_eq!(
            create_file(&root, &root, "page.md", Some(&original), Some("edited"))
                .unwrap_err()
                .kind(),
            io::ErrorKind::AlreadyExists
        );
        assert_eq!(fs::read(&original).unwrap(), b"saved");
        let image = root.join("logo.png");
        fs::write(&image, [0, 255, 4]).unwrap();
        let copy = create_file(&root, &root, "logo small.png", Some(&image), None).unwrap();
        assert_eq!(fs::read(copy).unwrap(), [0, 255, 4]);
        assert_eq!(copy_name(Path::new(".ignore")), ".ignore copy");
    }

    #[test]
    fn file_actions_are_limited_to_the_chosen_site_folder() {
        let site = tempfile::tempdir().unwrap();
        let root = site.path().canonicalize().unwrap();
        let outside = tempfile::tempdir().unwrap();
        for name in ["", "..", "../outside", "folder/page.md"] {
            assert!(create_file(&root, &root, name, None, None).is_err());
        }
        assert!(create_file(&root, outside.path(), "outside", None, None).is_err());
        #[cfg(unix)]
        {
            let link = root.join("linked");
            std::os::unix::fs::symlink(outside.path(), &link).unwrap();
            assert!(create_file(&root, &link, "outside", None, None).is_err());
        }
        assert!(!outside.path().join("outside").exists());
    }
}
