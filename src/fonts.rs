//! 문서에 포함되지 않은 글꼴을 윈도우 글꼴 폴더에서 바로 찾아 주는 로더.
//!
//! mupdf crate의 기본 system-fonts 기능(font-kit)은 글꼴 하나를 찾을 때마다 시스템 글꼴 전체를
//! 훑어서 첫 페이지 렌더링이 1초 넘게 늦어졌다. 여기서는 자주 쓰는 이름만 파일로 바로 연결하고,
//! 모르는 이름은 MuPDF 내장 글꼴(기본 14종)에 맡긴다.

use std::path::PathBuf;

use mupdf::font_loader::{FontHints, FontLoader};
use mupdf::{CjkFontOrdering, Font};

// MuPDF(UCDN)의 스크립트 번호
const SCRIPT_HANGUL: u32 = 24;
const SCRIPT_HIRAGANA: u32 = 32;
const SCRIPT_KATAKANA: u32 = 33;
const SCRIPT_BOPOMOFO: u32 = 34;
const SCRIPT_HAN: u32 = 35;
// MuPDF fz_text_language 값
const LANG_JA: u32 = 37;
const LANG_ZH_HANS: u32 = 14093;
const LANG_ZH_HANT: u32 = 14822;

pub struct WindowsFontLoader;

pub fn install() {
    mupdf::font_loader::set_font_loader(WindowsFontLoader);
}

fn fonts_dir() -> PathBuf {
    let windir = std::env::var_os("WINDIR").unwrap_or_else(|| "C:\\Windows".into());
    PathBuf::from(windir).join("Fonts")
}

/// 후보 (파일명, 컬렉션 내 번호) 중 처음으로 열리는 글꼴
fn load_first(candidates: &[(&str, i32)]) -> Option<Font> {
    let dir = fonts_dir();
    for (file, index) in candidates {
        let Ok(data) = std::fs::read(dir.join(file)) else { continue };
        if let Ok(font) = Font::from_bytes_with_index(file, *index, &data) {
            return Some(font);
        }
    }
    None
}

/// 비교용 이름: 부분집합 접두사(ABCDEF+)를 떼고 소문자·공백/기호 제거
fn normalize(name: &str) -> String {
    let name = match name.split_once('+') {
        Some((prefix, rest)) if prefix.len() == 6 && prefix.chars().all(|c| c.is_ascii_uppercase()) => rest,
        _ => name,
    };
    name.chars().filter(|c| !matches!(c, ' ' | '-' | '_' | ',')).flat_map(|c| c.to_lowercase()).collect()
}

fn styled<'a>(hints: FontHints, name: &str, regular: &'a str, bold: &'a str, italic: &'a str, bold_italic: &'a str) -> &'a str {
    let bold_wanted = hints.bold || name.contains("bold");
    let italic_wanted = hints.italic || name.contains("italic") || name.contains("oblique");
    match (bold_wanted, italic_wanted) {
        (true, true) => bold_italic,
        (true, false) => bold,
        (false, true) => italic,
        (false, false) => regular,
    }
}

