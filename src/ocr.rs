//! 스캔·이미지 PDF 검색용 글자 인식(OCR). 윈도우에 내장된 OCR(Windows.Media.Ocr)을 쓴다.
//! 파이썬 버전과 같은 규칙: 쪽을 180dpi로 그려 인식하고, 낱말 상자를 글자 수로 고르게 나눠
//! 글자별 위치를 만든 뒤, 한글 자모가 비슷하게 잘못 읽힌 경우까지 너그럽게 맞춰 본다.

use mupdf::pdf::PdfDocument;
use mupdf::text_page::TextPageFlags;
use mupdf::{Colorspace, Matrix};
use windows::core::HSTRING;
use windows::Globalization::Language;
use windows::Graphics::Imaging::{BitmapPixelFormat, SoftwareBitmap};
use windows::Media::Ocr::OcrEngine;
use windows::Storage::Streams::DataWriter;

const OCR_DPI: f32 = 180.0;
/// 글자가 이보다 적은 쪽은 스캔본으로 본다
const MIN_TEXT_CHARS: usize = 30;

/// 인식된 한 줄: 공백을 뺀 글자들과 각 글자의 위치(쪽 왼쪽 위 기준 pt, [x0, y0, x1, y1])
pub struct OcrLine {
    pub chars: Vec<(char, [f32; 4])>,
}

pub struct Recognizer {
    engine: OcrEngine,
}

impl Recognizer {
    /// 한국어 → 영어 → 사용자 언어 순으로 인식기를 만든다. 쓸 수 있는 언어가 없으면 None
    pub fn new() -> Option<Self> {
        for tag in ["ko", "ko-KR", "en"] {
            let Ok(language) = Language::CreateLanguage(&HSTRING::from(tag)) else { continue };
            if !OcrEngine::IsLanguageSupported(&language).unwrap_or(false) {
                continue;
            }
            if let Ok(engine) = OcrEngine::TryCreateFromLanguage(&language) {
                return Some(Self { engine });
            }
        }
        OcrEngine::TryCreateFromUserProfileLanguages().ok().map(|engine| Self { engine })
    }

    /// 쪽을 그려서 글자를 인식한다
    pub fn recognize_page(&self, doc: &PdfDocument, index: usize) -> Vec<OcrLine> {
        self.try_recognize(doc, index).unwrap_or_default()
    }

    fn try_recognize(&self, doc: &PdfDocument, index: usize) -> Option<Vec<OcrLine>> {
        let page = doc.load_page(index as i32).ok()?;
        let bounds = page.bounds().ok()?;
        // 인식기가 받는 최대 크기를 넘지 않게 배율을 낮춘다
        let max_dim = OcrEngine::MaxImageDimension().unwrap_or(10000).max(1000) as f32;
        let longest = (bounds.x1 - bounds.x0).max(bounds.y1 - bounds.y0).max(1.0);
        let zoom = (OCR_DPI / 72.0).min(max_dim / longest);
        let pixmap = page.to_pixmap(&Matrix::new_scale(zoom, zoom), &Colorspace::device_rgb(), false, true).ok()?;
        let (w, h) = (pixmap.width() as usize, pixmap.height() as usize);
        let stride = pixmap.stride() as usize;
        let samples = pixmap.samples();
        if pixmap.n() != 3 || w == 0 || h == 0 || samples.len() < stride * (h - 1) + w * 3 {
            return None;
        }
        // 흰 바탕의 RGB를 RGBA로 넓힌다
        let mut rgba = Vec::with_capacity(w * h * 4);
        for row in 0..h {
            for px in samples[row * stride..row * stride + w * 3].chunks_exact(3) {
                rgba.extend_from_slice(&[px[0], px[1], px[2], 255]);
            }
        }
        let writer = DataWriter::new().ok()?;
        writer.WriteBytes(&rgba).ok()?;
        let buffer = writer.DetachBuffer().ok()?;
        let bitmap = SoftwareBitmap::CreateCopyFromBuffer(&buffer, BitmapPixelFormat::Rgba8, w as i32, h as i32).ok()?;
        let result = self.engine.RecognizeAsync(&bitmap).ok()?.join().ok()?;

        let to_pt = 1.0 / zoom;
        let mut lines = Vec::new();
        for line in result.Lines().ok()? {
            let mut chars: Vec<(char, [f32; 4])> = Vec::new();
            let Ok(words) = line.Words() else { continue };
            for word in words {
                let text: Vec<char> = word.Text().map(|t| t.to_string()).unwrap_or_default().trim().chars().collect();
                let Ok(rect) = word.BoundingRect() else { continue };
                if text.is_empty() {
                    continue;
                }
                let x0 = rect.X * to_pt;
                let y0 = rect.Y * to_pt;
                let width = (rect.Width * to_pt).max(2.0);
                let height = (rect.Height * to_pt).max(2.0);
                let count = text.len() as f32;
                for (i, ch) in text.iter().enumerate() {
                    if ch.is_whitespace() {
                        continue;
                    }
                    let cx0 = x0 + width * (i as f32 / count);
                    let cx1 = x0 + width * ((i + 1) as f32 / count);
                    for lower in ch.to_lowercase() {
                        chars.push((lower, [cx0, y0, cx1, y0 + height]));
                    }
                }
            }
            if !chars.is_empty() {
                lines.push(OcrLine { chars });
            }
        }
        Some(lines)
    }
}

