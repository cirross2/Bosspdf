//! PDF 엔진 작업 스레드.
//! MuPDF 문서는 이 스레드 하나만 소유하고, 화면(UI) 스레드와는 메시지로만 주고받는다.
//! 우선순위: 편집·저장 > 화면에 보이는 페이지 렌더링 > 검색 > 썸네일.

use std::collections::{HashMap, VecDeque};
use std::sync::mpsc::{Receiver, TryRecvError};
use std::time::{Duration, Instant};

use mupdf::pdf::{Encryption, PdfDocument, PdfWriteOptions};
use mupdf::shape::{FinishOptions, PdfColor, Shape, TextOptions};
use mupdf::text_page::{TextCharFlags, TextPageFlags};
use mupdf::{Colorspace, Document, Matrix, Point, Rect};
use slint::{Rgb8Pixel, SharedPixelBuffer};

pub type PixelBuf = SharedPixelBuffer<Rgb8Pixel>;

/// 한 번에 만드는 비트맵의 최대 픽셀 수 (지나친 확대에서 메모리 폭주 방지)
const MAX_PIXELS: f32 = 48_000_000.0;
/// 실행 취소 단계 수 (파이썬 버전과 동일)
const UNDO_MAX: usize = 10;

/// 페이지 위에 직접 그리는 편집 (좌표는 페이지 왼쪽 위 기준 pt)
pub enum EditOp {
    /// 반투명 형광펜
    Highlight { page: usize, rect: [f32; 4] },
    /// 흰색으로 덮어 가리기
    Whiteout { page: usize, rect: [f32; 4] },
    /// 손글씨/서명
    Ink { page: usize, points: Vec<(f32, f32)> },
    /// 텍스트 추가 또는 교체.
    /// - baseline이 false면 (x, y)는 첫 줄의 왼쪽 위, true면 첫 줄 글자 밑선의 시작점
    /// - cover가 있으면 그 영역을 먼저 흰색으로 덮는다 (기존 텍스트 수정)
    /// - text가 비어 있고 cover만 있으면 지우기만 한다
    Text { page: usize, x: f32, y: f32, baseline: bool, text: String, style: TextStyle, lineheight: f32, cover: Option<[f32; 4]> },
}

/// 페이지 구조를 바꾸는 편집
pub enum PageOp {
    /// delta: 시계 방향 각도 (90 또는 -90)
    Rotate { page: usize, delta: i32 },
    Delete { page: usize },
    /// from 쪽을 to 위치로 옮긴다 (옮긴 뒤의 번호가 to)
    Move { from: usize, to: usize },
}

/// 넣을 텍스트의 서식
#[derive(Clone, Debug)]
pub struct TextStyle {
    pub font_path: String,
    /// 글꼴 모음(.ttc) 안에서의 번호
    pub font_index: u32,
    pub size: f32,
    pub color: [f32; 3],
}

/// 드래그한 영역에서 읽어 낸 기존 텍스트 정보
#[derive(Clone, Debug, Default)]
pub struct TextInfo {
    pub text: String,
    pub lines: usize,
    pub size: f32,
    pub color: [f32; 3],
    pub font_name: String,
    pub bold: bool,
    /// 첫 글자의 밑선 시작점 (페이지 왼쪽 위 기준 pt)
    pub baseline: Option<(f32, f32)>,
    /// 줄 간격 / 글자 크기
    pub lineheight: f32,
}

impl EditOp {
    fn page(&self) -> usize {
        match self {
            EditOp::Highlight { page, .. } | EditOp::Whiteout { page, .. } | EditOp::Ink { page, .. } | EditOp::Text { page, .. } => *page,
        }
    }
}

pub enum Req {
    Open { doc_id: u64, path: String, password: Option<String> },
    /// 지금 필요한 페이지 목록(앞에 있을수록 먼저). 이전 목록을 대체한다.
    Want { doc_id: u64, pages: Vec<usize>, scale: f32 },
    Thumbs { doc_id: u64, pages: Vec<usize>, width_px: f32 },
    Search { doc_id: u64, gen: u64, query: String },
    Edit { doc_id: u64, op: EditOp },
    Pages { doc_id: u64, op: PageOp },
    /// 영역 안의 기존 텍스트와 서식을 알려 달라 (텍스트 수정 도구)
    TextAt { doc_id: u64, page: usize, rect: [f32; 4] },
    Undo { doc_id: u64 },
    /// path가 None이면 열어 둔 파일에 덮어쓴다. remove_password면 암호를 풀어서 저장한다
    Save { doc_id: u64, path: Option<String>, remove_password: bool },
    /// 열어 둔 문서의 일부 쪽을 내보낸다 (pages: 0부터 시작하는 쪽 번호)
    Export { doc_id: u64, pages: Vec<usize>, kind: crate::output::ExportKind },
    Print { doc_id: u64, job: crate::print::PrintJob },
    /// 여러 PDF·이미지를 하나의 PDF로 합친다 (열어 둔 문서와 무관)
    Merge { files: Vec<String>, out: String, options: crate::output::MergeOptions },
}