impl FontLoader for WindowsFontLoader {
    fn load_font(&self, name: &str, hints: FontHints) -> Option<Font> {
        let n = normalize(name);
        let bold = hints.bold || n.contains("bold");

        // 한글 글꼴
        if n.contains("malgun") || n.contains("맑은고딕") {
            return load_first(&[(if bold { "malgunbd.ttf" } else { "malgun.ttf" }, 0)]);
        }
        if n.contains("gulimche") || n.contains("굴림체") {
            return load_first(&[("gulim.ttc", 1), ("malgun.ttf", 0)]);
        }
        if n.contains("gulim") || n.contains("굴림") {
            return load_first(&[("gulim.ttc", 0), ("malgun.ttf", 0)]);
        }
        if n.contains("dotumche") || n.contains("돋움체") {
            return load_first(&[("gulim.ttc", 3), ("malgun.ttf", 0)]);
        }
        if n.contains("dotum") || n.contains("돋움") {
            return load_first(&[("gulim.ttc", 2), ("malgun.ttf", 0)]);
        }
        if n.contains("gungsuh") || n.contains("궁서") {
            return load_first(&[("batang.ttc", 2), ("malgun.ttf", 0)]);
        }
        if n.contains("batang") || n.contains("바탕") || n.contains("myeongjo") || n.contains("명조") {
            return load_first(&[("batang.ttc", 0), ("malgun.ttf", 0)]);
        }
        if n.contains("nanumgothic") || n.contains("나눔고딕") {
            return load_first(&[(if bold { "NanumGothicBold.ttf" } else { "NanumGothic.ttf" }, 0), ("malgun.ttf", 0)]);
        }
        if n.contains("gothic") && (n.starts_with("hy") || n.contains("고딕")) {
            return load_first(&[(if bold { "malgunbd.ttf" } else { "malgun.ttf" }, 0)]);
        }

        // 자주 쓰는 라틴 글꼴 (문서에 포함되지 않았을 때 원래 글꼴 그대로 보여 주기 위함)
        let file = if n.starts_with("arial") {
            styled(hints, &n, "arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf")
        } else if n.starts_with("timesnewroman") {
            styled(hints, &n, "times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf")
        } else if n.starts_with("couriernew") {
            styled(hints, &n, "cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf")
        } else if n.starts_with("calibri") {
            styled(hints, &n, "calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf")
        } else if n.starts_with("cambria") {
            styled(hints, &n, "cambria.ttc", "cambriab.ttf", "cambriai.ttf", "cambriaz.ttf")
        } else if n.starts_with("verdana") {
            styled(hints, &n, "verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf")
        } else if n.starts_with("tahoma") {
            styled(hints, &n, "tahoma.ttf", "tahomabd.ttf", "tahoma.ttf", "tahomabd.ttf")
        } else if n.starts_with("georgia") {
            styled(hints, &n, "georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf")
        } else if n.starts_with("segoeui") {
            styled(hints, &n, "segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf")
        } else {
            // Helvetica, Times, Courier 등 기본 14종과 모르는 이름은 MuPDF 내장 글꼴에 맡긴다
            return None;
        };
        load_first(&[(file, 0)])
    }

    fn load_cjk_font(&self, _name: &str, ordering: CjkFontOrdering, serif: bool) -> Option<Font> {
        match ordering {
            CjkFontOrdering::AdobeKorea => {
                if serif {
                    load_first(&[("batang.ttc", 0), ("malgun.ttf", 0)])
                } else {
                    load_first(&[("malgun.ttf", 0), ("gulim.ttc", 0)])
                }
            }
            CjkFontOrdering::AdobeJapan => {
                if serif {
                    load_first(&[("msmincho.ttc", 0), ("YuGothR.ttc", 0), ("msgothic.ttc", 0)])
                } else {
                    load_first(&[("YuGothR.ttc", 0), ("msgothic.ttc", 0), ("meiryo.ttc", 0)])
                }
            }
            CjkFontOrdering::AdobeGb => {
                if serif {
                    load_first(&[("simsun.ttc", 0), ("msyh.ttc", 0)])
                } else {
                    load_first(&[("msyh.ttc", 0), ("simsun.ttc", 0)])
                }
            }
            CjkFontOrdering::AdobeCns => {
                if serif {
                    load_first(&[("mingliub.ttc", 0), ("msjh.ttc", 0)])
                } else {
                    load_first(&[("msjh.ttc", 0), ("mingliub.ttc", 0)])
                }
            }
        }
    }

    fn load_fallback_font(&self, script: u32, language: u32, hints: FontHints) -> Option<Font> {
        match script {
            SCRIPT_HANGUL => load_first(&[(if hints.bold { "malgunbd.ttf" } else { "malgun.ttf" }, 0), ("gulim.ttc", 0)]),
            SCRIPT_HIRAGANA | SCRIPT_KATAKANA => load_first(&[("YuGothR.ttc", 0), ("msgothic.ttc", 0), ("malgun.ttf", 0)]),
            SCRIPT_BOPOMOFO => load_first(&[("msjh.ttc", 0), ("mingliub.ttc", 0)]),
            SCRIPT_HAN => match language {
                LANG_JA => load_first(&[("YuGothR.ttc", 0), ("msgothic.ttc", 0), ("malgun.ttf", 0)]),
                LANG_ZH_HANS => load_first(&[("msyh.ttc", 0), ("simsun.ttc", 0), ("malgun.ttf", 0)]),
                LANG_ZH_HANT => load_first(&[("msjh.ttc", 0), ("mingliub.ttc", 0), ("malgun.ttf", 0)]),
                // 언어를 모르면 한국어 사용자를 기준으로 한자도 맑은 고딕에서 찾는다
                _ => load_first(&[("malgun.ttf", 0), ("msyh.ttc", 0), ("YuGothR.ttc", 0)]),
            },
            _ => None,
        }
    }
}

