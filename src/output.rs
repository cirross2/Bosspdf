//! 내보내기(새 PDF·쪽별 이미지·이어 붙인 이미지)와 합치기(PDF·이미지 → PDF).
//! 엔진 스레드에서 실행된다.

use std::io::Cursor;
use std::path::Path;

use image::codecs::jpeg::JpegEncoder;
use image::{ImageFormat, RgbImage};
use mupdf::pdf::{InsertImageOptions, InsertPdfOptions, PageImageSource, PageSelection, PdfDocument, PdfGraftMap, PdfWriteOptions};
use mupdf::{Colorspace, Matrix, Rect, Size};

/// 이어 붙인 이미지의 최대 픽셀 수 (이보다 크면 메모리가 수 GB 필요해진다)
const STITCH_MAX_PIXELS: u64 = 250_000_000;
const JPEG_QUALITY: u8 = 95;
pub const IMAGE_EXTENSIONS: &[&str] = &["png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff", "webp"];

pub enum ExportKind {
    /// 고른 쪽만 담은 새 PDF
    Pdf { path: String },
    /// 쪽마다 이미지 파일 하나: <dir>/<prefix>_<쪽번호>.png|jpg
    Images { dir: String, prefix: String, jpg: bool, dpi: u32 },
    /// 세로로 이어 붙인 긴 이미지 하나 (확장자가 jpg면 JPG, 아니면 PNG)
    Stitched { path: String, dpi: u32, spacing: u32 },
}

pub struct MergeOptions {
    /// 이미지를 A4 쪽에 맞춰 넣을지 (false면 이미지 크기 그대로의 쪽을 만든다)
    pub fit_a4: bool,
    /// A4에 맞출 때의 여백 (pt)
    pub margin: f32,
}

/// "1-3, 5, 8-" 같은 쪽 범위를 0부터 시작하는 번호 목록으로 바꾼다
pub fn parse_page_ranges(text: &str, count: usize) -> Result<Vec<usize>, String> {
    let mut pages = Vec::new();
    for part in text.split([',', ' ', ';']).filter(|p| !p.trim().is_empty()) {
        let part = part.trim();
        let bad = || format!("쪽 범위를 이해할 수 없습니다: \"{part}\"");
        let (start, end) = match part.split_once(['-', '~']) {
            Some((a, b)) => {
                let start = if a.trim().is_empty() { 1 } else { a.trim().parse::<usize>().map_err(|_| bad())? };
                let end = if b.trim().is_empty() { count } else { b.trim().parse::<usize>().map_err(|_| bad())? };
                (start, end)
            }
            None => {
                let n = part.parse::<usize>().map_err(|_| bad())?;
                (n, n)
            }
        };
        if start == 0 || end == 0 || start > count || end > count {
            return Err(format!("쪽 번호는 1부터 {count}까지입니다: \"{part}\""));
        }
        if start <= end {
            pages.extend((start..=end).map(|n| n - 1));
        } else {
            pages.extend((end..=start).rev().map(|n| n - 1));
        }
    }
    if pages.is_empty() {
        return Err("내보낼 쪽을 지정해 주세요.".into());
    }
    Ok(pages)
}

fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}

fn write_options() -> PdfWriteOptions {
    let mut options = PdfWriteOptions::default();
    options.set_garbage_level(3).set_compress(true);
    options
}

/// 임시 파일에 먼저 쓰고 교체해서, 실패해도 같은 이름의 기존 파일이 깨지지 않게 한다
fn save_pdf(doc: &PdfDocument, path: &str) -> Result<(), String> {
    let mut bytes = Vec::new();
    doc.write_to_with_options(&mut bytes, write_options()).map_err(err)?;
    let tmp = format!("{path}.bosspdf_tmp");
    std::fs::write(&tmp, &bytes).map_err(err)?;
    if let Err(e) = std::fs::rename(&tmp, path) {
        let _ = std::fs::remove_file(&tmp);
        return Err(err(e));
    }
    Ok(())
}

