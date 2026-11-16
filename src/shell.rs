//! 윈도우 탐색기 연동.
//!
//! 1. 우클릭 메뉴 등록/해제 (`--register` / `--unregister`, 현재 사용자 레지스트리만 건드림)
//!    - PDF: "BossPDF로 PDF 합치기" / 이미지: "BossPDF로 PDF 병합"
//!    키 이름과 메뉴 글자는 파이썬 버전(1.x)과 같아서, 설치하면 기존 메뉴가 그대로 새 버전을 가리킨다.
//!    보통은 설치 프로그램이 등록하고, 이 명령은 설치 없이 쓸 때를 위한 것이다.
//! 2. 여러 파일을 골라 "합치기"를 누르면 탐색기가 파일마다 프로그램을 따로 띄운다.
//!    먼저 뜬 하나(주 프로세스)만 남고, 나머지는 파일 경로를 대기열에 적고 바로 끝난다.
//! 3. 같은 문서를 또 열면 새 창을 띄우지 않고 이미 열려 있는 창을 앞으로 가져온다.

use std::collections::hash_map::DefaultHasher;
use std::ffi::c_void;
use std::hash::{Hash, Hasher};
use std::io::Write;
use std::path::PathBuf;
use std::time::Duration;

use windows_sys::Win32::Foundation::{CloseHandle, GetLastError, ERROR_ALREADY_EXISTS, INVALID_HANDLE_VALUE};
use windows_sys::Win32::System::Memory::{
    CreateFileMappingW, MapViewOfFile, OpenFileMappingW, UnmapViewOfFile, FILE_MAP_READ, FILE_MAP_WRITE, PAGE_READWRITE,
};
use windows_sys::Win32::System::Threading::CreateMutexW;
use windows_sys::Win32::UI::WindowsAndMessaging::{IsIconic, IsWindow, SetForegroundWindow, ShowWindow, SW_RESTORE};

pub const DEFAULT_REGISTRY_BASE: &str = r"Software\Classes";
const PDF_MERGE_VERB: &str = "BossPDF.MergePdfs";
const PDF_MERGE_TITLE: &str = "BossPDF로 PDF 합치기";
const IMAGE_MERGE_VERB: &str = "BossPDF.MergeToPdf";
const IMAGE_MERGE_TITLE: &str = "BossPDF로 PDF 병합";
/// 합치기 메뉴를 붙일 이미지 종류 ("image"는 윈도우가 이미지로 아는 모든 파일)
const IMAGE_CLASSES: &[&str] = &["image", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"];
/// 예전에 쓰던 메뉴 키 (해제할 때 함께 지운다): 1.x의 "BossPDF로 열기", 시제품 때의 BossPDFRust.*
const OLD_VERBS: &[&str] = &["BossPDF.Open", "BossPDFRust.Open", "BossPDFRust.Merge"];

const MERGE_MUTEX: &str = "Local\\BossPDFRust_Merge_Mutex";

fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain(std::iter::once(0)).collect()
}

// ------------------------------------------------------------------ 우클릭 메뉴 등록

fn verb_keys(base: &str) -> Vec<(String, &'static str, &'static str, bool)> {
    // (키 경로, 메뉴 글자, 명령 인자, 여러 개 선택 허용)
    let mut keys = vec![(format!(r"{base}\SystemFileAssociations\.pdf\shell\{PDF_MERGE_VERB}"), PDF_MERGE_TITLE, "--merge ", true)];
    for class in IMAGE_CLASSES {
        keys.push((format!(r"{base}\SystemFileAssociations\{class}\shell\{IMAGE_MERGE_VERB}"), IMAGE_MERGE_TITLE, "--merge ", true));
    }
    keys
}

/// 예전 버전이 만들었을 수 있는 메뉴 키들
fn old_verb_keys(base: &str) -> Vec<String> {
    let mut keys = Vec::new();
    for class in [".pdf"].iter().chain(IMAGE_CLASSES) {
        for verb in OLD_VERBS {
            keys.push(format!(r"{base}\SystemFileAssociations\{class}\shell\{verb}"));
        }
    }
    keys
}