// ---------------------------------------------------------------------------
// 텍스트 편집용 글꼴 목록: 윈도우 레지스트리의 설치 글꼴 표를 읽어 (이름 → 파일) 표를 만든다.
// ---------------------------------------------------------------------------

#[derive(Clone, Debug)]
pub struct FontFace {
    /// 화면에 보여 줄 글꼴 이름 (한글 이름이 있으면 한글)
    pub family: String,
    /// 레지스트리에 적힌 영문 이름
    pub english: String,
    pub bold: bool,
    pub italic: bool,
    pub path: PathBuf,
    /// 글꼴 모음(.ttc) 안에서의 번호
    pub index: u32,
}

pub struct FontCatalog {
    faces: Vec<FontFace>,
    pub families: Vec<String>,
}

const KOREAN_NAMES: &[(&str, &str)] = &[
    ("Malgun Gothic", "맑은 고딕"),
    ("Gulim", "굴림"),
    ("GulimChe", "굴림체"),
    ("Dotum", "돋움"),
    ("DotumChe", "돋움체"),
    ("Batang", "바탕"),
    ("BatangChe", "바탕체"),
    ("Gungsuh", "궁서"),
    ("GungsuhChe", "궁서체"),
];

const RECOMMENDED: &[&str] = &[
    "맑은 고딕", "굴림", "바탕", "돋움", "궁서", "Arial", "Calibri", "Segoe UI", "Times New Roman", "Courier New", "Consolas",
];

pub const DEFAULT_FAMILY: &str = "맑은 고딕";

impl FontCatalog {
    pub fn load() -> Self {
        use winreg::enums::{HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE};
        use winreg::RegKey;

        let mut faces: Vec<FontFace> = Vec::new();
        let system_dir = fonts_dir();
        for root in [HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER] {
            let Ok(key) = RegKey::predef(root).open_subkey(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") else {
                continue;
            };
            for (name, _) in key.enum_values().flatten() {
                let Ok(file) = key.get_value::<String, _>(&name) else { continue };
                let lower = file.to_lowercase();
                if !(lower.ends_with(".ttf") || lower.ends_with(".otf") || lower.ends_with(".ttc")) {
                    continue;
                }
                let path = if std::path::Path::new(&file).is_absolute() { PathBuf::from(&file) } else { system_dir.join(&file) };
                // "Gulim & GulimChe & Dotum & DotumChe (TrueType)" → 글꼴 모음의 0,1,2,3번
                let name = name.rsplit_once(" (").map(|(n, _)| n).unwrap_or(&name).to_string();
                for (index, part) in name.split(" & ").enumerate() {
                    let (english, bold, italic) = split_style(part.trim());
                    if english.is_empty() {
                        continue;
                    }
                    let family = KOREAN_NAMES
                        .iter()
                        .find(|(en, _)| en.eq_ignore_ascii_case(&english))
                        .map(|(_, ko)| ko.to_string())
                        .unwrap_or_else(|| english.clone());
                    faces.push(FontFace { family, english, bold, italic, path: path.clone(), index: index as u32 });
                }
            }
        }

        let mut families: Vec<String> = Vec::new();
        for rec in RECOMMENDED {
            if faces.iter().any(|f| f.family == *rec) {
                families.push(rec.to_string());
            }
        }
        let mut rest: Vec<String> = faces.iter().map(|f| f.family.clone()).filter(|f| !families.contains(f)).collect();
        rest.sort_by_key(|f| (!f.chars().any(|c| ('가'..='힣').contains(&c)), f.to_lowercase()));
        rest.dedup();
        families.extend(rest);
        Self { faces, families }
    }