pub enum Evt {
    Opened { doc_id: u64, path: String, sizes: Vec<(f32, f32)>, encrypted: bool },
    NeedPassword { doc_id: u64, wrong: bool },
    OpenFailed { doc_id: u64, message: String },
    Page { doc_id: u64, index: usize, scale: f32, buf: PixelBuf },
    Thumb { doc_id: u64, index: usize, buf: PixelBuf },
    /// rects: 페이지 왼쪽 위 기준 pt 단위 [x, y, w, h]
    Hits { doc_id: u64, gen: u64, index: usize, rects: Vec<[f32; 4]> },
    SearchDone { doc_id: u64, gen: u64 },
    /// 검색이 오래 걸리는 단계(글자 인식)에 있을 때의 진행 표시
    SearchNote { doc_id: u64, gen: u64, note: String },
    /// 문서 내용이 바뀜. page가 None이면 전체를 다시 그려야 한다.
    Changed { doc_id: u64, page: Option<usize>, can_undo: bool, dirty: bool },
    /// 페이지 수·크기·순서가 바뀌었을 수 있음(페이지 조작, 실행 취소). 화면 배치를 새로 잡아야 한다.
    /// focus가 있으면 그 쪽으로 이동한다.
    Restructured { doc_id: u64, sizes: Vec<(f32, f32)>, focus: Option<usize>, can_undo: bool, dirty: bool },
    EditFailed { doc_id: u64, message: String },
    TextFound { doc_id: u64, page: usize, rect: [f32; 4], info: TextInfo },
    Saved { doc_id: u64, path: String, error: Option<String>, encrypted: bool },
    /// 오래 걸리는 작업의 진행 상황 (알림으로 보여 줄 문장)
    Progress { message: String },
    /// 내보내기·합치기·인쇄 결과. result는 사용자에게 보여 줄 문장, open은 이어서 열 파일
    TaskDone { result: Result<String, String>, open: Option<String> },
}

struct SearchJob {
    gen: u64,
    query: String,
    next_page: usize,
    /// false: 문서의 텍스트에서 찾는 중, true: 그림 쪽을 글자 인식(OCR)해서 찾는 중
    ocr_phase: bool,
    /// 글자 인식 결과와 비교할 검색어 (소문자, 공백 없음)
    compact: Vec<char>,
    /// 텍스트 검색에서 이미 찾은 영역 (같은 곳을 두 번 세지 않기 위함)
    text_hits: HashMap<usize, Vec<[f32; 4]>>,
}

struct Worker<F: Fn(Evt)> {
    emit: F,
    doc: Option<PdfDocument>,
    doc_id: u64,
    path: String,
    password: Option<String>,
    page_count: usize,
    origins: Vec<(f32, f32)>,
    want: VecDeque<usize>,
    want_scale: f32,
    thumbs: VecDeque<usize>,
    thumb_width: f32,
    search: Option<SearchJob>,
    /// 실행 취소용 PDF 전체 스냅샷
    undo: Vec<Vec<u8>>,
    /// 저장 이후 편집 횟수 (실행 취소하면 줄어든다)
    unsaved_edits: i64,
    /// 읽어 둔 글꼴 파일: (경로, 번호) → (문서 안에서 쓸 이름, 글꼴 데이터)
    fonts: HashMap<(String, u32), (String, Vec<u8>)>,
    /// 저장할 때마다 올라가는 번호. 글꼴 이름에 넣어, 저장 때 줄여 둔 글꼴을 다시 쓰지 않게 한다.
    /// 글자 인식기. 바깥 Option은 "아직 만들어 보지 않음", 안쪽은 "이 PC에서 쓸 수 없음"
    recognizer: Option<Option<crate::ocr::Recognizer>>,
    /// 쪽별 글자 인식 결과 (내용이 바뀌면 지운다)
    ocr_cache: HashMap<usize, Vec<crate::ocr::OcrLine>>,
    font_gen: u32,
    /// 이 문서에 텍스트를 넣은 적이 있는지 (있으면 저장할 때 글꼴을 줄인다)
    text_added: bool,
}