/// 우클릭 메뉴를 등록한다. base는 보통 `Software\Classes` (HKEY_CURRENT_USER 아래)
pub fn register(base: &str, exe: &str) -> std::io::Result<usize> {
    use winreg::enums::HKEY_CURRENT_USER;
    use winreg::RegKey;
    let root = RegKey::predef(HKEY_CURRENT_USER);
    let keys = verb_keys(base);
    for (path, title, args, multi) in &keys {
        let (key, _) = root.create_subkey(path)?;
        key.set_value("", title)?;
        key.set_value("Icon", &format!("\"{exe}\",0"))?;
        if *multi {
            // 16개 이상 골라도 메뉴가 보이게 한다 (기본값은 15개까지)
            key.set_value("MultiSelectModel", &"Player")?;
        }
        let (command, _) = root.create_subkey(format!(r"{path}\command"))?;
        command.set_value("", &format!("\"{exe}\" {args}\"%1\""))?;
    }
    Ok(keys.len())
}

/// 등록한 우클릭 메뉴를 지운다 (BossPDF가 만든 키만)
pub fn unregister(base: &str) -> std::io::Result<usize> {
    use winreg::enums::HKEY_CURRENT_USER;
    use winreg::RegKey;
    let root = RegKey::predef(HKEY_CURRENT_USER);
    let mut removed = 0;
    let paths: Vec<String> = verb_keys(base).into_iter().map(|k| k.0).chain(old_verb_keys(base)).collect();
    for path in paths {
        match root.delete_subkey_all(&path) {
            Ok(()) => removed += 1,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(e) => return Err(e),
        }
    }
    Ok(removed)
}

// ------------------------------------------------------------------ 합치기: 여러 프로세스의 파일 모으기

fn queue_path() -> PathBuf {
    std::env::temp_dir().join("bosspdf_rust_merge_queue.txt")
}

