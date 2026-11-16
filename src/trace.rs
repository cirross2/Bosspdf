//! 시작 과정 시간 기록 (자동 점검 보고서에 실린다)
use std::sync::{Mutex, OnceLock};
use std::time::Instant;

static START: OnceLock<Instant> = OnceLock::new();
static MARKS: Mutex<Vec<(String, u128)>> = Mutex::new(Vec::new());

pub fn init() {
    START.get_or_init(Instant::now);
}

/// 같은 이름은 처음 한 번만 기록한다
pub fn mark(label: &str) {
    let ms = START.get_or_init(Instant::now).elapsed().as_millis();
    if let Ok(mut marks) = MARKS.lock() {
        if !marks.iter().any(|m| m.0 == label) {
            marks.push((label.to_string(), ms));
        }
    }
}

pub fn dump() -> String {
    MARKS
        .lock()
        .map(|m| m.iter().map(|(l, ms)| format!("{l} {ms}ms")).collect::<Vec<_>>().join(" → "))
        .unwrap_or_default()
}