pub fn run<F: Fn(Evt)>(rx: Receiver<Req>, emit: F) {
    let mut w = Worker {
        emit,
        doc: None,
        doc_id: 0,
        path: String::new(),
        password: None,
        page_count: 0,
        origins: Vec::new(),
        want: VecDeque::new(),
        want_scale: 1.0,
        thumbs: VecDeque::new(),
        thumb_width: 120.0,
        search: None,
        undo: Vec::new(),
        unsaved_edits: 0,
        fonts: HashMap::new(),
        recognizer: None,
        ocr_cache: HashMap::new(),
        font_gen: 0,
        text_added: false,
    };
    loop {
        let idle = w.want.is_empty() && w.thumbs.is_empty() && w.search.is_none();
        if idle {
            match rx.recv() {
                Ok(req) => w.handle(req),
                Err(_) => return,
            }
        }
        loop {
            match rx.try_recv() {
                Ok(req) => w.handle(req),
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => return,
            }
        }
        w.step();
    }
}

impl<F: Fn(Evt)> Worker<F> {
    fn handle(&mut self, req: Req) {
        match req {
            Req::Open { doc_id, path, password } => self.open(doc_id, path, password),
            Req::Want { doc_id, pages, scale } => {
                if doc_id == self.doc_id {
                    self.want = pages.into();
                    self.want_scale = scale;
                }
            }
            Req::Thumbs { doc_id, pages, width_px } => {
                if doc_id == self.doc_id {
                    self.thumbs = pages.into();
                    self.thumb_width = width_px;
                }
            }
            Req::Search { doc_id, gen, query } => {
                if doc_id == self.doc_id {
                    self.search = if query.is_empty() {
                        None
                    } else {
                        let compact = crate::ocr::compact_query(&query);
                        Some(SearchJob { gen, query, next_page: 0, ocr_phase: false, compact, text_hits: HashMap::new() })
                    };
                }
            }
            Req::Edit { doc_id, op } => {
                if doc_id == self.doc_id {
                    self.edit(op);
                }
            }
            Req::Pages { doc_id, op } => {
                if doc_id == self.doc_id {
                    self.page_op(op);
                }
            }
            Req::TextAt { doc_id, page, rect } => {
                if doc_id == self.doc_id {
                    let origin = self.origins.get(page).copied().unwrap_or((0.0, 0.0));
                    let info = self.doc.as_ref().map(|doc| text_in_rect(doc, page, rect, origin)).unwrap_or_default();
                    (self.emit)(Evt::TextFound { doc_id, page, rect, info });
                }
            }
            Req::Undo { doc_id } => {
                if doc_id == self.doc_id {
                    self.undo_last();
                }
            }
            Req::Save { doc_id, path, remove_password } => {
                if doc_id == self.doc_id {
                    self.save(path, remove_password);
                }
            }
            Req::Export { doc_id, pages, kind } => {
                let result = match self.doc.as_ref() {
                    Some(doc) if doc_id == self.doc_id => crate::output::export(doc, &pages, &kind),
                    _ => Err("열린 문서가 없습니다.".to_string()),
                };
                (self.emit)(Evt::TaskDone { result, open: None });
            }
            Req::Print { doc_id, job } => {
                let result = match self.doc.as_ref() {
                    Some(doc) if doc_id == self.doc_id => {
                        let emit = &self.emit;
                        crate::print::run(doc, &job, &|current, total| {
                            emit(Evt::Progress { message: format!("인쇄 중… {current} / {total}") })
                        })
                        .map(|sent| format!("{sent}쪽을 프린터로 보냈습니다"))
                    }
                    _ => Err("열린 문서가 없습니다.".to_string()),
                };
                (self.emit)(Evt::TaskDone { result, open: None });
            }
            Req::Merge { files, out, options } => {
                let result = crate::output::merge(&files, &out, &options);
                let open = result.is_ok().then(|| out.clone());
                let result = result.map(|pages| format!("{}개 파일을 {pages}쪽짜리 PDF로 합쳤습니다", files.len()));
                (self.emit)(Evt::TaskDone { result, open });
            }
        }
    }