/// 대기열에 쌓인 파일 경로를 모두 꺼낸다
pub fn drain_merge_queue() -> Vec<String> {
    let queue = queue_path();
    if !queue.exists() {
        return Vec::new();
    }
    // 다른 프로세스가 쓰는 중일 수 있으므로 이름을 바꿔 가져온 뒤 읽는다
    let grabbed = queue.with_extension(format!("{}.reading", std::process::id()));
    let mut moved = false;
    for _ in 0..10 {
        match std::fs::rename(&queue, &grabbed) {
            Ok(()) => {
                moved = true;
                break;
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Vec::new(),
            Err(_) => std::thread::sleep(Duration::from_millis(20)),
        }
    }
    if !moved {
        return Vec::new();
    }
    let text = std::fs::read_to_string(&grabbed).unwrap_or_default();
    let _ = std::fs::remove_file(&grabbed);
    let mut files: Vec<String> = Vec::new();
    for line in text.lines().map(str::trim).filter(|l| !l.is_empty()) {
        if std::path::Path::new(line).is_file() && !files.iter().any(|f| f == line) {
            files.push(line.to_string());
        }
    }
    files
}

/// `--merge 파일…`로 시작했을 때 부른다.
/// 이미 합치기 창을 띄운 프로세스가 있으면 파일만 넘기고 None(이 프로세스는 끝내야 함),
/// 없으면 이 프로세스가 주 프로세스가 되어 지금까지 모인 파일 목록을 돌려준다.
pub fn collect_merge(files: &[String]) -> Option<Vec<String>> {
    // 1. 내 파일을 대기열에 적는다
    for _ in 0..10 {
        let opened = std::fs::OpenOptions::new().create(true).append(true).open(queue_path());
        if let Ok(mut file) = opened {
            let mut text = String::new();
            for f in files {
                if let Ok(full) = std::fs::canonicalize(f) {
                    // canonicalize는 \\?\ 접두사를 붙인다
                    text.push_str(full.to_string_lossy().trim_start_matches(r"\\?\"));
                    text.push('\n');
                }
            }
            let _ = file.write_all(text.as_bytes());
            break;
        }
        std::thread::sleep(Duration::from_millis(20));
    }

    // 2. 주 프로세스인지 확인 (이름 있는 뮤텍스를 먼저 만든 쪽이 주 프로세스)
    let name = wide(MERGE_MUTEX);
    let mutex = unsafe { CreateMutexW(std::ptr::null(), 1, name.as_ptr()) };
    let already = unsafe { GetLastError() } == ERROR_ALREADY_EXISTS;
    if already {
        if !mutex.is_null() {
            unsafe { CloseHandle(mutex) };
        }
        return None;
    }
    // 뮤텍스는 프로세스가 끝날 때까지 쥐고 있는다 (일부러 닫지 않음)

    // 3. 같이 뜬 다른 프로세스들이 대기열에 적을 시간을 잠깐 준다
    let mut collected: Vec<String> = Vec::new();
    let mut quiet_rounds = 0;
    for _ in 0..20 {
        std::thread::sleep(Duration::from_millis(60));
        let more = drain_merge_queue();
        if more.is_empty() {
            quiet_rounds += 1;
            if quiet_rounds >= 4 && !collected.is_empty() {
                break;
            }
        } else {
            quiet_rounds = 0;
            for f in more {
                if !collected.contains(&f) {
                    collected.push(f);
                }
            }
        }
    }
    collected.sort_by_key(|f| natural_key(f));
    Some(collected)
}

/// 파일 이름 기준 자연 정렬 키 (2가 10보다 앞)
pub fn natural_key(path: &str) -> Vec<(u8, u64, String)> {
    let name = std::path::Path::new(path).file_name().map(|n| n.to_string_lossy().to_lowercase()).unwrap_or_default();
    let mut key = Vec::new();
    let mut chars = name.chars().peekable();
    while let Some(&c) = chars.peek() {
        if c.is_ascii_digit() {
            let mut n: u64 = 0;
            while let Some(&d) = chars.peek() {
                let Some(v) = d.to_digit(10) else { break };
                n = n.saturating_mul(10).saturating_add(v as u64);
                chars.next();
            }
            key.push((0, n, String::new()));
        } else {
            let mut text = String::new();
            while let Some(&d) = chars.peek() {
                if d.is_ascii_digit() {
                    break;
                }
                text.push(d);
                chars.next();
            }
            key.push((1, 0, text));
        }
    }
    key
}

// ------------------------------------------------------------------ 같은 문서를 연 창 찾기

fn document_mapping_name(path: &str) -> Vec<u16> {
    let full = std::fs::canonicalize(path).map(|p| p.to_string_lossy().into_owned()).unwrap_or_else(|_| path.to_string());
    let mut hasher = DefaultHasher::new();
    full.to_lowercase().hash(&mut hasher);
    wide(&format!("Local\\BossPDFRust_doc_{:016x}", hasher.finish()))
}

/// 열어 둔 문서를 "이 창이 열고 있다"고 알리는 표식. 버리면(drop) 표식이 사라진다.
pub struct DocumentClaim {
    handle: *mut c_void,
}

impl Drop for DocumentClaim {
    fn drop(&mut self) {
        unsafe { CloseHandle(self.handle) };
    }
}

/// 문서를 이 창(hwnd)이 열었다고 표시한다. 다른 창이 이미 표시해 뒀으면 None
pub fn claim_document(path: &str, hwnd: isize) -> Option<DocumentClaim> {
    if hwnd == 0 {
        return None;
    }
    let name = document_mapping_name(path);
    unsafe {
        let handle = CreateFileMappingW(INVALID_HANDLE_VALUE, std::ptr::null(), PAGE_READWRITE, 0, 8, name.as_ptr());
        if handle.is_null() {
            return None;
        }
        if GetLastError() == ERROR_ALREADY_EXISTS {
            CloseHandle(handle);
            return None;
        }
        let view = MapViewOfFile(handle, FILE_MAP_WRITE, 0, 0, 8);
        if view.Value.is_null() {
            CloseHandle(handle);
            return None;
        }
        (view.Value as *mut i64).write_unaligned(hwnd as i64);
        UnmapViewOfFile(view);
        Some(DocumentClaim { handle })
    }
}

/// 이 문서를 이미 열어 둔 창이 있으면 앞으로 가져오고 true
pub fn activate_existing(path: &str) -> bool {
    let name = document_mapping_name(path);
    unsafe {
        let handle = OpenFileMappingW(FILE_MAP_READ, 0, name.as_ptr());
        if handle.is_null() {
            return false;
        }
        let view = MapViewOfFile(handle, FILE_MAP_READ, 0, 0, 8);
        let hwnd = if view.Value.is_null() {
            0
        } else {
            let value = (view.Value as *const i64).read_unaligned();
            UnmapViewOfFile(view);
            value
        };
        CloseHandle(handle);
        let window = hwnd as isize as *mut c_void;
        if hwnd == 0 || IsWindow(window) == 0 {
            return false;
        }
        bring_to_front(hwnd as isize);
        true
    }
}

pub fn bring_to_front(hwnd: isize) {
    if hwnd == 0 {
        return;
    }
    let window = hwnd as *mut c_void;
    unsafe {
        if IsIconic(window) != 0 {
            ShowWindow(window, SW_RESTORE);
        }
        SetForegroundWindow(window);
    }
}