/// 이 쪽에 글자 인식이 필요한지: 그림이 들어 있거나, 뽑히는 글자가 거의 없을 때
pub fn page_needs_ocr(doc: &PdfDocument, index: usize) -> bool {
    if let Ok(page) = doc.load_pdf_page(index as i32) {
        if page.images().map(|images| !images.is_empty()).unwrap_or(false) {
            return true;
        }
    }
    let text_len = doc
        .load_page(index as i32)
        .and_then(|p| p.to_text_page(TextPageFlags::empty()))
        .and_then(|t| t.to_text())
        .map(|t| t.trim().chars().count())
        .unwrap_or(0);
    text_len < MIN_TEXT_CHARS
}

/// 검색어를 인식 결과와 비교하기 좋게: 소문자로 바꾸고 공백을 뺀다
pub fn compact_query(query: &str) -> Vec<char> {
    query.chars().filter(|c| !c.is_whitespace()).flat_map(|c| c.to_lowercase()).collect()
}

/// 인식된 줄들에서 검색어를 찾아 [x, y, w, h] 영역 목록으로 돌려준다
pub fn find_in_lines(lines: &[OcrLine], query: &[char]) -> Vec<[f32; 4]> {
    let mut found = Vec::new();
    for line in lines {
        let text: Vec<char> = line.chars.iter().map(|c| c.0).collect();
        for (start, end) in match_spans(&text, query) {
            let mut rect = line.chars[start].1;
            for (_, r) in &line.chars[start + 1..end] {
                rect = [rect[0].min(r[0]), rect[1].min(r[1]), rect[2].max(r[2]), rect[3].max(r[3])];
            }
            found.push([rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]]);
        }
    }
    found
}

/// 두 영역([x, y, w, h])이 작은 쪽 넓이의 35% 이상 겹치는지 (같은 결과를 두 번 세지 않기 위함)
pub fn overlaps(a: &[f32; 4], b: &[f32; 4]) -> bool {
    let w = (a[0] + a[2]).min(b[0] + b[2]) - a[0].max(b[0]);
    let h = (a[1] + a[3]).min(b[1] + b[3]) - a[1].max(b[1]);
    if w <= 0.0 || h <= 0.0 {
        return false;
    }
    let smaller = (a[2] * a[3]).min(b[2] * b[3]).max(1.0);
    w * h / smaller >= 0.35
}

// ---------------------------------------------------------------- 너그러운 한글 비교

const CHO: [char; 19] = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'];
const JUNG: [char; 21] = [
    'ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅘ', 'ㅙ', 'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅠ', 'ㅡ', 'ㅢ', 'ㅣ',
];
/// 인식기가 서로 헷갈리기 쉬운 첫소리 묶음
const CHO_GROUPS: [&[char]; 6] =
    [&['ㄱ', 'ㅋ', 'ㄲ'], &['ㄴ', 'ㄷ', 'ㅌ', 'ㄸ'], &['ㅂ', 'ㅍ', 'ㅃ'], &['ㅅ', 'ㅆ'], &['ㅈ', 'ㅊ', 'ㅉ'], &['ㅇ', 'ㅎ']];
/// 서로 헷갈리기 쉬운 가운뎃소리 묶음
const JUNG_GROUPS: [&[char]; 4] =
    [&['ㅏ', 'ㅑ'], &['ㅓ', 'ㅕ'], &['ㅗ', 'ㅛ', 'ㅜ', 'ㅠ', 'ㅡ', 'ㅚ'], &['ㅐ', 'ㅒ', 'ㅔ', 'ㅖ']];

/// 한글 한 글자를 (첫소리, 가운뎃소리, 받침 번호)로 나눈다
fn decompose(ch: char) -> Option<(char, char, u32)> {
    let code = (ch as u32).checked_sub(0xAC00)?;
    if code > 11171 {
        return None;
    }
    Some((CHO[(code / 588) as usize], JUNG[((code % 588) / 28) as usize], code % 28))
}

fn same_group(a: char, b: char, groups: &[&[char]]) -> bool {
    a == b || groups.iter().any(|g| g.contains(&a) && g.contains(&b))
}

/// 받침이 같고, 첫소리나 가운뎃소리 중 하나만 비슷하게 다른 글자면 같은 글자로 본다
fn similar(a: char, b: char) -> bool {
    if a == b {
        return true;
    }
    let (Some(x), Some(y)) = (decompose(a), decompose(b)) else { return false };
    if x.2 != y.2 {
        return false;
    }
    (x.0 == y.0 && same_group(x.1, y.1, &JUNG_GROUPS)) || (x.1 == y.1 && same_group(x.0, y.0, &CHO_GROUPS))
}

/// text 안에서 query가 나오는 구간들. 두 글자 이상이면 한 글자까지는 비슷한 글자를 허용한다.
fn match_spans(text: &[char], query: &[char]) -> Vec<(usize, usize)> {
    let (n, m) = (text.len(), query.len());
    let mut spans = Vec::new();
    if m == 0 || m > n {
        return spans;
    }
    let mut i = 0;
    while i + m <= n {
        let matched = if m == 1 {
            text[i] == query[0]
        } else {
            let mut exact = 0;
            let mut ok = true;
            for k in 0..m {
                if text[i + k] == query[k] {
                    exact += 1;
                } else if !similar(text[i + k], query[k]) {
                    ok = false;
                    break;
                }
            }
            ok && exact >= (m - 1).max(1)
        };
        if matched {
            spans.push((i, i + m));
            i += m;
        } else {
            i += 1;
        }
    }
    spans
}