    fn open(&mut self, doc_id: u64, path: String, password: Option<String>) {
        self.doc = None;
        self.doc_id = doc_id;
        self.want.clear();
        self.thumbs.clear();
        self.search = None;
        self.undo.clear();
        self.unsaved_edits = 0;
        self.fonts.clear();
        self.font_gen += 1;
        self.text_added = false;
        self.ocr_cache.clear();

        crate::trace::mark("엔진: 열기 시작");
        let mut doc = match PdfDocument::open(path.as_str()) {
            Ok(d) => d,
            Err(e) => {
                (self.emit)(Evt::OpenFailed { doc_id, message: e.to_string() });
                return;
            }
        };
        let encrypted = doc.needs_password().unwrap_or(false);
        if encrypted {
            let ok = match &password {
                Some(pw) => doc.authenticate(pw).unwrap_or(false),
                None => false,
            };
            if !ok {
                (self.emit)(Evt::NeedPassword { doc_id, wrong: password.is_some() });
                return;
            }
        }
        crate::trace::mark("엔진: 문서 열림");
        let Some((sizes, origins)) = page_geometry(&doc) else {
            (self.emit)(Evt::OpenFailed { doc_id, message: "페이지가 없는 문서입니다.".into() });
            return;
        };
        crate::trace::mark("엔진: 페이지 크기 수집");
        self.page_count = sizes.len();
        self.origins = origins;
        self.doc = Some(doc);
        self.path = path.clone();
        self.password = if encrypted { password } else { None };
        (self.emit)(Evt::Opened { doc_id, path, sizes, encrypted });
    }

    /// 작업 하나를 처리한다 (중간중간 새 요청을 받을 수 있게 짧게 끊는다)
    fn step(&mut self) {
        let Some(doc) = self.doc.as_ref() else {
            self.want.clear();
            self.thumbs.clear();
            self.search = None;
            return;
        };
        if let Some(index) = self.want.pop_front() {
            crate::trace::mark("엔진: 첫 렌더 시작");
            if let Some(buf) = render(doc, index, self.want_scale) {
                crate::trace::mark("엔진: 첫 렌더 끝");
                (self.emit)(Evt::Page { doc_id: self.doc_id, index, scale: self.want_scale, buf });
            }
            return;
        }
        if let Some(job) = self.search.as_mut() {
            if !job.ocr_phase {
                // 1단계: 문서에 들어 있는 텍스트에서 찾는다 (빠름)
                let started = Instant::now();
                while job.next_page < self.page_count && started.elapsed() < Duration::from_millis(12) {
                    let index = job.next_page;
                    job.next_page += 1;
                    let origin = self.origins.get(index).copied().unwrap_or((0.0, 0.0));
                    let rects = search_page(doc, index, &job.query, origin);
                    if !rects.is_empty() {
                        job.text_hits.insert(index, rects.clone());
                        (self.emit)(Evt::Hits { doc_id: self.doc_id, gen: job.gen, index, rects });
                    }
                }
                if job.next_page >= self.page_count {
                    job.ocr_phase = true;
                    job.next_page = 0;
                }
                return;
            }

            // 2단계: 그림이 든 쪽·글자가 거의 없는 쪽을 글자 인식해서 찾는다 (한 번에 한 쪽씩)
            if self.recognizer.is_none() {
                self.recognizer = Some(crate::ocr::Recognizer::new());
            }
            let recognizer = self.recognizer.as_ref().and_then(|r| r.as_ref());
            let mut finished = recognizer.is_none() || job.compact.is_empty();
            while !finished {
                if job.next_page >= self.page_count {
                    finished = true;
                    break;
                }
                let index = job.next_page;
                job.next_page += 1;
                let cached = self.ocr_cache.contains_key(&index);
                if !cached {
                    if !crate::ocr::page_needs_ocr(doc, index) {
                        self.ocr_cache.insert(index, Vec::new());
                        continue; // 인식이 필요 없는 쪽은 바로 다음으로
                    }
                    (self.emit)(Evt::SearchNote {
                        doc_id: self.doc_id,
                        gen: job.gen,
                        note: format!("글자 인식 {} / {}", index + 1, self.page_count),
                    });
                    let lines = recognizer.map(|r| r.recognize_page(doc, index)).unwrap_or_default();
                    self.ocr_cache.insert(index, lines);
                }
                let lines = self.ocr_cache.get(&index).map(|l| l.as_slice()).unwrap_or(&[]);
                let known = job.text_hits.get(&index);
                let rects: Vec<[f32; 4]> = crate::ocr::find_in_lines(lines, &job.compact)
                    .into_iter()
                    .filter(|r| !known.map(|k| k.iter().any(|t| crate::ocr::overlaps(r, t))).unwrap_or(false))
                    .collect();
                if !rects.is_empty() {
                    (self.emit)(Evt::Hits { doc_id: self.doc_id, gen: job.gen, index, rects });
                }
                if !cached {
                    break; // 방금 인식을 돌렸으면 새 요청을 받을 수 있게 한 번 쉰다
                }
            }
            if finished {
                (self.emit)(Evt::SearchDone { doc_id: self.doc_id, gen: job.gen });
                self.search = None;
            }
            return;
        }
        if let Some(index) = self.thumbs.pop_front() {
            let scale = doc
                .load_page(index as i32)
                .and_then(|p| p.bounds())
                .map(|r| self.thumb_width / (r.x1 - r.x0).max(1.0))
                .unwrap_or(0.2);
            if let Some(buf) = render(doc, index, scale) {
                (self.emit)(Evt::Thumb { doc_id: self.doc_id, index, buf });
            }
        }
    }

