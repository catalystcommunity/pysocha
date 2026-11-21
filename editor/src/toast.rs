use std::time::{Duration, Instant};

#[derive(Default)]
pub struct Toast {
    last: String,
    expires: Option<Instant>,
    paused: Option<Duration>,
}

impl Toast {
    pub fn error(&mut self, message: String, now: Instant) {
        if self.last != message {
            self.last = message;
            if self.paused.is_some() {
                self.paused = Some(Duration::from_secs(10));
            } else {
                self.expires = Some(now + Duration::from_secs(10));
            }
        }
    }
    pub fn clear(&mut self) {
        *self = Self::default();
    }
    pub fn message(&self) -> Option<&str> {
        (self.expires.is_some() || self.paused.is_some()).then_some(&self.last)
    }
    pub fn tick(&mut self, now: Instant) -> bool {
        if self.expires.is_some_and(|end| end <= now) {
            self.expires = None;
            return true;
        }
        false
    }
    pub fn hover(&mut self, inside: bool, now: Instant) {
        if inside {
            if let Some(end) = self.expires.take() {
                self.paused = Some(end.saturating_duration_since(now));
            }
        } else if let Some(left) = self.paused.take() {
            self.expires = Some(now + left);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn repeated_error_does_not_restart_and_hover_preserves_remaining_time() {
        let t = Instant::now();
        let at = |seconds| t + Duration::from_secs(seconds);
        let mut toast = Toast::default();
        toast.error("YAML".into(), t);
        toast.error("YAML".into(), at(6));
        toast.hover(true, at(8));
        assert!(!toast.tick(at(30)));
        toast.hover(false, at(30));
        assert!(toast.tick(at(32)));
        toast.error("YAML".into(), at(40));
        assert!(toast.message().is_none());
        toast.error("Template".into(), at(41));
        assert_eq!(toast.message(), Some("Template"));
    }
}
