//! 인쇄 (윈도우 GDI).
//! 인쇄 대화상자는 UI 스레드에서 띄우고, 실제로 쪽을 그려 보내는 일은 엔진 스레드가 한다.
//!
//! 각 쪽은 용지의 인쇄 가능 영역 안에 비율을 지켜 가운데에 놓는다.
//! 쪽과 용지의 방향이 다르면(가로 쪽 + 세로 용지) 쪽을 90° 돌려 더 크게 찍는다.

use std::ffi::c_void;

use mupdf::pdf::PdfDocument;
use mupdf::{Colorspace, Matrix};
use windows_sys::Win32::Foundation::GlobalFree;
use windows_sys::Win32::Graphics::Gdi::{
    CreateDCW, DeleteDC, GetDeviceCaps, SetStretchBltMode, StretchDIBits, BITMAPINFO, BITMAPINFOHEADER, BI_RGB,
    DIB_RGB_COLORS, HALFTONE, HORZRES, LOGPIXELSX, LOGPIXELSY, SRCCOPY, VERTRES,
};
use windows_sys::Win32::Storage::Xps::{AbortDoc, EndDoc, EndPage, StartDocW, StartPage, DOCINFOW};
use windows_sys::Win32::UI::Controls::Dialogs::{
    PrintDlgW, PD_NOSELECTION, PD_PAGENUMS, PD_RETURNDC, PD_USEDEVMODECOPIESANDCOLLATE, PRINTDLGW,
};

/// 쪽을 그릴 때의 최대 해상도. 프린터가 600dpi여도 300dpi로 그려서 늘려 보낸다
/// (A4 600dpi는 한 쪽에 100MB가 넘어 느리고, 문서 인쇄 품질 차이는 거의 없다).
const MAX_RENDER_DPI: f32 = 300.0;

pub struct PrintJob {
    /// 프린터 장치 컨텍스트(HDC). 인쇄가 끝나면 run이 닫는다.
    pub hdc: isize,
    /// 0부터 시작하는 쪽 번호
    pub pages: Vec<usize>,
    pub copies: u32,
    pub doc_name: String,
    /// 파일로 인쇄할 때의 경로 (예: "Microsoft Print to PDF"로 대화상자 없이 저장)
    pub output: Option<String>,
}

fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain(std::iter::once(0)).collect()
}

/// 윈도우 인쇄 대화상자를 띄운다. 사용자가 [인쇄]를 누르면 (HDC, 쪽 목록, 부수)를 돌려준다.
pub fn ask_user(owner_hwnd: isize, page_count: usize) -> Option<(isize, Vec<usize>, u32)> {
    if page_count == 0 {
        return None;
    }
    let max_page = page_count.min(u16::MAX as usize) as u16;
    let mut dialog: PRINTDLGW = unsafe { std::mem::zeroed() };
    dialog.lStructSize = std::mem::size_of::<PRINTDLGW>() as u32;
    dialog.hwndOwner = owner_hwnd as _;
    dialog.Flags = PD_RETURNDC | PD_NOSELECTION | PD_USEDEVMODECOPIESANDCOLLATE;
    dialog.nMinPage = 1;
    dialog.nMaxPage = max_page;
    dialog.nFromPage = 1;
    dialog.nToPage = max_page;
    dialog.nCopies = 1;

    let accepted = unsafe { PrintDlgW(&mut dialog) } != 0;
    unsafe {
        if !dialog.hDevMode.is_null() {
            GlobalFree(dialog.hDevMode);
        }
        if !dialog.hDevNames.is_null() {
            GlobalFree(dialog.hDevNames);
        }
    }
    if !accepted || dialog.hDC.is_null() {
        return None;
    }
    let pages: Vec<usize> = if dialog.Flags & PD_PAGENUMS != 0 {
        let from = (dialog.nFromPage.max(1) as usize).min(page_count);
        let to = (dialog.nToPage.max(1) as usize).min(page_count);
        (from.min(to)..=from.max(to)).map(|n| n - 1).collect()
    } else {
        (0..page_count).collect()
    };
    // 드라이버가 부수를 처리하면 nCopies는 1로 돌아온다. 못 하면 우리가 그만큼 반복해서 보낸다.
    Some((dialog.hDC as isize, pages, dialog.nCopies.max(1) as u32))
}

/// 이름으로 프린터를 연다 (대화상자 없이 인쇄할 때)
pub fn open_printer(name: &str) -> Option<isize> {
    let driver = wide("WINSPOOL");
    let device = wide(name);
    let hdc = unsafe { CreateDCW(driver.as_ptr(), device.as_ptr(), std::ptr::null(), std::ptr::null()) };
    (!hdc.is_null()).then_some(hdc as isize)
}

/// 인쇄 작업을 실행한다. 보낸 쪽 수(부수 포함)를 돌려준다. 끝나면 HDC를 닫는다.
pub fn run(doc: &PdfDocument, job: &PrintJob, progress: &dyn Fn(usize, usize)) -> Result<usize, String> {
    let hdc = job.hdc as *mut c_void;
    let result = print_pages(doc, job, hdc, progress);
    unsafe {
        if result.is_err() {
            AbortDoc(hdc);
        }
        DeleteDC(hdc);
    }
    result
}