    // ------------------------------------------------------------ 편집
    fn edit(&mut self, op: EditOp) {
        let page = op.page();
        if page >= self.page_count {
            return;
        }
        match self.apply_edit(op) {
            Ok(()) => {
                self.unsaved_edits += 1;
                self.emit_changed(Some(page));
            }
            Err(message) => (self.emit)(Evt::EditFailed { doc_id: self.doc_id, message }),
        }
    }

    fn apply_edit(&mut self, op: EditOp) -> Result<(), String> {
        // 텍스트에 쓸 글꼴 파일은 처음 필요할 때 한 번만 읽는다
        let mut font_key = None;
        if let EditOp::Text { style, text, .. } = &op {
            if !text.is_empty() {
                let key = (style.font_path.clone(), style.font_index);
                if !self.fonts.contains_key(&key) {
                    let data = crate::fonts::face_bytes(std::path::Path::new(&style.font_path), style.font_index)
                        .map_err(|e| format!("글꼴을 읽을 수 없습니다: {e}"))?;
                    let alias = format!("bossf{}x{}", self.font_gen, self.fonts.len());
                    self.fonts.insert(key.clone(), (alias, data));
                }
                font_key = Some(key);
            }
        }
        let Some(doc) = self.doc.as_mut() else { return Err("열린 문서가 없습니다.".into()) };

        // 실행 취소용 스냅샷을 먼저 남긴다
        let mut snapshot = Vec::new();
        doc.write_to(&mut snapshot).map_err(|e| format!("실행 취소 지점을 만들 수 없습니다: {e}"))?;

        let font = font_key.as_ref().and_then(|key| self.fonts.get(key));
        let drawn = (|| -> Result<(), mupdf::Error> {
            let mut page = doc.load_pdf_page(op.page() as i32)?;
            let mut shape = Shape::new(&mut page)?;
            match &op {
                EditOp::Highlight { rect, .. } => {
                    shape.draw_rect(&Rect::new(rect[0], rect[1], rect[2], rect[3]))?.finish(&FinishOptions {
                        color: None,
                        fill: Some(PdfColor::rgb(1.0, 0.9, 0.2)),
                        fill_opacity: Some(0.4),
                        ..Default::default()
                    })?;
                }
                EditOp::Whiteout { rect, .. } => {
                    shape.draw_rect(&Rect::new(rect[0], rect[1], rect[2], rect[3]))?.finish(&FinishOptions {
                        color: Some(PdfColor::rgb(1.0, 1.0, 1.0)),
                        fill: Some(PdfColor::rgb(1.0, 1.0, 1.0)),
                        ..Default::default()
                    })?;
                }
                EditOp::Ink { points, .. } => {
                    let pts: Vec<Point> = points.iter().map(|p| Point::new(p.0, p.1)).collect();
                    shape.draw_polyline(&pts)?.finish(&FinishOptions {
                        color: Some(PdfColor::rgb(0.1, 0.3, 0.9)),
                        fill: None,
                        width: 2.0,
                        line_cap: Some(1),
                        line_join: Some(1),
                        close_path: false,
                        ..Default::default()
                    })?;
                }
                EditOp::Text { x, y, baseline, text, style, lineheight, cover, .. } => {
                    if let Some(rect) = cover {
                        shape.draw_rect(&Rect::new(rect[0], rect[1], rect[2], rect[3]))?.finish(&FinishOptions {
                            color: Some(PdfColor::rgb(1.0, 1.0, 1.0)),
                            fill: Some(PdfColor::rgb(1.0, 1.0, 1.0)),
                            ..Default::default()
                        })?;
                    }
                    if let Some((alias, data)) = font {
                        // insert_text의 기준점은 첫 줄의 글자 밑선
                        let origin = if *baseline { Point::new(*x, *y) } else { Point::new(*x, *y + style.size * 0.92) };
                        shape.insert_text(
                            origin,
                            text,
                            &TextOptions {
                                fontsize: style.size,
                                lineheight: *lineheight,
                                fontname: alias.clone(),
                                fontfile: Some(data.as_slice()),
                                fill: Some(PdfColor::rgb(style.color[0], style.color[1], style.color[2])),
                                simple: false,
                                ..Default::default()
                            },
                        )?;
                    }
                }
            }
            shape.commit(doc, true)?;
            Ok(())
        })();

        match drawn {
            Ok(()) => {
                if font_key.is_some() {
                    self.text_added = true;
                }
                self.undo.push(snapshot);
                if self.undo.len() > UNDO_MAX {
                    self.undo.remove(0);
                }
                Ok(())
            }
            Err(e) => {
                // 그리다 실패하면 문서를 스냅샷으로 되돌려 반쯤 바뀐 상태가 남지 않게 한다
                if let Ok(restored) = self.load_bytes(&snapshot) {
                    self.doc = Some(restored);
                }
                Err(format!("편집을 적용할 수 없습니다: {e}"))
            }
        }
    }