/// 쪽에 붙은 주석(형광펜·필기·메모·도형·글상자 등)을 다른 문서의 쪽으로 옮겨 붙인다.
///
/// MuPDF의 쪽 복사(pdf_graft_page)는 쪽 내용만 옮기고 주석은 옮기지 않아서, 다른 프로그램에서 넣은
/// 필기가 합친 결과에서 사라졌다. 옮긴 주석 수를 돌려준다.
/// - 입력 양식 칸(Widget)과 메모 팝업 창(Popup)은 옮기지 않는다 (메모 내용 자체는 주석에 들어 있어 유지됨)
/// - 링크는 웹 주소 링크만 옮긴다 (문서 안 이동 링크는 대상 쪽이 달라지므로 뺌)
fn copy_annotations(
    dst: &mut PdfDocument,
    map: &mut PdfGraftMap,
    src: &PdfDocument,
    src_index: usize,
    dst_index: usize,
) -> Result<usize, mupdf::Error> {
    let name_of = |obj: Option<mupdf::pdf::PdfObject>| -> String {
        obj.and_then(|o| o.as_name().ok())
            .map(|bytes| String::from_utf8_lossy(&bytes).trim_end_matches('\0').to_string())
            .unwrap_or_default()
    };
    let src_page = src.find_page(src_index as i32)?;
    let Some(annots) = src_page.get_dict("Annots")? else { return Ok(0) };
    if !annots.is_array()? {
        return Ok(0);
    }
    let mut copied = Vec::new();
    for i in 0..annots.len()? {
        let Some(annot) = annots.get_array(i as i32)? else { continue };
        if !annot.is_dict()? {
            continue;
        }
        let subtype = name_of(annot.get_dict("Subtype")?);
        if subtype == "Widget" || subtype == "Popup" {
            continue;
        }
        if subtype == "Link" {
            let action = annot.get_dict("A")?;
            let is_web_link = match action {
                Some(a) if a.is_dict()? => name_of(a.get_dict("S")?) == "URI",
                _ => false,
            };
            if !is_web_link {
                continue;
            }
        }
        // 원본 쪽을 가리키는 항목을 뺀 얕은 사본을 만들어 옮긴다.
        // (그대로 옮기면 /P를 따라 원본 쪽과 그 위의 문서 구조까지 통째로 딸려 온다)
        let mut copy = annot.copy_dict()?;
        for key in ["P", "Popup", "IRT", "Parent"] {
            copy.dict_delete(key)?;
        }
        let grafted = map.graft_object(&copy)?;
        copied.push(dst.add_object(&grafted)?);
    }
    if copied.is_empty() {
        return Ok(0);
    }
    let count = copied.len();
    let mut array = dst.new_array()?;
    for reference in copied {
        array.array_push(reference)?;
    }
    let mut dst_page = dst.find_page(dst_index as i32)?;
    dst_page.dict_put("Annots", array)?;
    Ok(count)
}

/// src의 쪽들(pages, 없으면 전체)을 dst 끝에 붙이고 주석도 함께 옮긴다
fn append_pages(dst: &mut PdfDocument, src: &PdfDocument, pages: Option<&[usize]>) -> Result<(), mupdf::Error> {
    let count = src.page_count()?.max(0) as usize;
    let indices: Vec<usize> = match pages {
        Some(list) => list.to_vec(),
        None => (0..count).collect(),
    };
    let start = dst.page_count()?.max(0) as usize;
    dst.insert_pdf(src, InsertPdfOptions { source_pages: PageSelection::Pages(indices.clone()), ..Default::default() })?;
    let mut map = dst.new_graft_map()?;
    for (offset, &src_index) in indices.iter().enumerate() {
        // 주석 하나가 깨져 있어도 쪽 자체는 이미 옮겨졌으므로, 그 쪽의 주석만 포기하고 계속한다
        let _ = copy_annotations(dst, &mut map, src, src_index, start + offset);
    }
    Ok(())
}

