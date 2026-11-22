use gpui_kit::Window;
use raw_window_handle::{HasWindowHandle, RawWindowHandle};
use x11rb::{
    connection::Connection,
    protocol::xproto::{AtomEnum, ConnectionExt, PropMode},
    wrapper::ConnectionExt as _,
};

// X11 window managers use _NET_WM_ICON for the task switcher and dock,
// including when the editor runs directly from an extracted archive.
pub fn set(window: &Window) -> Result<(), Box<dyn std::error::Error>> {
    let id = match HasWindowHandle::window_handle(window)?.as_raw() {
        RawWindowHandle::Xlib(h) => h.window.try_into()?,
        RawWindowHandle::Xcb(h) => h.window.get(),
        _ => return Ok(()),
    };
    let icon = image::load_from_memory(include_bytes!("../assets/pysocha-128.png"))?.to_rgba8();
    let mut pixels = vec![icon.width(), icon.height()];
    pixels.extend(
        icon.pixels()
            .map(|p| u32::from_be_bytes([p[3], p[0], p[1], p[2]])),
    );
    let (display, _) = x11rb::connect(None)?;
    let atom = display.intern_atom(false, b"_NET_WM_ICON")?.reply()?.atom;
    display
        .change_property32(PropMode::REPLACE, id, atom, AtomEnum::CARDINAL, &pixels)?
        .check()?;
    display.flush()?;
    Ok(())
}