    /// 글꼴 이름과 굵기에 맞는 파일. 굵은 글꼴이 따로 없으면 보통 굵기를 돌려준다.
    pub fn resolve(&self, family: &str, bold: bool) -> Option<&FontFace> {
        let of_family = || self.faces.iter().filter(|f| f.family == family || f.english.eq_ignore_ascii_case(family));
        of_family()
            .find(|f| f.bold == bold && !f.italic)
            .or_else(|| of_family().find(|f| !f.bold && !f.italic))
            .or_else(|| of_family().next())
    }

    /// PDF 안의 글꼴 이름(예: "ABCDEF+MalgunGothic-Bold")과 가장 비슷한 설치 글꼴 이름
    pub fn match_pdf_font(&self, pdf_name: &str) -> Option<String> {
        let wanted = normalize(pdf_name).replace("regular", "").replace("bold", "").replace("italic", "");
        let wanted = wanted.trim_end_matches("mt").trim_end_matches("ps");
        if wanted.is_empty() {
            return None;
        }
        self.faces
            .iter()
            .find(|f| normalize(&f.english) == wanted || normalize(&f.family) == wanted)
            .map(|f| f.family.clone())
    }
}

/// "Arial Bold Italic" → ("Arial", true, true)
fn split_style(name: &str) -> (String, bool, bool) {
    let mut words: Vec<&str> = name.split_whitespace().collect();
    let (mut bold, mut italic) = (false, false);
    while let Some(last) = words.last() {
        match last.to_lowercase().as_str() {
            "bold" => bold = true,
            "italic" | "oblique" => italic = true,
            "regular" => {}
            _ => break,
        }
        words.pop();
    }
    (words.join(" "), bold, italic)
}

/// 글꼴 파일을 읽는다. 글꼴 모음(.ttc)이면 index번 글꼴만 떼어 내 단독 글꼴 파일로 만든다.
/// (PDF에 넣는 API가 글꼴 모음 안의 번호를 받지 않기 때문)
pub fn face_bytes(path: &std::path::Path, index: u32) -> std::io::Result<Vec<u8>> {
    let data = std::fs::read(path)?;
    if data.len() < 12 || &data[0..4] != b"ttcf" {
        return Ok(data);
    }
    extract_ttc_face(&data, index).ok_or_else(|| std::io::Error::new(std::io::ErrorKind::InvalidData, "글꼴 모음을 해석할 수 없습니다"))
}

fn extract_ttc_face(data: &[u8], index: u32) -> Option<Vec<u8>> {
    let u16_at = |o: usize| -> Option<u16> { Some(u16::from_be_bytes(data.get(o..o + 2)?.try_into().ok()?)) };
    let u32_at = |o: usize| -> Option<u32> { Some(u32::from_be_bytes(data.get(o..o + 4)?.try_into().ok()?)) };

    let count = u32_at(8)?;
    if index >= count {
        return None;
    }
    let dir = u32_at(12 + 4 * index as usize)? as usize;
    let num_tables = u16_at(dir + 4)? as usize;

    // 새 파일: 머리(12) + 표 목록(16*n) + 각 표 데이터(4바이트 정렬)
    let header_len = 12 + 16 * num_tables;
    let mut out = Vec::with_capacity(header_len);
    out.extend_from_slice(data.get(dir..dir + 12)?);
    out.resize(header_len, 0);
    for t in 0..num_tables {
        let rec = dir + 12 + 16 * t;
        let offset = u32_at(rec + 8)? as usize;
        let length = u32_at(rec + 12)? as usize;
        let table = data.get(offset..offset + length)?;
        let new_offset = out.len() as u32;
        out.extend_from_slice(table);
        while out.len() % 4 != 0 {
            out.push(0);
        }
        let dst = 12 + 16 * t;
        out[dst..dst + 8].copy_from_slice(data.get(rec..rec + 8)?); // tag + checksum
        out[dst + 8..dst + 12].copy_from_slice(&new_offset.to_be_bytes());
        out[dst + 12..dst + 16].copy_from_slice(&(length as u32).to_be_bytes());
    }
    Some(out)
}