fn render_page(doc: &PdfDocument, index: usize, dpi: u32) -> Result<RgbImage, String> {
    let scale = dpi as f32 / 72.0;
    let page = doc.load_page(index as i32).map_err(err)?;
    let pixmap = page.to_pixmap(&Matrix::new_scale(scale, scale), &Colorspace::device_rgb(), false, true).map_err(err)?;
    let (w, h) = (pixmap.width() as usize, pixmap.height() as usize);
    let stride = pixmap.stride() as usize;
    let samples = pixmap.samples();
    if pixmap.n() != 3 || w == 0 || h == 0 || samples.len() < stride * (h - 1) + w * 3 {
        return Err(format!("{}쪽을 그릴 수 없습니다.", index + 1));
    }
    let mut data = Vec::with_capacity(w * h * 3);
    for row in 0..h {
        data.extend_from_slice(&samples[row * stride..row * stride + w * 3]);
    }
    RgbImage::from_raw(w as u32, h as u32, data).ok_or_else(|| "이미지를 만들 수 없습니다.".to_string())
}

fn save_image(image: &RgbImage, path: &str, jpg: bool) -> Result<(), String> {
    let tmp = format!("{path}.bosspdf_tmp");
    let written = (|| -> Result<(), String> {
        let file = std::fs::File::create(&tmp).map_err(err)?;
        let mut writer = std::io::BufWriter::new(file);
        if jpg {
            JpegEncoder::new_with_quality(&mut writer, JPEG_QUALITY).encode_image(image).map_err(err)?;
        } else {
            image.write_to(&mut writer, ImageFormat::Png).map_err(err)?;
        }
        Ok(())
    })();
    if let Err(e) = written {
        let _ = std::fs::remove_file(&tmp);
        return Err(e);
    }
    std::fs::rename(&tmp, path).map_err(|e| {
        let _ = std::fs::remove_file(&tmp);
        err(e)
    })
}

/// 내보내기. 성공하면 사용자에게 보여 줄 한 줄 요약을 돌려준다.
pub fn export(doc: &PdfDocument, pages: &[usize], kind: &ExportKind) -> Result<String, String> {
    if pages.is_empty() {
        return Err("내보낼 쪽이 없습니다.".into());
    }
    match kind {
        ExportKind::Pdf { path } => {
            let mut out = PdfDocument::new();
            append_pages(&mut out, doc, Some(pages)).map_err(err)?;
            save_pdf(&out, path)?;
            Ok(format!("{}쪽을 새 PDF로 내보냈습니다", pages.len()))
        }
        ExportKind::Images { dir, prefix, jpg, dpi } => {
            std::fs::create_dir_all(dir).map_err(err)?;
            let ext = if *jpg { "jpg" } else { "png" };
            for &index in pages {
                let image = render_page(doc, index, *dpi)?;
                let path = Path::new(dir).join(format!("{prefix}_{}.{ext}", index + 1));
                save_image(&image, &path.to_string_lossy(), *jpg)?;
            }
            Ok(format!("이미지 {}개를 내보냈습니다", pages.len()))
        }
        ExportKind::Stitched { path, dpi, spacing } => {
            // 먼저 크기만 계산해서 너무 크면 그리기 전에 멈춘다
            let scale = *dpi as f64 / 72.0;
            let (mut total_w, mut total_h) = (0u64, 0u64);
            for &index in pages {
                let bounds = doc.load_page(index as i32).and_then(|p| p.bounds()).map_err(err)?;
                total_w = total_w.max(((bounds.x1 - bounds.x0) as f64 * scale).ceil() as u64);
                total_h += ((bounds.y1 - bounds.y0) as f64 * scale).ceil() as u64;
            }
            total_h += *spacing as u64 * (pages.len() as u64 - 1);
            if total_w * total_h > STITCH_MAX_PIXELS {
                return Err(format!(
                    "이어 붙인 이미지가 너무 큽니다 ({total_w}x{total_h}). 해상도를 낮추거나 쪽 수를 줄여 주세요."
                ));
            }

            let images: Vec<RgbImage> = pages.iter().map(|&i| render_page(doc, i, *dpi)).collect::<Result<_, _>>()?;
            let width = images.iter().map(|i| i.width()).max().unwrap_or(1);
            let height: u32 = images.iter().map(|i| i.height()).sum::<u32>() + spacing * (images.len() as u32 - 1);
            let mut canvas = RgbImage::from_pixel(width, height, image::Rgb([255, 255, 255]));
            let mut y = 0i64;
            for img in &images {
                let x = ((width - img.width()) / 2) as i64;
                image::imageops::replace(&mut canvas, img, x, y);
                y += img.height() as i64 + *spacing as i64;
            }
            let lower = path.to_lowercase();
            save_image(&canvas, path, lower.ends_with(".jpg") || lower.ends_with(".jpeg"))?;
            Ok(format!("{}쪽을 이어 붙인 이미지로 내보냈습니다 ({width}x{height})", pages.len()))
        }
    }
}