    fn page_op(&mut self, op: PageOp) {
        let count = self.page_count;
        let result = (|| -> Result<Option<usize>, String> {
            let Some(doc) = self.doc.as_mut() else { return Err("열린 문서가 없습니다.".into()) };
            match &op {
                PageOp::Rotate { page, .. } | PageOp::Delete { page } if *page >= count => return Err("없는 페이지입니다.".into()),
                PageOp::Move { from, to } if *from >= count || *to >= count => return Err("없는 페이지입니다.".into()),
                PageOp::Delete { .. } if count <= 1 => return Err("마지막 한 쪽은 삭제할 수 없습니다.".into()),
                _ => {}
            }
            let mut snapshot = Vec::new();
            doc.write_to(&mut snapshot).map_err(|e| format!("실행 취소 지점을 만들 수 없습니다: {e}"))?;
            let done = (|| -> Result<Option<usize>, mupdf::Error> {
                match op {
                    PageOp::Rotate { page, delta } => {
                        let mut pdf_page = doc.load_pdf_page(page as i32)?;
                        let current = pdf_page.rotation()?;
                        pdf_page.set_rotation((current + delta).rem_euclid(360))?;
                        Ok(None)
                    }
                    PageOp::Delete { page } => {
                        doc.delete_page(page as i32)?;
                        Ok(None)
                    }
                    PageOp::Move { from, to } => {
                        doc.move_page(from, to)?;
                        Ok(Some(to))
                    }
                }
            })();
            match done {
                Ok(focus) => {
                    self.undo.push(snapshot);
                    if self.undo.len() > UNDO_MAX {
                        self.undo.remove(0);
                    }
                    Ok(focus)
                }
                Err(e) => {
                    if let Ok(restored) = self.load_bytes(&snapshot) {
                        self.doc = Some(restored);
                    }
                    Err(format!("페이지를 바꿀 수 없습니다: {e}"))
                }
            }
        })();
        match result {
            Ok(focus) => {
                self.unsaved_edits += 1;
                self.emit_restructured(focus);
            }
            Err(message) => (self.emit)(Evt::EditFailed { doc_id: self.doc_id, message }),
        }
    }

    /// 페이지 크기 표를 다시 만들어 UI에 알린다
    fn emit_restructured(&mut self, focus: Option<usize>) {
        self.ocr_cache.clear();
        self.want.clear();
        self.thumbs.clear();
        self.search = None;
        let (sizes, origins) = self.doc.as_ref().and_then(|d| page_geometry(d)).unwrap_or_default();
        self.page_count = sizes.len();
        self.origins = origins;
        (self.emit)(Evt::Restructured {
            doc_id: self.doc_id,
            sizes,
            focus,
            can_undo: !self.undo.is_empty(),
            dirty: self.unsaved_edits != 0,
        });
    }

    fn undo_last(&mut self) {
        let Some(snapshot) = self.undo.pop() else { return };
        match self.load_bytes(&snapshot) {
            Ok(doc) => {
                self.doc = Some(doc);
                self.unsaved_edits -= 1;
                // 되돌린 것이 페이지 조작일 수도 있으므로 배치부터 새로 알린다
                self.emit_restructured(None);
            }
            Err(e) => {
                self.undo.push(snapshot);
                (self.emit)(Evt::EditFailed { doc_id: self.doc_id, message: format!("실행 취소 실패: {e}") });
            }
        }
    }

    fn emit_changed(&mut self, page: Option<usize>) {
        match page {
            Some(index) => {
                self.ocr_cache.remove(&index);
            }
            None => self.ocr_cache.clear(),
        }
        // 진행 중이던 검색은 바뀌기 전 내용 기준이므로 멈춘다 (UI가 다시 요청)
        self.search = None;
        (self.emit)(Evt::Changed {
            doc_id: self.doc_id,
            page,
            can_undo: !self.undo.is_empty(),
            dirty: self.unsaved_edits != 0,
        });
    }