fn print_pages(doc: &PdfDocument, job: &PrintJob, hdc: *mut c_void, progress: &dyn Fn(usize, usize)) -> Result<usize, String> {
    let (paper_w, paper_h, dpi_x, dpi_y) = unsafe {
        (
            GetDeviceCaps(hdc, HORZRES as i32),
            GetDeviceCaps(hdc, VERTRES as i32),
            GetDeviceCaps(hdc, LOGPIXELSX as i32).max(1) as f32,
            GetDeviceCaps(hdc, LOGPIXELSY as i32).max(1) as f32,
        )
    };
    if paper_w <= 0 || paper_h <= 0 {
        return Err("프린터의 용지 크기를 알 수 없습니다.".into());
    }

    let name = wide(&job.doc_name);
    let output = job.output.as_deref().map(wide);
    let mut info: DOCINFOW = unsafe { std::mem::zeroed() };
    info.cbSize = std::mem::size_of::<DOCINFOW>() as i32;
    info.lpszDocName = name.as_ptr();
    info.lpszOutput = output.as_ref().map(|o| o.as_ptr()).unwrap_or(std::ptr::null());
    if unsafe { StartDocW(hdc, &info) } <= 0 {
        return Err("인쇄 작업을 시작할 수 없습니다.".into());
    }
    unsafe { SetStretchBltMode(hdc, HALFTONE) };

    let total = job.pages.len() * job.copies.max(1) as usize;
    let mut sent = 0;
    for _ in 0..job.copies.max(1) {
        for &index in &job.pages {
            progress(sent + 1, total);
            let page = doc.load_page(index as i32).map_err(|e| e.to_string())?;
            let bounds = page.bounds().map_err(|e| e.to_string())?;
            let (page_w, page_h) = ((bounds.x1 - bounds.x0).max(1.0), (bounds.y1 - bounds.y0).max(1.0));

            // 쪽과 용지의 방향이 다르면 90° 돌려서 찍는다
            let rotate = (page_w > page_h) != (paper_w > paper_h);
            let (fit_w, fit_h) = if rotate { (page_h, page_w) } else { (page_w, page_h) };
            // 용지 픽셀 / 쪽 pt. 가로·세로 해상도가 다른 프린터도 있으므로 따로 계산한다
            let scale = (paper_w as f32 / dpi_x * 72.0 / fit_w).min(paper_h as f32 / dpi_y * 72.0 / fit_h);
            let dest_w = (fit_w * scale / 72.0 * dpi_x).round().max(1.0) as i32;
            let dest_h = (fit_h * scale / 72.0 * dpi_y).round().max(1.0) as i32;
            let dest_x = (paper_w - dest_w) / 2;
            let dest_y = (paper_h - dest_h) / 2;

            // 그리는 해상도: 실제 찍히는 크기 기준, 최대 300dpi
            let zoom = (scale * dpi_x.min(dpi_y).min(MAX_RENDER_DPI) / 72.0).max(0.1);
            let mut matrix = Matrix::new_scale(zoom, zoom);
            if rotate {
                // 반시계 방향으로 돌린다: 세로 문서를 시계 방향으로 돌려 둔 쪽이 종이에서는 다시 바로 서게 된다
                matrix.concat(Matrix::new_rotate(-90.0));
            }
            let pixmap = page.to_pixmap(&matrix, &Colorspace::device_bgr(), false, true).map_err(|e| e.to_string())?;
            let (w, h) = (pixmap.width() as usize, pixmap.height() as usize);
            let stride = pixmap.stride() as usize;
            let samples = pixmap.samples();
            if pixmap.n() != 3 || w == 0 || h == 0 || samples.len() < stride * (h - 1) + w * 3 {
                return Err(format!("{}쪽을 그릴 수 없습니다.", index + 1));
            }
            // DIB는 줄마다 4바이트 단위로 맞춰야 한다
            let dib_stride = (w * 3 + 3) & !3;
            let mut bits = vec![0u8; dib_stride * h];
            for row in 0..h {
                bits[row * dib_stride..row * dib_stride + w * 3].copy_from_slice(&samples[row * stride..row * stride + w * 3]);
            }
            let mut bmi: BITMAPINFO = unsafe { std::mem::zeroed() };
            bmi.bmiHeader.biSize = std::mem::size_of::<BITMAPINFOHEADER>() as u32;
            bmi.bmiHeader.biWidth = w as i32;
            bmi.bmiHeader.biHeight = -(h as i32); // 음수 = 위에서 아래로
            bmi.bmiHeader.biPlanes = 1;
            bmi.bmiHeader.biBitCount = 24;
            bmi.bmiHeader.biCompression = BI_RGB;

            unsafe {
                if StartPage(hdc) <= 0 {
                    return Err("새 쪽을 시작할 수 없습니다.".into());
                }
                let copied = StretchDIBits(
                    hdc,
                    dest_x,
                    dest_y,
                    dest_w,
                    dest_h,
                    0,
                    0,
                    w as i32,
                    h as i32,
                    bits.as_ptr() as *const c_void,
                    &bmi,
                    DIB_RGB_COLORS,
                    SRCCOPY,
                );
                if copied == 0 {
                    return Err(format!("{}쪽을 프린터로 보낼 수 없습니다.", index + 1));
                }
                if EndPage(hdc) <= 0 {
                    return Err("쪽을 마칠 수 없습니다. (인쇄가 취소됐을 수 있습니다)".into());
                }
            }
            sent += 1;
        }
    }
    if unsafe { EndDoc(hdc) } <= 0 {
        return Err("인쇄 작업을 마칠 수 없습니다.".into());
    }
    Ok(sent)
}