pub fn is_image_file(path: &str) -> bool {
    Path::new(path)
        .extension()
        .map(|e| IMAGE_EXTENSIONS.contains(&e.to_string_lossy().to_lowercase().as_str()))
        .unwrap_or(false)
}

/// PDF와 이미지를 순서대로 하나의 PDF로 합친다. 만들어진 PDF의 쪽 수를 돌려준다.
pub fn merge(files: &[String], out_path: &str, options: &MergeOptions) -> Result<usize, String> {
    if files.is_empty() {
        return Err("합칠 파일이 없습니다.".into());
    }
    let mut out = PdfDocument::new();
    for file in files {
        let name = Path::new(file).file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| file.clone());
        if is_image_file(file) {
            add_image_page(&mut out, file, options).map_err(|e| format!("{name}: {e}"))?;
        } else {
            let src = PdfDocument::open(file.as_str()).map_err(|e| format!("{name}: {e}"))?;
            if src.needs_password().unwrap_or(false) {
                return Err(format!("{name}: 암호가 걸린 문서입니다. 먼저 열어서 암호 없이 저장한 뒤 합쳐 주세요."));
            }
            append_pages(&mut out, &src, None).map_err(|e| format!("{name}: {e}"))?;
        }
    }
    let pages = out.page_count().map_err(err)?.max(0) as usize;
    if pages == 0 {
        return Err("합친 결과에 쪽이 없습니다.".into());
    }
    save_pdf(&out, out_path)?;
    Ok(pages)
}

fn add_image_page(out: &mut PdfDocument, file: &str, options: &MergeOptions) -> Result<(), String> {
    let mut bytes = std::fs::read(file).map_err(err)?;
    let reader = image::ImageReader::new(Cursor::new(&bytes)).with_guessed_format().map_err(err)?;
    let format = reader.format();
    let (w, h) = reader.into_dimensions().map_err(|e| format!("이미지를 읽을 수 없습니다 ({e})"))?;
    // MuPDF가 직접 읽지 못하는 형식(WebP)은 PNG로 바꿔서 넣는다
    if format == Some(ImageFormat::WebP) {
        let decoded = image::load_from_memory(&bytes).map_err(err)?;
        let mut png = Vec::new();
        decoded.write_to(&mut Cursor::new(&mut png), ImageFormat::Png).map_err(err)?;
        bytes = png;
    }
    let (w, h) = (w.max(1) as f32, h.max(1) as f32);

    let (page_size, rect) = if options.fit_a4 {
        // 가로로 긴 이미지는 A4 가로, 아니면 A4 세로. 비율을 지켜 가운데에 놓는다.
        let (pw, ph) = if w > h { (Size::A4.height, Size::A4.width) } else { (Size::A4.width, Size::A4.height) };
        let avail_w = (pw - options.margin * 2.0).max(10.0);
        let avail_h = (ph - options.margin * 2.0).max(10.0);
        let scale = (avail_w / w).min(avail_h / h);
        let (dw, dh) = (w * scale, h * scale);
        let (x, y) = ((pw - dw) / 2.0, (ph - dh) / 2.0);
        (Size::new(pw, ph), Rect::new(x, y, x + dw, y + dh))
    } else {
        (Size::new(w, h), Rect::new(0.0, 0.0, w, h))
    };
    let mut page = out.new_page(page_size).map_err(err)?;
    page.insert_image(out, rect, PageImageSource::Bytes { data: &bytes, format_hint: None }, InsertImageOptions::default())
        .map_err(err)?;
    Ok(())
}