    /// 메모리의 PDF를 열고, 암호 문서면 열 때 쓴 비밀번호로 다시 인증한다
    fn load_bytes(&self, bytes: &[u8]) -> Result<PdfDocument, String> {
        let mut doc = PdfDocument::from_bytes(bytes).map_err(|e| e.to_string())?;
        if doc.needs_password().unwrap_or(false) {
            let ok = self.password.as_deref().map(|pw| doc.authenticate(pw).unwrap_or(false)).unwrap_or(false);
            if !ok {
                return Err("비밀번호 인증에 실패했습니다.".into());
            }
        }
        Ok(doc)
    }

    fn save(&mut self, target: Option<String>, remove_password: bool) {
        let path = target.unwrap_or_else(|| self.path.clone());
        let result = self.save_to(&path, remove_password);
        if result.is_ok() {
            self.path = path.clone();
            self.unsaved_edits = 0;
        }
        let encrypted = self.password.is_some();
        (self.emit)(Evt::Saved { doc_id: self.doc_id, path, error: result.err(), encrypted });
    }

    fn save_to(&mut self, path: &str, remove_password: bool) -> Result<(), String> {
        let Some(doc) = self.doc.as_ref() else { return Err("열린 문서가 없습니다.".into()) };
        let mut options = PdfWriteOptions::default();
        options.set_garbage_level(3).set_compress(true);
        if remove_password {
            options.set_encryption(Encryption::None);
        }

        let mut bytes = Vec::new();
        if self.text_added && !doc.has_acro_form().unwrap_or(true) {
            // 텍스트를 넣으면 글꼴 파일 전체(수 MB)가 문서에 들어가므로, 실제로 쓴 글자만 남긴다.
            // 줄인 글꼴로는 새 글자를 쓸 수 없어서, 편집 중인 문서가 아니라 사본에 적용한다.
            // (입력 양식이 있는 문서는 나중에 입력할 글자가 필요할 수 있어 줄이지 않는다)
            let mut plain = Vec::new();
            doc.write_to(&mut plain).map_err(|e| e.to_string())?;
            let mut copy = self.load_bytes(&plain)?;
            if copy.subset_fonts().is_err() {
                copy = self.load_bytes(&plain)?; // 줄이기에 실패하면 줄이지 않은 채로 저장
            }
            copy.write_to_with_options(&mut bytes, options).map_err(|e| e.to_string())?;
        } else {
            doc.write_to_with_options(&mut bytes, options).map_err(|e| e.to_string())?;
        }

        // 열어 둔 원본 파일을 덮어쓸 수 있도록, 문서를 메모리 사본으로 바꿔 파일 잠금을 푼다.
        // 이 사본의 글꼴은 줄어든 상태이므로, 이후에 넣는 텍스트는 새 이름으로 글꼴을 다시 넣는다.
        let reloaded = self.load_bytes(&bytes)?;
        if remove_password {
            self.password = None; // 이제 암호 없는 문서다
        }
        self.doc = Some(reloaded);
        self.fonts.clear();
        self.font_gen += 1;

        // 임시 파일에 먼저 쓰고 교체: 쓰다가 실패해도 기존 파일은 그대로 남는다
        let tmp = format!("{path}.bosspdf_tmp");
        std::fs::write(&tmp, &bytes).map_err(|e| format!("{e}"))?;
        if let Err(e) = std::fs::rename(&tmp, path) {
            let _ = std::fs::remove_file(&tmp);
            return Err(format!("{e}"));
        }
        Ok(())
    }
}

fn page_geometry(doc: &Document) -> Option<(Vec<(f32, f32)>, Vec<(f32, f32)>)> {
    let count = doc.page_count().unwrap_or(0).max(0) as usize;
    if count == 0 {
        return None;
    }
    let mut sizes = Vec::with_capacity(count);
    let mut origins = Vec::with_capacity(count);
    for i in 0..count {
        let (w, h, x0, y0) = match doc.load_page(i as i32).and_then(|p| p.bounds()) {
            Ok(r) => ((r.x1 - r.x0).max(1.0), (r.y1 - r.y0).max(1.0), r.x0, r.y0),
            Err(_) => (595.0, 842.0, 0.0, 0.0),
        };
        sizes.push((w, h));
        origins.push((x0, y0));
    }
    Some((sizes, origins))
}

