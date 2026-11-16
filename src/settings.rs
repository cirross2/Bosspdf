//! 사용자 설정 기억: 테마(다크/화이트), 썸네일 사이드바 표시, 창 크기와 위치.
//! `%APPDATA%\BossPDF\settings.ini`에 `이름=값` 줄로 저장한다.

use std::path::PathBuf;

#[derive(Clone, Debug, PartialEq)]
pub struct Settings {
    pub dark: bool,
    pub sidebar: bool,
    /// 창 크기 (논리 픽셀). 없으면 기본 크기
    pub size: Option<(f32, f32)>,
    /// 창 위치 (화면 픽셀)
    pub position: Option<(i32, i32)>,
    pub maximized: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Self { dark: false, sidebar: true, size: None, position: None, maximized: false }
    }
}

/// 설정 파일 위치. 환경 변수 BOSSPDF_SETTINGS_FILE로 바꿀 수 있다(시험용).
pub fn path() -> Option<PathBuf> {
    if let Some(custom) = std::env::var_os("BOSSPDF_SETTINGS_FILE") {
        return Some(PathBuf::from(custom));
    }
    std::env::var_os("APPDATA").map(|dir| PathBuf::from(dir).join("BossPDF").join("settings.ini"))
}

pub fn load() -> Settings {
    let mut settings = Settings::default();
    let Some(text) = path().and_then(|p| std::fs::read_to_string(p).ok()) else { return settings };
    let pair = |value: &str| -> Option<(f32, f32)> {
        let (a, b) = value.split_once(',')?;
        Some((a.trim().parse().ok()?, b.trim().parse().ok()?))
    };
    for line in text.lines() {
        let Some((key, value)) = line.split_once('=') else { continue };
        let value = value.trim();
        match key.trim() {
            "theme" => settings.dark = value == "dark",
            "sidebar" => settings.sidebar = value != "0",
            "maximized" => settings.maximized = value == "1",
            // 터무니없는 값(다른 모니터 구성에서 저장된 값 등)은 버린다
            "size" => settings.size = pair(value).filter(|(w, h)| (400.0..=10000.0).contains(w) && (300.0..=10000.0).contains(h)),
            "position" => {
                settings.position =
                    pair(value).map(|(x, y)| (x as i32, y as i32)).filter(|(x, y)| (-20000..=20000).contains(x) && (-20000..=20000).contains(y))
            }
            _ => {}
        }
    }
    settings
}

pub fn save(settings: &Settings) -> std::io::Result<()> {
    let Some(file) = path() else { return Ok(()) };
    if let Some(dir) = file.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let mut text = String::new();
    text.push_str(&format!("theme={}\n", if settings.dark { "dark" } else { "light" }));
    text.push_str(&format!("sidebar={}\n", if settings.sidebar { 1 } else { 0 }));
    text.push_str(&format!("maximized={}\n", if settings.maximized { 1 } else { 0 }));
    if let Some((w, h)) = settings.size {
        text.push_str(&format!("size={w:.0},{h:.0}\n"));
    }
    if let Some((x, y)) = settings.position {
        text.push_str(&format!("position={x},{y}\n"));
    }
    std::fs::write(file, text)
}