fn render(doc: &Document, index: usize, scale: f32) -> Option<PixelBuf> {
    let page = doc.load_page(index as i32).ok()?;
    let bounds = page.bounds().ok()?;
    let area = (bounds.x1 - bounds.x0).max(1.0) * (bounds.y1 - bounds.y0).max(1.0);
    let max_scale = (MAX_PIXELS / area).sqrt();
    let scale = scale.min(max_scale).max(0.02);

    let pixmap = page
        .to_pixmap(&Matrix::new_scale(scale, scale), &Colorspace::device_rgb(), false, true)
        .ok()?;
    let (w, h) = (pixmap.width() as usize, pixmap.height() as usize);
    if w == 0 || h == 0 || pixmap.n() != 3 {
        return None;
    }
    let stride = pixmap.stride() as usize;
    let samples = pixmap.samples();
    if samples.len() < stride * (h - 1) + w * 3 {
        return None;
    }
    let mut buf = PixelBuf::new(w as u32, h as u32);
    let dst = buf.make_mut_bytes();
    if stride == w * 3 {
        dst.copy_from_slice(&samples[..w * 3 * h]);
    } else {
        for row in 0..h {
            dst[row * w * 3..(row + 1) * w * 3].copy_from_slice(&samples[row * stride..row * stride + w * 3]);
        }
    }
    Some(buf)
}

/// 영역(페이지 왼쪽 위 기준 pt) 안에 중심이 들어 있는 글자들을 줄 단위로 모은다
fn text_in_rect(doc: &Document, index: usize, rect: [f32; 4], origin: (f32, f32)) -> TextInfo {
    let mut info = TextInfo { size: 12.0, lineheight: 1.2, ..Default::default() };
    let Ok(page) = doc.load_page(index as i32) else { return info };
    let Ok(text_page) = page.to_text_page(TextPageFlags::empty()) else { return info };
    let (x0, y0, x1, y1) = (rect[0] + origin.0, rect[1] + origin.1, rect[2] + origin.0, rect[3] + origin.1);

    let mut lines: Vec<String> = Vec::new();
    let mut baselines: Vec<f32> = Vec::new();
    for block in text_page.blocks() {
        for line in block.lines() {
            let mut picked = String::new();
            for ch in line.chars() {
                let q = ch.quad();
                let cx = (q.ul.x + q.ur.x + q.ll.x + q.lr.x) / 4.0;
                let cy = (q.ul.y + q.ur.y + q.ll.y + q.lr.y) / 4.0;
                if cx < x0 || cx > x1 || cy < y0 || cy > y1 {
                    continue;
                }
                let Some(c) = ch.char() else { continue };
                if picked.is_empty() {
                    baselines.push(ch.origin().y);
                    if info.baseline.is_none() {
                        // 첫 글자의 서식을 대표값으로 쓴다
                        let o = ch.origin();
                        info.baseline = Some((o.x - origin.0, o.y - origin.1));
                        info.size = ch.size();
                        let argb = ch.argb();
                        info.color = [
                            ((argb >> 16) & 0xFF) as f32 / 255.0,
                            ((argb >> 8) & 0xFF) as f32 / 255.0,
                            (argb & 0xFF) as f32 / 255.0,
                        ];
                        let font = ch.font();
                        info.font_name = font.as_ref().map(|f| f.name().to_string()).unwrap_or_default();
                        info.bold = ch.flags().contains(TextCharFlags::BOLD) || font.map(|f| f.is_bold()).unwrap_or(false);
                    }
                }
                picked.push(c);
            }
            let picked = picked.trim_end().to_string();
            if !picked.trim().is_empty() {
                lines.push(picked);
            } else if !picked.is_empty() || baselines.len() > lines.len() {
                baselines.truncate(lines.len());
            }
        }
    }
    if lines.len() >= 2 && baselines.len() >= 2 && info.size > 0.0 {
        let gap = (baselines[baselines.len() - 1] - baselines[0]) / (baselines.len() - 1) as f32;
        info.lineheight = (gap / info.size).clamp(0.8, 3.0);
    }
    info.lines = lines.len();
    info.text = lines.join("\n");
    info
}

fn search_page(doc: &Document, index: usize, query: &str, origin: (f32, f32)) -> Vec<[f32; 4]> {
    let Ok(page) = doc.load_page(index as i32) else {
        return Vec::new();
    };
    let Ok(quads) = page.search(query, 512) else {
        return Vec::new();
    };
    quads
        .iter()
        .map(|q| {
            let xs = [q.ul.x, q.ur.x, q.ll.x, q.lr.x];
            let ys = [q.ul.y, q.ur.y, q.ll.y, q.lr.y];
            let x0 = xs.iter().copied().fold(f32::INFINITY, f32::min);
            let x1 = xs.iter().copied().fold(f32::NEG_INFINITY, f32::max);
            let y0 = ys.iter().copied().fold(f32::INFINITY, f32::min);
            let y1 = ys.iter().copied().fold(f32::NEG_INFINITY, f32::max);
            [x0 - origin.0, y0 - origin.1, x1 - x0, y1 - y0]
        })
        .collect()
}
