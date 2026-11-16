//! BossPDF (Rust 시제품) — PDF 뷰어
//! 열기 · 연속 스크롤 · 확대/축소 · 썸네일 · 검색
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod engine;
mod fonts;
mod ocr;
mod output;
mod print;
mod selftest;
mod settings;
mod shell;
mod trace;
mod updater;

use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::rc::Rc;
use std::collections::VecDeque;
use std::sync::mpsc::{self, Sender};
use std::sync::Mutex;

use engine::{EditOp, Evt, PageOp, PixelBuf, Req, TextInfo, TextStyle};
use slint::{ComponentHandle, Image, Model, ModelRc, VecModel};

slint::include_modules!();

/// 100% 배율에서 1pt가 차지하는 논리 픽셀 (96dpi 기준)
const PX_PER_PT: f32 = 96.0 / 72.0;
const PAGE_GAP: f32 = 14.0;
const MARGIN: f32 = 20.0;
const SCROLLBAR: f32 = 14.0;
const ZOOM_STEP: f32 = 1.15;
const ZOOM_MIN: f32 = 0.15;
const ZOOM_MAX: f32 = 8.0;
const THUMB_W: f32 = 120.0;
const THUMB_MAX_H: f32 = 220.0;
const THUMB_ROW_EXTRA: f32 = 30.0;
const THUMB_CACHE_MAX: usize = 400;
/// 편집 도구 번호 (ui/app.slint의 tool 값과 같아야 한다)
const TOOL_WHITEOUT: i32 = 2;
const TOOL_HIGHLIGHT: i32 = 3;
const TOOL_EDIT_TEXT: i32 = 5;
/// 손글씨 선 굵기 (pt)
const PEN_WIDTH_PT: f32 = 2.0;

thread_local! {
    static APP: RefCell<Option<Rc<App>>> = const { RefCell::new(None) };
}

fn with_app(f: impl FnOnce(&Rc<App>)) {
    let app = APP.with(|a| a.borrow().clone());
    if let Some(app) = app {
        f(&app);
    }
}

#[derive(Default)]
struct State {
    doc_id: u64,
    path: String,
    pending_path: Option<String>,
    /// 페이지 크기 (pt)
    sizes: Vec<(f32, f32)>,
    /// 1pt당 논리 픽셀
    zoom: f32,
    fit_width: bool,
    ys: Vec<f32>,
    content_w: f32,
    content_h: f32,
    layout_ver: u64,

    /// 렌더링된 페이지: (이미지, 렌더링 배율(pt당 실제 픽셀), 버전)
    cache: HashMap<usize, (Image, f32, u64)>,
    render_ver: u64,
    last_want: Vec<usize>,
    last_want_scale: f32,
    pending_renders: usize,
    rows: Vec<usize>,
    row_stamps: Vec<(u64, u64, u64)>,

    // 검색
    search_gen: u64,
    search_query: String,
    search_running: bool,
    /// 검색이 글자 인식 단계일 때의 진행 표시
    search_note: String,
    hits: HashMap<usize, Vec<[f32; 4]>>,
    hit_order: Vec<(usize, usize)>,
    current_hit: Option<usize>,
    hits_ver: u64,

    // 썸네일
    thumb_sizes: Vec<(f32, f32)>,
    thumb_ys: Vec<f32>,
    thumbs_content_h: f32,
    thumb_cache: HashMap<usize, Image>,
    thumb_requested: HashSet<usize>,
    thumb_sig: (usize, usize, u64),
    thumb_ver: u64,
    /// 내용이 바뀌어 다시 그려야 하는 썸네일
    thumb_stale: HashSet<usize>,
    current_page: usize,

    // 편집
    can_undo: bool,
    dirty: bool,
    /// 엔진에 보냈지만 아직 결과가 안 온 편집·실행 취소 수
    pending_edits: usize,
    saving: bool,
    last_saved: Option<Result<String, String>>,
    quit_after_save: bool,
    /// 그리는 중인 손글씨: (페이지, 페이지 안 논리 픽셀 좌표들)
    pen: Option<(usize, Vec<(f32, f32)>)>,
    /// 이 페이지가 다시 그려지면 손글씨 미리보기를 지운다
    pen_clear_on_render: Option<usize>,
    /// 편집 뒤 자동으로 다시 돌리는 검색: 결과 위치로 화면을 옮기지 않는다
    search_quiet: bool,
    /// 수정하려고 드래그한 기존 텍스트의 위치 정보 (입력창이 떠 있는 동안)
    replace: Option<ReplaceCtx>,
    /// 썸네일을 끌어서 옮기는 중: (옮기는 쪽, 끼워 넣을 자리 0..=쪽수)
    thumb_drag: Option<(usize, usize)>,
}

struct ReplaceCtx {
    page: usize,
    /// 흰색으로 덮을 영역 (pt)
    rect: [f32; 4],
    /// 기존 첫 글자의 밑선 시작점 (pt). 없으면 영역 왼쪽 위에 맞춘다
    baseline: Option<(f32, f32)>,
    lineheight: f32,
}

pub struct App {
    ui: slint::Weak<AppWindow>,
    tx: Sender<Req>,
    st: RefCell<State>,
    pages_model: Rc<VecModel<PageView>>,
    thumbs_model: Rc<VecModel<ThumbView>>,
    toast_timer: slint::Timer,
    /// 설치 글꼴 목록 (텍스트 도구를 처음 쓸 때 읽는다)
    fonts: RefCell<Option<Rc<fonts::FontCatalog>>>,
    /// 합치기 창에 올려 둔 파일 경로들
    merge_files: RefCell<Vec<String>>,
    /// 내보내기·합치기처럼 엔진에 맡기고 기다리는 작업 수 (문서를 새로 열어도 유지된다)
    pending_tasks: std::cell::Cell<usize>,
    /// "이 문서는 이 창이 열고 있다"는 표식 (같은 문서를 또 열면 이 창을 앞으로 가져오게 함)
    doc_claim: RefCell<Option<shell::DocumentClaim>>,
    /// 탐색기에서 늦게 넘어오는 합치기 파일을 받는 타이머
    merge_poll: slint::Timer,
    /// 설정을 파일에 남길지 (자동 점검 중에는 사용자의 설정을 건드리지 않는다)
    persist_settings: bool,
    /// 확인된 새 버전 정보와, 이미 내려받은 설치 파일 경로
    update: RefCell<Option<updater::UpdateInfo>>,
    update_installer: RefCell<Option<String>>,
}

impl App {
    fn ui(&self) -> Option<AppWindow> {
        self.ui.upgrade()
    }

    // ------------------------------------------------------------ 열기
    pub fn open_path(&self, path: String, password: Option<String>) {
        let doc_id = {
            let mut st = self.st.borrow_mut();
            st.doc_id += 1;
            st.pending_path = Some(path.clone());
            st.doc_id
        };
        let _ = self.tx.send(Req::Open { doc_id, path, password });
    }

    fn pick_and_open(&self) {
        if !self.confirm_discard("다른 문서를 열까요?") {
            return;
        }
        let picked = rfd::FileDialog::new().add_filter("PDF 문서", &["pdf"]).set_title("PDF 열기").pick_file();
        if let Some(path) = picked {
            self.open_path(path.to_string_lossy().into_owned(), None);
        }
    }

    fn on_opened(&self, doc_id: u64, path: String, sizes: Vec<(f32, f32)>, encrypted: bool) {
        let Some(ui) = self.ui() else { return };
        trace::mark("문서 열림(UI)");
        {
            let mut st = self.st.borrow_mut();
            if doc_id != st.doc_id {
                return;
            }
            let keep_id = st.doc_id;
            *st = State { doc_id: keep_id, path: path.clone(), sizes, fit_width: true, zoom: PX_PER_PT, ..State::default() };

            layout_thumbs(&mut st);
        }
        let title = std::path::Path::new(&path)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        let (count, thumbs_h) = {
            let st = self.st.borrow();
            (st.sizes.len(), st.thumbs_content_h)
        };
        self.pages_model.set_vec(Vec::new());
        self.thumbs_model.set_vec(Vec::new());
        ui.set_doc_title(title.into());
        ui.set_page_count(count as i32);
        ui.set_current_page(0);
        ui.set_thumbs_content_h(thumbs_h);
        ui.set_thumbs_scroll_y(0.0);
        ui.set_scroll_x(0.0);
        ui.set_scroll_y(0.0);
        ui.set_ask_password(false);
        ui.set_password_error("".into());
        ui.set_search_label("".into());
        ui.set_status_text("".into());
        ui.set_doc_encrypted(encrypted);
        ui.set_can_undo(false);
        ui.set_dirty(false);
        ui.set_tool(0);
        ui.set_text_page(-1);
        ui.set_pen_page(-1);
        ui.set_pen_path("".into());
        ui.set_has_doc(true);
        self.relayout(None);
        self.refresh_thumbs();
        self.claim_document(&path);
    }

    /// 지금 연 문서를 이 창의 것으로 표시한다
    fn claim_document(&self, path: &str) {
        let mut claim = self.doc_claim.borrow_mut();
        *claim = None; // 이전 문서의 표식을 먼저 내려놓는다
        *claim = shell::claim_document(path, self.window_hwnd());
    }

    fn on_need_password(&self, doc_id: u64, wrong: bool) {
        let Some(ui) = self.ui() else { return };
        if doc_id != self.st.borrow().doc_id {
            return;
        }
        ui.set_password_error(if wrong { "비밀번호가 일치하지 않습니다.".into() } else { "".into() });
        ui.set_ask_password(true);
    }

    fn on_open_failed(&self, doc_id: u64, message: String) {
        let Some(ui) = self.ui() else { return };
        if doc_id != self.st.borrow().doc_id {
            return;
        }
        if ui.get_has_doc() {
            return; // 이미 열린 문서는 그대로 둔다
        }
        ui.set_status_text(format!("문서를 열 수 없습니다: {message}").into());
    }

    // ------------------------------------------------------------ 배치
    /// 페이지 위치를 다시 계산한다. anchor = (페이지, 페이지 높이 대비 비율) 위치를 화면 맨 위에 유지.
    fn relayout(&self, anchor: Option<(usize, f32)>) {
        let Some(ui) = self.ui() else { return };
        let view_w = ui.get_view_w();
        let view_h = ui.get_view_h();
        let (content_w, content_h, new_scroll, zoom) = {
            let mut st = self.st.borrow_mut();
            if st.sizes.is_empty() {
                return;
            }
            let max_w_pt = st.sizes.iter().map(|s| s.0).fold(1.0, f32::max);
            if st.fit_width && view_w > 80.0 {
                st.zoom = ((view_w - 2.0 * MARGIN - SCROLLBAR) / max_w_pt).clamp(ZOOM_MIN, ZOOM_MAX);
            }
            let zoom = st.zoom;
            let mut y = PAGE_GAP;
            let mut ys = Vec::with_capacity(st.sizes.len());
            for &(_, h) in &st.sizes {
                ys.push(y);
                y += h * zoom + PAGE_GAP;
            }
            st.ys = ys;
            st.content_h = y;
            st.content_w = (max_w_pt * zoom + 2.0 * MARGIN).max(view_w - SCROLLBAR);
            st.layout_ver += 1;
            let new_scroll = anchor.map(|(page, frac)| {
                let page = page.min(st.sizes.len() - 1);
                st.ys[page] + frac * st.sizes[page].1 * zoom
            });
            (st.content_w, st.content_h, new_scroll, zoom)
        };
        ui.set_content_w(content_w);
        ui.set_content_h(content_h);
        ui.set_zoom_label(format!("{}%", (zoom / PX_PER_PT * 100.0).round() as i32).into());
        ui.set_zoom_px(zoom);
        ui.set_pen_width(PEN_WIDTH_PT * zoom);
        if let Some(top) = new_scroll {
            let max_top = (content_h - view_h).max(0.0);
            ui.set_scroll_y(-top.clamp(0.0, max_top));
        }
        self.refresh_view();
    }

    fn top_anchor(&self) -> Option<(usize, f32)> {
        let ui = self.ui()?;
        let st = self.st.borrow();
        if st.ys.is_empty() {
            return None;
        }
        let top = -ui.get_scroll_y();
        let page = page_at(&st.ys, top);
        let h = st.sizes[page].1 * st.zoom;
        Some((page, (top - st.ys[page]) / h.max(1.0)))
    }

    fn set_zoom(&self, zoom: Option<f32>) {
        let anchor = self.top_anchor();
        {
            let mut st = self.st.borrow_mut();
            if st.sizes.is_empty() {
                return;
            }
            match zoom {
                Some(z) => {
                    st.zoom = z.clamp(ZOOM_MIN, ZOOM_MAX);
                    st.fit_width = false;
                }
                None => st.fit_width = true,
            }
        }
        self.relayout(anchor);
    }

    fn zoom_by(&self, factor: f32) {
        let z = self.st.borrow().zoom;
        self.set_zoom(Some(z * factor));
    }

    // ------------------------------------------------------------ 화면 갱신
    /// 스크롤 위치에 맞춰 보이는 페이지만 모델에 올리고, 필요한 페이지를 엔진에 요청한다.
    fn refresh_view(&self) {
        let Some(ui) = self.ui() else { return };
        let view_w = ui.get_view_w();
        let view_h = ui.get_view_h();
        let top = -ui.get_scroll_y();
        let device_scale = ui.window().scale_factor().max(0.5);

        // 창 너비가 바뀌었는데 '너비 맞춤' 상태면 배치를 다시 계산
        let needs_fit = {
            let st = self.st.borrow();
            if st.sizes.is_empty() {
                return;
            }
            let max_w_pt = st.sizes.iter().map(|s| s.0).fold(1.0, f32::max);
            let fit_zoom = ((view_w - 2.0 * MARGIN - SCROLLBAR) / max_w_pt).clamp(ZOOM_MIN, ZOOM_MAX);
            let wanted_content_w = (max_w_pt * st.zoom + 2.0 * MARGIN).max(view_w - SCROLLBAR);
            view_w > 80.0
                && ((st.fit_width && (fit_zoom - st.zoom).abs() > 0.001) || (wanted_content_w - st.content_w).abs() > 0.5)
        };
        if needs_fit {
            let anchor = self.top_anchor();
            self.relayout(anchor);
            return;
        }

        let mut want_msg = None;
        let current_page;
        let mut model_ops: Option<(Vec<usize>, Vec<Option<PageView>>)> = None;
        {
            let mut st = self.st.borrow_mut();
            let count = st.sizes.len();
            let zoom = st.zoom;
            let first_vis = page_at(&st.ys, top);
            let last_vis = page_at(&st.ys, top + view_h.max(1.0));
            current_page = page_at(&st.ys, top + view_h * 0.4);
            st.current_page = current_page;

            let first = first_vis.saturating_sub(1);
            let last = (last_vis + 1).min(count - 1);
            let keep_first = first_vis.saturating_sub(3);
            let keep_last = (last_vis + 3).min(count - 1);
            st.cache.retain(|i, _| *i >= keep_first && *i <= keep_last);

            // 엔진에 요청할 페이지 (화면 중앙에 가까운 순)
            let target_scale = zoom * device_scale;
            let mut needed: Vec<usize> = (first..=last)
                .filter(|i| match st.cache.get(i) {
                    Some((_, scale, _)) => (scale - target_scale).abs() > target_scale * 0.01,
                    None => true,
                })
                .collect();
            needed.sort_by_key(|i| i.abs_diff(current_page));
            st.pending_renders = needed.len();
            if needed != st.last_want || (target_scale - st.last_want_scale).abs() > 0.0001 {
                st.last_want = needed.clone();
                st.last_want_scale = target_scale;
                want_msg = Some(Req::Want { doc_id: st.doc_id, pages: needed, scale: target_scale });
            }

            // 모델 행 계산 (바뀐 행만 갱신하도록 행별 도장을 비교)
            let new_rows: Vec<usize> = (first..=last).collect();
            let mut new_stamps = Vec::with_capacity(new_rows.len());
            let mut items = Vec::with_capacity(new_rows.len());
            for &i in &new_rows {
                let stamp = (st.layout_ver, st.hits_ver, st.cache.get(&i).map(|c| c.2).unwrap_or(0));
                let unchanged = st.rows.iter().position(|r| *r == i).map(|pos| st.row_stamps[pos] == stamp).unwrap_or(false);
                new_stamps.push(stamp);
                if unchanged {
                    items.push(None);
                    continue;
                }
                let (w_pt, h_pt) = st.sizes[i];
                let (w, h) = (w_pt * zoom, h_pt * zoom);
                let current = st.current_hit.and_then(|c| st.hit_order.get(c).copied());
                let hits: Vec<Hit> = st
                    .hits
                    .get(&i)
                    .map(|rects| {
                        rects
                            .iter()
                            .enumerate()
                            .map(|(n, r)| Hit {
                                x: r[0] * zoom - 1.0,
                                y: r[1] * zoom - 1.0,
                                w: r[2] * zoom + 2.0,
                                h: r[3] * zoom + 2.0,
                                current: current == Some((i, n)),
                            })
                            .collect()
                    })
                    .unwrap_or_default();
                let cached = st.cache.get(&i);
                items.push(Some(PageView {
                    index: i as i32,
                    x: ((st.content_w - w) / 2.0).max(MARGIN),
                    y: st.ys[i],
                    w,
                    h,
                    image: cached.map(|c| c.0.clone()).unwrap_or_default(),
                    ready: cached.is_some(),
                    hits: ModelRc::new(VecModel::from(hits)),
                }));
            }
            if new_rows != st.rows || items.iter().any(|i| i.is_some()) {
                model_ops = Some((st.rows.clone(), items));
            }
            st.rows = new_rows;
            st.row_stamps = new_stamps;
        }

        if let Some((old_rows, items)) = model_ops {
            let new_rows = self.st.borrow().rows.clone();
            self.apply_page_rows(&old_rows, &new_rows, items);
        }
        if let Some(msg) = want_msg {
            let _ = self.tx.send(msg);
        }
        if ui.get_current_page() != current_page as i32 {
            ui.set_current_page(current_page as i32);
            self.keep_thumb_visible(current_page);
            self.refresh_thumbs();
        }
    }

    /// 페이지 모델을 최소한으로 고친다 (행을 통째로 갈면 텍스처를 다시 올리느라 스크롤이 끊긴다)
    fn apply_page_rows(&self, old_rows: &[usize], new_rows: &[usize], items: Vec<Option<PageView>>) {
        let model = &self.pages_model;
        let overlap = !old_rows.is_empty()
            && !new_rows.is_empty()
            && old_rows[0] <= *new_rows.last().unwrap()
            && new_rows[0] <= *old_rows.last().unwrap();
        let build = |pos: usize, items: &[Option<PageView>]| -> PageView {
            items[pos].clone().unwrap_or_else(|| {
                // 도장은 같지만 모델에 없던 행: 기존 모델에서 찾아 재사용
                let idx = new_rows[pos];
                old_rows
                    .iter()
                    .position(|r| *r == idx)
                    .and_then(|p| model.row_data(p))
                    .unwrap_or_default()
            })
        };
        if !overlap {
            let rows: Vec<PageView> = (0..new_rows.len()).map(|pos| build(pos, &items)).collect();
            model.set_vec(rows);
            return;
        }
        // 겹치는 구간은 그대로 두고 양 끝만 넣고 뺀다
        let mut cur: Vec<usize> = old_rows.to_vec();
        while cur[0] < new_rows[0] {
            model.remove(0);
            cur.remove(0);
        }
        while *cur.last().unwrap() > *new_rows.last().unwrap() {
            model.remove(cur.len() - 1);
            cur.pop();
        }
        let mut front: Vec<(usize, PageView)> = Vec::new();
        for (pos, &idx) in new_rows.iter().enumerate() {
            if idx < cur[0] {
                front.push((idx, items[pos].clone().unwrap_or_default()));
            }
        }
        for (idx, item) in front.into_iter().rev() {
            model.insert(0, item);
            cur.insert(0, idx);
        }
        for (pos, &idx) in new_rows.iter().enumerate() {
            if idx > *cur.last().unwrap() {
                model.push(items[pos].clone().unwrap_or_default());
                cur.push(idx);
            } else if let Some(item) = &items[pos] {
                if model.row_data(pos).map(|r| r.index) == Some(idx as i32) {
                    model.set_row_data(pos, item.clone());
                }
            }
        }
    }

    fn on_page(&self, doc_id: u64, index: usize, scale: f32, buf: PixelBuf) {
        trace::mark("첫 페이지 도착(UI)");
        let mut clear_pen = false;
        {
            let mut st = self.st.borrow_mut();
            if doc_id != st.doc_id || index >= st.sizes.len() {
                return;
            }
            st.render_ver += 1;
            let ver = st.render_ver;
            st.cache.insert(index, (Image::from_rgb8(buf), scale, ver));
            st.last_want.retain(|i| *i != index);
            if st.pen_clear_on_render == Some(index) {
                st.pen_clear_on_render = None;
                clear_pen = true;
            }
        }
        if clear_pen {
            if let Some(ui) = self.ui() {
                ui.set_pen_page(-1);
                ui.set_pen_path("".into());
            }
        }
        // 시작할 때 연 문서는 창이 만들어지기 전에 열려서 표식을 못 달았을 수 있다 → 창이 생긴 지금 단다
        if self.doc_claim.borrow().is_none() {
            let path = self.st.borrow().path.clone();
            if !path.is_empty() {
                self.claim_document(&path);
            }
        }
        self.refresh_view();
    }

    fn scroll_to(&self, top: f32) {
        let Some(ui) = self.ui() else { return };
        let max_top = (self.st.borrow().content_h - ui.get_view_h()).max(0.0);
        ui.set_scroll_y(-top.clamp(0.0, max_top));
        self.refresh_view();
    }

    pub fn goto_page(&self, index: usize) {
        let top = {
            let st = self.st.borrow();
            if st.ys.is_empty() {
                return;
            }
            st.ys[index.min(st.ys.len() - 1)] - PAGE_GAP / 2.0
        };
        self.scroll_to(top);
    }

    // ------------------------------------------------------------ 썸네일
    fn refresh_thumbs(&self) {
        let Some(ui) = self.ui() else { return };
        if !ui.get_sidebar_visible() {
            return;
        }
        let top = -ui.get_thumbs_scroll_y();
        let view_h = ui.get_thumbs_view_h().max(1.0);
        let device_scale = ui.window().scale_factor().max(0.5);
        let mut request = None;
        let mut rows = None;
        {
            let mut st = self.st.borrow_mut();
            if st.thumb_ys.is_empty() {
                return;
            }
            let count = st.thumb_ys.len();
            let first = page_at(&st.thumb_ys, top).saturating_sub(2);
            let last = (page_at(&st.thumb_ys, top + view_h) + 2).min(count - 1);

            if st.thumb_cache.len() > THUMB_CACHE_MAX {
                let (lo, hi) = (first.saturating_sub(60), last + 60);
                st.thumb_cache.retain(|i, _| *i >= lo && *i <= hi);
                st.thumb_requested.retain(|i| *i >= lo && *i <= hi);
            }
            let missing: Vec<usize> = (first..=last).filter(|i| !st.thumb_requested.contains(i)).collect();
            if !missing.is_empty() {
                // 요청 목록은 통째로 대체되므로, 아직 안 온 것도 함께 다시 보낸다
                let pending: Vec<usize> = (first..=last)
                    .filter(|i| !st.thumb_cache.contains_key(i) || st.thumb_stale.contains(i))
                    .collect();
                for i in &pending {
                    st.thumb_requested.insert(*i);
                }
                request = Some(Req::Thumbs { doc_id: st.doc_id, pages: pending, width_px: THUMB_W * device_scale });
            }
            let sig = (first, last, st.thumb_ver);
            if sig != st.thumb_sig {
                st.thumb_sig = sig;
                rows = Some(
                    (first..=last)
                        .map(|i| ThumbView {
                            index: i as i32,
                            y: st.thumb_ys[i],
                            w: st.thumb_sizes[i].0,
                            h: st.thumb_sizes[i].1,
                            image: st.thumb_cache.get(&i).cloned().unwrap_or_default(),
                            ready: st.thumb_cache.contains_key(&i),
                        })
                        .collect::<Vec<_>>(),
                );
            }
        }
        if let Some(rows) = rows {
            self.thumbs_model.set_vec(rows);
        }
        if let Some(req) = request {
            let _ = self.tx.send(req);
        }
    }

    fn on_thumb(&self, doc_id: u64, index: usize, buf: PixelBuf) {
        {
            let mut st = self.st.borrow_mut();
            if doc_id != st.doc_id {
                return;
            }
            st.thumb_cache.insert(index, Image::from_rgb8(buf));
            st.thumb_stale.remove(&index);
            st.thumb_ver += 1;
        }
        self.refresh_thumbs();
    }

    fn keep_thumb_visible(&self, page: usize) {
        let Some(ui) = self.ui() else { return };
        let st = self.st.borrow();
        let (Some(&y), Some(&(_, h))) = (st.thumb_ys.get(page), st.thumb_sizes.get(page)) else { return };
        let top = -ui.get_thumbs_scroll_y();
        let view_h = ui.get_thumbs_view_h();
        let row_h = h + THUMB_ROW_EXTRA;
        let max_top = (st.thumbs_content_h - view_h).max(0.0);
        if y < top {
            ui.set_thumbs_scroll_y(-(y - 6.0).clamp(0.0, max_top));
        } else if y + row_h > top + view_h {
            ui.set_thumbs_scroll_y(-(y + row_h - view_h + 6.0).clamp(0.0, max_top));
        }
    }

    // ------------------------------------------------------------ 검색
    pub fn start_search(&self, query: &str) {
        self.run_search(query, false);
    }

    /// quiet이면 결과가 와도 화면을 옮기지 않는다 (편집 뒤 강조 표시만 새로 고칠 때)
    fn run_search(&self, query: &str, quiet: bool) {
        let query = query.trim().to_string();
        let msg = {
            let mut st = self.st.borrow_mut();
            if st.sizes.is_empty() {
                return;
            }
            st.search_gen += 1;
            st.search_query = query.clone();
            st.hits.clear();
            st.hit_order.clear();
            st.current_hit = None;
            st.hits_ver += 1;
            st.search_running = !query.is_empty();
            st.search_note.clear();
            st.search_quiet = quiet;
            Req::Search { doc_id: st.doc_id, gen: st.search_gen, query }
        };
        let _ = self.tx.send(msg);
        self.update_search_label();
        self.refresh_view();
    }

    fn on_hits(&self, doc_id: u64, gen: u64, index: usize, rects: Vec<[f32; 4]>) {
        let mut jump = false;
        {
            let mut st = self.st.borrow_mut();
            if doc_id != st.doc_id || gen != st.search_gen {
                return;
            }
            // 텍스트 검색 결과가 먼저 오고, 글자 인식 결과가 나중에 같은 쪽으로 더 올 수 있다.
            // 쪽 안의 번호는 뒤에 덧붙이기만 하므로, 지금 고른 결과(쪽, 번호)는 그대로 유효하다.
            let selected = st.current_hit.and_then(|c| st.hit_order.get(c).copied());
            st.hits.entry(index).or_default().extend(rects);
            let mut order: Vec<(usize, usize)> =
                st.hits.iter().flat_map(|(page, list)| (0..list.len()).map(move |n| (*page, n))).collect();
            order.sort_unstable();
            st.hit_order = order;
            st.current_hit = selected.and_then(|sel| st.hit_order.iter().position(|h| *h == sel));
            st.hits_ver += 1;
            // 지금 보고 있는 페이지 이후의 첫 결과로 이동
            if !st.search_quiet && st.current_hit.is_none() && index >= st.current_page {
                st.current_hit = st.hit_order.iter().position(|h| h.0 == index);
                jump = true;
            }
        }
        self.update_search_label();
        if jump {
            self.show_current_hit();
        } else {
            self.refresh_view();
        }
    }

    fn on_search_note(&self, doc_id: u64, gen: u64, note: String) {
        {
            let mut st = self.st.borrow_mut();
            if doc_id != st.doc_id || gen != st.search_gen {
                return;
            }
            st.search_note = note;
        }
        self.update_search_label();
    }

    fn on_search_done(&self, doc_id: u64, gen: u64) {
        let mut jump = false;
        {
            let mut st = self.st.borrow_mut();
            if doc_id != st.doc_id || gen != st.search_gen {
                return;
            }
            st.search_running = false;
            st.search_note.clear();
            if !st.search_quiet && st.current_hit.is_none() && !st.hit_order.is_empty() {
                st.current_hit = Some(0);
                st.hits_ver += 1;
                jump = true;
            }
        }
        self.update_search_label();
        if jump {
            self.show_current_hit();
        }
    }

    fn step_hit(&self, delta: i32) {
        {
            let mut st = self.st.borrow_mut();
            let total = st.hit_order.len() as i32;
            if total == 0 {
                return;
            }
            let cur = st.current_hit.map(|c| c as i32).unwrap_or(if delta > 0 { -1 } else { 0 });
            st.current_hit = Some((cur + delta).rem_euclid(total) as usize);
            st.hits_ver += 1;
        }
        self.update_search_label();
        self.show_current_hit();
    }

    fn show_current_hit(&self) {
        let Some(ui) = self.ui() else { return };
        let target = {
            let st = self.st.borrow();
            let Some((page, n)) = st.current_hit.and_then(|c| st.hit_order.get(c).copied()) else { return };
            let Some(rect) = st.hits.get(&page).and_then(|r| r.get(n)) else { return };
            let y = st.ys[page] + rect[1] * st.zoom;
            let top = -ui.get_scroll_y();
            let view_h = ui.get_view_h();
            // 이미 화면 안쪽에 있으면 스크롤하지 않는다
            if y >= top + 60.0 && y + rect[3] * st.zoom <= top + view_h - 80.0 {
                None
            } else {
                Some(y - view_h * 0.3)
            }
        };
        match target {
            Some(top) => self.scroll_to(top),
            None => self.refresh_view(),
        }
    }

    fn update_search_label(&self) {
        let Some(ui) = self.ui() else { return };
        let st = self.st.borrow();
        let total = st.hit_order.len();
        let label = if st.search_query.is_empty() {
            String::new()
        } else if total == 0 {
            if !st.search_running {
                "결과 없음".to_string()
            } else if st.search_note.is_empty() {
                "검색 중…".to_string()
            } else {
                st.search_note.clone()
            }
        } else {
            let cur = st.current_hit.map(|c| c + 1).unwrap_or(0);
            if !st.search_running {
                format!("{cur} / {total}")
            } else if st.search_note.is_empty() {
                format!("{cur} / {total}+")
            } else {
                format!("{cur} / {total}+ · {}", st.search_note)
            }
        };
        ui.set_search_label(label.into());
    }

    // ------------------------------------------------------------ 편집
    fn send_edit(&self, op: EditOp) {
        let doc_id = {
            let mut st = self.st.borrow_mut();
            if st.sizes.is_empty() {
                return;
            }
            st.pending_edits += 1;
            st.doc_id
        };
        let _ = self.tx.send(Req::Edit { doc_id, op });
    }

    /// 끌어서 지정한 영역(페이지 안 논리 픽셀)에 가리기 또는 형광펜을 적용
    pub fn edit_rect(&self, page: usize, tool: i32, x0: f32, y0: f32, x1: f32, y1: f32) {
        let rect = {
            let st = self.st.borrow();
            let Some(&(w_pt, h_pt)) = st.sizes.get(page) else { return };
            let zoom = st.zoom.max(0.01);
            if (x1 - x0).abs() < 3.0 || (y1 - y0).abs() < 3.0 {
                return; // 클릭만 한 경우
            }
            [
                (x0.min(x1) / zoom).clamp(0.0, w_pt),
                (y0.min(y1) / zoom).clamp(0.0, h_pt),
                (x0.max(x1) / zoom).clamp(0.0, w_pt),
                (y0.max(y1) / zoom).clamp(0.0, h_pt),
            ]
        };
        match tool {
            TOOL_WHITEOUT => self.send_edit(EditOp::Whiteout { page, rect }),
            TOOL_HIGHLIGHT => self.send_edit(EditOp::Highlight { page, rect }),
            TOOL_EDIT_TEXT => {
                // 영역 안의 기존 텍스트를 엔진에 물어본다 → on_text_found에서 입력창을 띄운다
                let doc_id = {
                    let mut st = self.st.borrow_mut();
                    st.pending_edits += 1;
                    st.doc_id
                };
                let _ = self.tx.send(Req::TextAt { doc_id, page, rect });
            }
            _ => {}
        }
    }

    pub fn pen_start(&self, page: usize, x: f32, y: f32) {
        self.st.borrow_mut().pen = Some((page, vec![(x, y)]));
        self.update_pen_preview();
    }

    pub fn pen_move(&self, x: f32, y: f32) {
        {
            let mut st = self.st.borrow_mut();
            let Some((_, points)) = st.pen.as_mut() else { return };
            if let Some(&(lx, ly)) = points.last() {
                if (x - lx).abs() + (y - ly).abs() < 1.5 {
                    return;
                }
            }
            points.push((x, y));
        }
        self.update_pen_preview();
    }

    pub fn pen_end(&self) {
        let stroke = {
            let mut st = self.st.borrow_mut();
            let zoom = st.zoom.max(0.01);
            match st.pen.take() {
                Some((page, points)) if points.len() >= 2 => {
                    // 다시 그려진 페이지가 도착할 때까지 미리보기를 남겨 깜빡임을 줄인다
                    st.pen_clear_on_render = Some(page);
                    Some((page, points.iter().map(|p| (p.0 / zoom, p.1 / zoom)).collect::<Vec<_>>()))
                }
                _ => None,
            }
        };
        match stroke {
            Some((page, points)) => self.send_edit(EditOp::Ink { page, points }),
            None => {
                if let Some(ui) = self.ui() {
                    ui.set_pen_page(-1);
                    ui.set_pen_path("".into());
                }
            }
        }
    }

    fn update_pen_preview(&self) {
        let Some(ui) = self.ui() else { return };
        let st = self.st.borrow();
        let Some((page, points)) = st.pen.as_ref() else { return };
        let mut path = String::with_capacity(points.len() * 14);
        for (i, (x, y)) in points.iter().enumerate() {
            path.push_str(if i == 0 { "M " } else { " L " });
            path.push_str(&format!("{x:.1} {y:.1}"));
        }
        if points.len() == 1 {
            path.push_str(&format!(" L {:.1} {:.1}", points[0].0 + 0.1, points[0].1));
        }
        ui.set_pen_page(*page as i32);
        ui.set_pen_path(path.into());
    }

    fn font_catalog(&self) -> Rc<fonts::FontCatalog> {
        if let Some(catalog) = self.fonts.borrow().as_ref() {
            return catalog.clone();
        }
        let catalog = Rc::new(fonts::FontCatalog::load());
        if let Some(ui) = self.ui() {
            let names: Vec<slint::SharedString> = catalog.families.iter().map(|f| f.as_str().into()).collect();
            ui.set_fonts(ModelRc::new(VecModel::from(names)));
        }
        *self.fonts.borrow_mut() = Some(catalog.clone());
        catalog
    }

    /// 서식 막대에서 고른 글꼴·크기·색
    fn current_text_style(&self) -> Option<TextStyle> {
        let ui = self.ui()?;
        let catalog = self.font_catalog();
        let family = ui.get_text_font().to_string();
        let bold = ui.get_text_bold();
        let face = catalog.resolve(&family, bold).or_else(|| catalog.resolve(fonts::DEFAULT_FAMILY, bold))?;
        let color = ui.get_text_color();
        Some(TextStyle {
            font_path: face.path.to_string_lossy().into_owned(),
            font_index: face.index,
            size: ui.get_text_pt().clamp(4.0, 200.0),
            color: [color.red() as f32 / 255.0, color.green() as f32 / 255.0, color.blue() as f32 / 255.0],
        })
    }

    /// 입력창에서 Enter를 눌렀을 때. replacing이면 드래그했던 기존 텍스트를 덮고 그 자리에 쓴다.
    /// (x, y)는 클릭한 위치(페이지 안 논리 픽셀)로, 새로 추가할 때만 쓴다.
    pub fn commit_text(&self, page: usize, x: f32, y: f32, text: &str, replacing: bool) {
        let text = text.trim_end().to_string();
        let replace = self.st.borrow_mut().replace.take().filter(|r| replacing && r.page == page);
        if text.trim().is_empty() && replace.is_none() {
            return;
        }
        let Some(style) = self.current_text_style() else {
            self.toast("사용할 수 있는 글꼴을 찾지 못했습니다");
            return;
        };
        let zoom = self.st.borrow().zoom.max(0.01);
        let op = match replace {
            Some(ctx) => {
                let (bx, by, baseline) = match ctx.baseline {
                    Some((bx, by)) => (bx, by, true),
                    None => (ctx.rect[0], ctx.rect[1], false),
                };
                EditOp::Text { page, x: bx, y: by, baseline, text, style, lineheight: ctx.lineheight, cover: Some(ctx.rect) }
            }
            None => EditOp::Text { page, x: x / zoom, y: y / zoom, baseline: false, text, style, lineheight: 1.2, cover: None },
        };
        self.send_edit(op);
    }

    /// 드래그한 영역의 기존 텍스트를 읽어 왔을 때: 입력창에 채우고 서식 막대를 기존 서식에 맞춘다
    fn on_text_found(&self, doc_id: u64, page: usize, rect: [f32; 4], info: TextInfo) {
        let Some(ui) = self.ui() else { return };
        let zoom = {
            let mut st = self.st.borrow_mut();
            if doc_id != st.doc_id {
                return;
            }
            st.pending_edits = st.pending_edits.saturating_sub(1);
            st.replace = Some(ReplaceCtx { page, rect, baseline: info.baseline, lineheight: info.lineheight });
            st.zoom.max(0.01)
        };
        if ui.get_tool() != TOOL_EDIT_TEXT {
            self.st.borrow_mut().replace = None;
            return;
        }
        if !info.text.is_empty() {
            ui.set_text_pt((info.size * 10.0).round() / 10.0);
            ui.set_text_bold(info.bold);
            ui.set_text_color(slint::Color::from_rgb_u8(
                (info.color[0] * 255.0).round() as u8,
                (info.color[1] * 255.0).round() as u8,
                (info.color[2] * 255.0).round() as u8,
            ));
            if let Some(family) = self.font_catalog().match_pdf_font(&info.font_name) {
                ui.set_text_font(family.into());
            }
        }
        ui.set_text_initial(info.text.into());
        ui.set_text_x(rect[0] * zoom);
        ui.set_text_y(rect[1] * zoom);
        ui.set_text_w((rect[2] - rect[0]) * zoom);
        ui.set_text_h((rect[3] - rect[1]) * zoom);
        ui.set_text_replacing(true);
        ui.set_text_page(page as i32);
    }

    pub fn undo(&self) {
        let doc_id = {
            let mut st = self.st.borrow_mut();
            if !st.can_undo {
                return;
            }
            st.pending_edits += 1;
            st.doc_id
        };
        let _ = self.tx.send(Req::Undo { doc_id });
    }

    /// path가 None이면 열어 둔 파일에 저장
    pub fn save(&self, path: Option<String>) {
        self.save_with(path, false);
    }

    /// 암호를 풀어서 path에 저장 (자동 점검에서도 쓴다)
    pub fn save_unlocked_to(&self, path: String) {
        self.save_with(Some(path), true);
    }

    /// 정보 창의 [암호 없이 저장]: 저장 위치를 묻고 암호를 푼 사본을 만든다
    fn save_unlocked_from_ui(&self) {
        let current = std::path::PathBuf::from(self.st.borrow().path.clone());
        let stem = current.file_stem().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| "문서".into());
        let mut dialog = rfd::FileDialog::new().add_filter("PDF 문서", &["pdf"]).set_title("암호 없이 저장").set_file_name(format!("{stem}_암호해제.pdf"));
        if let Some(dir) = current.parent() {
            dialog = dialog.set_directory(dir);
        }
        if let Some(path) = dialog.save_file() {
            let mut path = path.to_string_lossy().into_owned();
            if !path.to_lowercase().ends_with(".pdf") {
                path.push_str(".pdf");
            }
            if let Some(ui) = self.ui() {
                ui.set_info_open(false);
            }
            self.save_unlocked_to(path);
        }
    }

    fn save_with(&self, path: Option<String>, remove_password: bool) {
        let doc_id = {
            let mut st = self.st.borrow_mut();
            if st.sizes.is_empty() || st.saving {
                return;
            }
            st.saving = true;
            st.last_saved = None;
            st.doc_id
        };
        let _ = self.tx.send(Req::Save { doc_id, path, remove_password });
    }

    fn save_as(&self) {
        let current = self.st.borrow().path.clone();
        let current = std::path::Path::new(&current);
        let mut dialog = rfd::FileDialog::new().add_filter("PDF 문서", &["pdf"]).set_title("다른 이름으로 저장");
        if let Some(dir) = current.parent() {
            dialog = dialog.set_directory(dir);
        }
        if let Some(name) = current.file_name() {
            dialog = dialog.set_file_name(name.to_string_lossy());
        }
        if let Some(path) = dialog.save_file() {
            let mut path = path.to_string_lossy().into_owned();
            if !path.to_lowercase().ends_with(".pdf") {
                path.push_str(".pdf");
            }
            self.save(Some(path));
        }
    }

    fn on_changed(&self, doc_id: u64, page: Option<usize>, can_undo: bool, dirty: bool) {
        let Some(ui) = self.ui() else { return };
        let requery = {
            let mut st = self.st.borrow_mut();
            if doc_id != st.doc_id {
                return;
            }
            st.can_undo = can_undo;
            st.dirty = dirty;
            st.pending_edits = st.pending_edits.saturating_sub(1);
            // 바뀐 페이지는 '오래된 그림'으로 표시: 새 그림이 올 때까지는 그대로 보여 준다
            match page {
                Some(i) => {
                    if let Some(entry) = st.cache.get_mut(&i) {
                        entry.1 = -1.0;
                    }
                    st.thumb_stale.insert(i);
                    st.thumb_requested.remove(&i);
                }
                None => {
                    for entry in st.cache.values_mut() {
                        entry.1 = -1.0;
                    }
                    let cached: Vec<usize> = st.thumb_cache.keys().copied().collect();
                    st.thumb_stale.extend(cached);
                    st.thumb_requested.clear();
                }
            }
            st.last_want.clear();
            st.last_want_scale = -1.0;
            st.search_query.clone()
        };
        ui.set_can_undo(can_undo);
        ui.set_dirty(dirty);
        self.refresh_view();
        self.refresh_thumbs();
        if !requery.is_empty() {
            self.run_search(&requery, true);
        }
    }

    // ------------------------------------------------------------ 페이지 조작
    fn send_page_op(&self, op: PageOp) {
        let doc_id = {
            let mut st = self.st.borrow_mut();
            if st.sizes.is_empty() {
                return;
            }
            st.pending_edits += 1;
            st.doc_id
        };
        let _ = self.tx.send(Req::Pages { doc_id, op });
    }

    pub fn rotate_page(&self, page: usize, delta: i32) {
        self.send_page_op(PageOp::Rotate { page, delta });
    }

    /// to: 옮긴 뒤의 쪽 번호(0부터)
    pub fn move_page(&self, from: usize, to: usize) {
        let count = self.st.borrow().sizes.len();
        if count == 0 || from >= count {
            return;
        }
        let to = to.min(count - 1);
        if to != from {
            self.send_page_op(PageOp::Move { from, to });
        }
    }

    /// 우클릭 메뉴의 이동: where_ = -1 앞으로, 1 뒤로, -2 맨 앞으로, 2 맨 뒤로
    fn move_page_by(&self, page: usize, where_: i32) {
        let count = self.st.borrow().sizes.len();
        if count == 0 {
            return;
        }
        let to = match where_ {
            -1 => page.saturating_sub(1),
            1 => page + 1,
            -2 => 0,
            _ => count - 1,
        };
        self.move_page(page, to);
    }

    /// 확인 창 없이 바로 삭제 (자동 점검에서도 쓴다)
    pub fn delete_page(&self, page: usize) {
        self.send_page_op(PageOp::Delete { page });
    }

    fn ask_delete_page(&self, page: usize) {
        if self.st.borrow().sizes.len() <= 1 {
            self.toast("마지막 한 쪽은 삭제할 수 없습니다");
            return;
        }
        let answer = rfd::MessageDialog::new()
            .set_level(rfd::MessageLevel::Warning)
            .set_title("BossPDF")
            .set_description(format!("{}쪽을 삭제할까요?\n(Ctrl+Z로 되돌릴 수 있습니다)", page + 1))
            .set_buttons(rfd::MessageButtons::YesNo)
            .show();
        if matches!(answer, rfd::MessageDialogResult::Yes | rfd::MessageDialogResult::Ok) {
            self.delete_page(page);
        }
    }

    /// 썸네일을 끄는 중: content_y는 썸네일 목록 안의 세로 위치
    pub fn thumb_drag(&self, page: usize, content_y: f32) {
        let Some(ui) = self.ui() else { return };
        let line_y = {
            let mut st = self.st.borrow_mut();
            let count = st.thumb_ys.len();
            if count == 0 {
                return;
            }
            // 가운데가 마우스보다 위에 있는 썸네일의 수 = 끼워 넣을 자리
            let slot = (0..count)
                .filter(|&i| st.thumb_ys[i] + (st.thumb_sizes[i].1 + THUMB_ROW_EXTRA) / 2.0 < content_y)
                .count();
            st.thumb_drag = Some((page, slot));
            if slot < count { st.thumb_ys[slot] - 2.0 } else { st.thumbs_content_h - 8.0 }
        };
        ui.set_thumb_drop_y(line_y);
    }

    pub fn thumb_drop(&self) {
        let drag = self.st.borrow_mut().thumb_drag.take();
        if let Some(ui) = self.ui() {
            ui.set_thumb_drop_y(-1.0);
        }
        if let Some((from, slot)) = drag {
            // 원래 자리보다 뒤로 가면, 자기 자신이 빠진 만큼 번호가 하나 당겨진다
            let to = if slot > from { slot - 1 } else { slot };
            self.move_page(from, to);
        }
    }

    fn on_restructured(&self, doc_id: u64, sizes: Vec<(f32, f32)>, focus: Option<usize>, can_undo: bool, dirty: bool) {
        let Some(ui) = self.ui() else { return };
        let anchor = self.top_anchor();
        let (count, thumbs_h, requery) = {
            let mut st = self.st.borrow_mut();
            if doc_id != st.doc_id {
                return;
            }
            st.pending_edits = st.pending_edits.saturating_sub(1);
            st.can_undo = can_undo;
            st.dirty = dirty;
            st.sizes = sizes;
            layout_thumbs(&mut st);
            // 쪽 번호가 달라졌을 수 있으므로 그려 둔 그림은 모두 버린다
            st.cache.clear();
            st.thumb_cache.clear();
            st.thumb_requested.clear();
            st.thumb_stale.clear();
            st.thumb_ver += 1;
            st.hits.clear();
            st.hit_order.clear();
            st.current_hit = None;
            st.hits_ver += 1;
            st.last_want.clear();
            st.last_want_scale = -1.0;
            st.replace = None;
            st.thumb_drag = None;
            st.pen = None;
            st.pen_clear_on_render = None;
            (st.sizes.len(), st.thumbs_content_h, st.search_query.clone())
        };
        ui.set_can_undo(can_undo);
        ui.set_dirty(dirty);
        ui.set_page_count(count as i32);
        ui.set_thumbs_content_h(thumbs_h);
        ui.set_text_page(-1);
        ui.set_pen_page(-1);
        ui.set_pen_path("".into());
        ui.set_thumb_drop_y(-1.0);
        self.relayout(anchor);
        if let Some(page) = focus {
            self.goto_page(page);
            self.keep_thumb_visible(page);
        }
        self.refresh_thumbs();
        if !requery.is_empty() {
            self.run_search(&requery, true);
        }
    }

    // ------------------------------------------------------------ 내보내기
    /// 내보내기 창의 선택(전체/현재 쪽/직접 지정)을 쪽 번호 목록으로 바꾼다
    fn export_pages_from_ui(&self) -> Result<Vec<usize>, String> {
        let ui = self.ui().ok_or("창이 없습니다.")?;
        let st = self.st.borrow();
        let count = st.sizes.len();
        if count == 0 {
            return Err("열린 문서가 없습니다.".into());
        }
        match ui.get_export_range_mode() {
            0 => Ok((0..count).collect()),
            1 => Ok(vec![st.current_page.min(count - 1)]),
            _ => output::parse_page_ranges(ui.get_export_range().as_str(), count),
        }
    }

    /// 내보내기 창의 [내보내기] 버튼: 저장 위치를 물은 뒤 엔진에 맡긴다
    fn export_from_ui(&self) {
        let Some(ui) = self.ui() else { return };
        let pages = match self.export_pages_from_ui() {
            Ok(p) => p,
            Err(e) => {
                ui.set_export_error(e.into());
                return;
            }
        };
        ui.set_export_error("".into());
        let source = std::path::PathBuf::from(self.st.borrow().path.clone());
        let stem = source.file_stem().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| "문서".into());
        let dir = source.parent().map(|p| p.to_path_buf());
        let dpi = ui.get_export_dpi().clamp(36, 600) as u32;
        let jpg = ui.get_export_jpg();
        let with_dir = |dialog: rfd::FileDialog| match &dir {
            Some(d) => dialog.set_directory(d),
            None => dialog,
        };
        let kind = match ui.get_export_kind() {
            0 => {
                let picked = with_dir(rfd::FileDialog::new().add_filter("PDF 문서", &["pdf"]))
                    .set_title("내보낼 PDF 저장")
                    .set_file_name(format!("{stem}_추출.pdf"))
                    .save_file();
                let Some(path) = picked else { return };
                let mut path = path.to_string_lossy().into_owned();
                if !path.to_lowercase().ends_with(".pdf") {
                    path.push_str(".pdf");
                }
                if std::path::Path::new(&path) == source.as_path() {
                    ui.set_export_error("열어 둔 문서와 같은 파일로는 내보낼 수 없습니다.".into());
                    return;
                }
                output::ExportKind::Pdf { path }
            }
            1 => {
                let picked = with_dir(rfd::FileDialog::new()).set_title("이미지를 저장할 폴더 선택").pick_folder();
                let Some(folder) = picked else { return };
                output::ExportKind::Images { dir: folder.to_string_lossy().into_owned(), prefix: stem, jpg, dpi }
            }
            _ => {
                let (ext, label) = if jpg { ("jpg", "JPG 이미지") } else { ("png", "PNG 이미지") };
                let picked = with_dir(rfd::FileDialog::new().add_filter(label, &[ext]))
                    .set_title("이어 붙인 이미지 저장")
                    .set_file_name(format!("{stem}_이어붙임.{ext}"))
                    .save_file();
                let Some(path) = picked else { return };
                let mut path = path.to_string_lossy().into_owned();
                if !path.to_lowercase().ends_with(&format!(".{ext}")) {
                    path.push_str(&format!(".{ext}"));
                }
                output::ExportKind::Stitched { path, dpi, spacing: 10 }
            }
        };
        ui.set_export_open(false);
        self.export_with(pages, kind);
    }

    /// 저장 위치가 정해진 내보내기 (자동 점검에서도 쓴다)
    pub fn export_with(&self, pages: Vec<usize>, kind: output::ExportKind) {
        let doc_id = self.st.borrow().doc_id;
        self.pending_tasks.set(self.pending_tasks.get() + 1);
        self.toast("내보내는 중…");
        let _ = self.tx.send(Req::Export { doc_id, pages, kind });
    }

    // ------------------------------------------------------------ 자동 업데이트
    /// 새 버전이 있는지 뒤에서 확인한다. manual이면 결과가 없어도(최신이어도) 알려 준다.
    pub fn check_updates(&self, manual: bool) {
        if manual {
            self.toast("업데이트 확인 중…");
        }
        std::thread::spawn(move || {
            let result = updater::check();
            let _ = slint::invoke_from_event_loop(move || with_app(|app| app.on_update_checked(result, manual)));
        });
    }

    fn on_update_checked(&self, result: Result<Option<updater::UpdateInfo>, String>, manual: bool) {
        let Some(ui) = self.ui() else { return };
        match result {
            Ok(Some(info)) => {
                ui.set_update_version(info.version.as_str().into());
                ui.set_update_notes(info.notes.as_str().into());
                ui.set_update_status("".into());
                ui.set_update_busy(false);
                *self.update.borrow_mut() = Some(info);
                ui.set_info_open(false);
                ui.set_update_open(true);
            }
            Ok(None) => {
                if manual {
                    self.toast(&format!("최신 버전입니다 (v{})", updater::VERSION));
                }
            }
            Err(message) => {
                if manual {
                    self.toast(&message);
                }
            }
        }
    }

    /// 업데이트 창의 [업데이트]: 설치 파일을 받아 실행하고 앱을 끝낸다
    fn start_update(&self) {
        let Some(ui) = self.ui() else { return };
        if self.st.borrow().dirty {
            ui.set_update_status("저장하지 않은 변경 사항이 있습니다. 먼저 저장한 뒤 다시 눌러 주세요.".into());
            return;
        }
        // 이미 받아 둔 설치 파일이 있으면 바로 실행
        if let Some(path) = self.update_installer.borrow().clone() {
            self.run_installer(&path);
            return;
        }
        let Some(info) = self.update.borrow().clone() else { return };
        ui.set_update_busy(true);
        ui.set_update_status("설치 파일을 내려받는 중…".into());
        std::thread::spawn(move || {
            let result = updater::download(&info);
            let _ = slint::invoke_from_event_loop(move || with_app(|app| app.on_update_downloaded(result)));
        });
    }

    fn on_update_downloaded(&self, result: Result<String, String>) {
        let Some(ui) = self.ui() else { return };
        ui.set_update_busy(false);
        match result {
            Ok(path) => {
                *self.update_installer.borrow_mut() = Some(path.clone());
                if self.st.borrow().dirty {
                    ui.set_update_status("내려받았습니다. 저장한 뒤 [업데이트]를 다시 눌러 주세요.".into());
                } else {
                    self.run_installer(&path);
                }
            }
            Err(message) => ui.set_update_status(message.into()),
        }
    }

    fn run_installer(&self, path: &str) {
        match updater::launch_installer(path) {
            Ok(()) => {
                // 설치 프로그램이 파일을 바꿀 수 있게 앱을 끝낸다
                self.save_settings();
                let _ = slint::quit_event_loop();
            }
            Err(message) => {
                if let Some(ui) = self.ui() {
                    ui.set_update_status(message.into());
                }
            }
        }
    }

    // ------------------------------------------------------------ 설정 기억
    /// 지금의 테마·사이드바·창 크기와 위치를 설정 파일에 남긴다
    pub fn save_settings(&self) {
        if !self.persist_settings {
            return;
        }
        let Some(ui) = self.ui() else { return };
        let window = ui.window();
        let maximized = window.is_maximized();
        let previous = settings::load();
        let scale = window.scale_factor().max(0.5);
        let size = window.size();
        let position = window.position();
        let current = settings::Settings {
            dark: ui.global::<Theme>().get_dark(),
            sidebar: ui.get_sidebar_visible(),
            // 최대화 중에는 "보통 크기"를 알 수 없으므로 전에 저장한 값을 유지한다
            size: if maximized || window.is_minimized() { previous.size } else { Some((size.width as f32 / scale, size.height as f32 / scale)) },
            position: if maximized || window.is_minimized() { previous.position } else { Some((position.x, position.y)) },
            maximized,
        };
        if current != previous {
            let _ = settings::save(&current);
        }
    }

    // ------------------------------------------------------------ 인쇄
    /// 이 창의 윈도우 핸들 (대화상자를 이 창 위에 띄우기 위함). 못 얻으면 0
    fn window_hwnd(&self) -> isize {
        use raw_window_handle::{HasWindowHandle, RawWindowHandle};
        let Some(ui) = self.ui() else { return 0 };
        let handle = ui.window().window_handle();
        match handle.window_handle().map(|h| h.as_raw()) {
            Ok(RawWindowHandle::Win32(win)) => win.hwnd.get(),
            _ => 0,
        }
    }

    fn doc_name(&self) -> String {
        let path = self.st.borrow().path.clone();
        std::path::Path::new(&path).file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| "BossPDF".into())
    }

    /// 인쇄 대화상자를 띄우고, [인쇄]를 누르면 엔진에 맡긴다
    fn print_from_ui(&self) {
        let count = self.st.borrow().sizes.len();
        if count == 0 {
            return;
        }
        let Some((hdc, pages, copies)) = print::ask_user(self.window_hwnd(), count) else { return };
        self.print_with(print::PrintJob { hdc, pages, copies, doc_name: self.doc_name(), output: None });
    }

    /// 대화상자 없이 이름으로 고른 프린터에 인쇄 (자동 점검에서 PDF 프린터로 시험할 때 쓴다)
    pub fn print_to_printer(&self, printer: &str, pages: Vec<usize>, output: Option<String>) -> bool {
        let Some(hdc) = print::open_printer(printer) else { return false };
        self.print_with(print::PrintJob { hdc, pages, copies: 1, doc_name: self.doc_name(), output });
        true
    }

    fn print_with(&self, job: print::PrintJob) {
        let doc_id = self.st.borrow().doc_id;
        self.pending_tasks.set(self.pending_tasks.get() + 1);
        self.toast("인쇄 준비 중…");
        let _ = self.tx.send(Req::Print { doc_id, job });
    }

    // ------------------------------------------------------------ 합치기
    fn refresh_merge_list(&self) {
        let Some(ui) = self.ui() else { return };
        let names: Vec<slint::SharedString> = self
            .merge_files
            .borrow()
            .iter()
            .map(|p| std::path::Path::new(p).file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| p.clone()).into())
            .collect();
        let count = names.len() as i32;
        ui.set_merge_files(ModelRc::new(VecModel::from(names)));
        // 시험용: 환경 변수로 지정한 파일에 현재 목록을 적는다
        if let Some(dump) = std::env::var_os("BOSSPDF_MERGE_DUMP") {
            let _ = std::fs::write(dump, self.merge_files.borrow().join("\n"));
        }
        if ui.get_merge_selected() >= count {
            ui.set_merge_selected(count - 1);
        }
    }

    /// 합치기 목록에 파일을 더한다 (PDF와 이미지만, 이미 있는 파일은 건너뜀)
    pub fn merge_add(&self, files: Vec<String>) {
        {
            let mut list = self.merge_files.borrow_mut();
            for file in files {
                let ok = file.to_lowercase().ends_with(".pdf") || output::is_image_file(&file);
                if ok && std::path::Path::new(&file).is_file() && !list.contains(&file) {
                    list.push(file);
                }
            }
        }
        self.refresh_merge_list();
    }

    fn merge_pick_files(&self) {
        let mut extensions = vec!["pdf"];
        extensions.extend_from_slice(output::IMAGE_EXTENSIONS);
        let picked = rfd::FileDialog::new().add_filter("PDF와 이미지", &extensions).set_title("합칠 파일 선택").pick_files();
        if let Some(files) = picked {
            self.merge_add(files.into_iter().map(|p| p.to_string_lossy().into_owned()).collect());
        }
    }

    fn merge_remove(&self, index: usize) {
        {
            let mut list = self.merge_files.borrow_mut();
            if index < list.len() {
                list.remove(index);
            }
        }
        self.refresh_merge_list();
    }

    fn merge_move(&self, index: usize, delta: i32) {
        let Some(ui) = self.ui() else { return };
        {
            let mut list = self.merge_files.borrow_mut();
            let target = index as i32 + delta;
            if index >= list.len() || target < 0 || target as usize >= list.len() {
                return;
            }
            list.swap(index, target as usize);
            ui.set_merge_selected(target);
        }
        self.refresh_merge_list();
    }

    fn merge_options_from_ui(&self) -> output::MergeOptions {
        let (fit_a4, margin_index) = self.ui().map(|ui| (ui.get_merge_fit_a4(), ui.get_merge_margin())).unwrap_or((true, 2));
        let margin = [0.0, 10.0, 20.0, 36.0][margin_index.clamp(0, 3) as usize];
        output::MergeOptions { fit_a4, margin }
    }

    /// 탐색기에서 여러 파일을 골라 합치기를 누르면 파일마다 프로세스가 따로 뜬다.
    /// 이 창(주 프로세스)이 대기열을 계속 살펴서 늦게 도착한 파일도 목록에 넣는다.
    pub fn start_merge_polling(self: &Rc<Self>) {
        let weak = Rc::downgrade(self);
        self.merge_poll.start(slint::TimerMode::Repeated, std::time::Duration::from_millis(300), move || {
            let Some(app) = weak.upgrade() else { return };
            let late = shell::drain_merge_queue();
            if late.is_empty() {
                return;
            }
            let mut late = late;
            late.sort_by_key(|f| shell::natural_key(f));
            app.merge_add(late);
            if let Some(ui) = app.ui() {
                ui.set_merge_open(true);
            }
            shell::bring_to_front(app.window_hwnd());
        });
    }

    /// 합치기 창의 [합치기] 버튼
    fn merge_from_ui(&self) {
        let Some(ui) = self.ui() else { return };
        let files = self.merge_files.borrow().clone();
        if files.is_empty() {
            return;
        }
        let first = std::path::PathBuf::from(&files[0]);
        let stem = first.file_stem().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| "문서".into());
        let mut dialog = rfd::FileDialog::new().add_filter("PDF 문서", &["pdf"]).set_title("합친 PDF 저장").set_file_name(format!("{stem}_합본.pdf"));
        if let Some(dir) = first.parent() {
            dialog = dialog.set_directory(dir);
        }
        let Some(path) = dialog.save_file() else { return };
        let mut out = path.to_string_lossy().into_owned();
        if !out.to_lowercase().ends_with(".pdf") {
            out.push_str(".pdf");
        }
        if files.iter().any(|f| std::path::Path::new(f) == std::path::Path::new(&out)) {
            ui.set_merge_error("합칠 파일 중 하나와 같은 이름으로는 저장할 수 없습니다.".into());
            return;
        }
        ui.set_merge_error("".into());
        ui.set_merge_open(false);
        self.merge_with(files, out, self.merge_options_from_ui());
    }

    /// 저장 위치가 정해진 합치기 (자동 점검에서도 쓴다)
    pub fn merge_with(&self, files: Vec<String>, out: String, options: output::MergeOptions) {
        self.pending_tasks.set(self.pending_tasks.get() + 1);
        self.toast("합치는 중…");
        let _ = self.tx.send(Req::Merge { files, out, options });
    }

    fn on_task_done(&self, result: Result<String, String>, open: Option<String>) {
        self.pending_tasks.set(self.pending_tasks.get().saturating_sub(1));
        match result {
            Ok(message) => {
                self.toast(&message);
                // 합친 결과는 바로 열어 보여 준다 (저장 안 한 변경이 있으면 먼저 묻는다)
                if let Some(path) = open {
                    self.merge_files.borrow_mut().clear();
                    self.refresh_merge_list();
                    if self.confirm_discard("합친 문서를 열까요?") {
                        self.open_path(path, None);
                    }
                }
            }
            Err(message) => self.toast(&format!("실패: {message}")),
        }
    }

    fn on_edit_failed(&self, doc_id: u64, message: String) {
        {
            let mut st = self.st.borrow_mut();
            if doc_id != st.doc_id {
                return;
            }
            st.pending_edits = st.pending_edits.saturating_sub(1);
            st.pen_clear_on_render = None;
        }
        if let Some(ui) = self.ui() {
            ui.set_pen_page(-1);
            ui.set_pen_path("".into());
        }
        self.toast(&message);
    }

    fn on_saved(&self, doc_id: u64, path: String, error: Option<String>) {
        let Some(ui) = self.ui() else { return };
        let quit = {
            let mut st = self.st.borrow_mut();
            if doc_id != st.doc_id {
                return;
            }
            st.saving = false;
            st.last_saved = Some(match &error {
                None => Ok(path.clone()),
                Some(e) => Err(e.clone()),
            });
            let quit = st.quit_after_save && error.is_none();
            st.quit_after_save = false;
            if error.is_none() {
                st.dirty = false;
                st.path = path.clone();
            }
            quit
        };
        match error {
            None => {
                let name = std::path::Path::new(&path).file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
                ui.set_dirty(false);
                ui.set_doc_title(name.into());
                self.claim_document(&path);
                self.toast("저장했습니다");
                if quit {
                    let _ = slint::quit_event_loop();
                }
            }
            Some(e) => self.toast(&format!("저장하지 못했습니다: {e}")),
        }
    }

    pub fn toast(&self, message: &str) {
        let Some(ui) = self.ui() else { return };
        ui.set_toast(message.into());
        let weak = self.ui.clone();
        self.toast_timer.start(slint::TimerMode::SingleShot, std::time::Duration::from_millis(2600), move || {
            if let Some(ui) = weak.upgrade() {
                ui.set_toast("".into());
            }
        });
    }

    /// 저장하지 않은 변경이 있으면 버려도 되는지 묻는다. 계속 진행해도 되면 true
    fn confirm_discard(&self, question: &str) -> bool {
        if !self.st.borrow().dirty {
            return true;
        }
        let answer = rfd::MessageDialog::new()
            .set_level(rfd::MessageLevel::Warning)
            .set_title("BossPDF")
            .set_description(format!("저장하지 않은 변경 사항이 있습니다.\n저장하지 않고 {question}"))
            .set_buttons(rfd::MessageButtons::OkCancel)
            .show();
        matches!(answer, rfd::MessageDialogResult::Ok | rfd::MessageDialogResult::Yes)
    }

    /// 창을 닫으려 할 때: 저장하지 않은 변경이 있으면 저장 여부를 묻는다
    fn on_close_requested(&self) -> slint::CloseRequestResponse {
        self.save_settings();
        if !self.st.borrow().dirty {
            return slint::CloseRequestResponse::HideWindow;
        }
        let answer = rfd::MessageDialog::new()
            .set_level(rfd::MessageLevel::Warning)
            .set_title("BossPDF")
            .set_description("저장하지 않은 변경 사항이 있습니다.\n닫기 전에 저장할까요?")
            .set_buttons(rfd::MessageButtons::YesNoCancel)
            .show();
        match answer {
            rfd::MessageDialogResult::Yes => {
                self.st.borrow_mut().quit_after_save = true;
                self.save(None);
                slint::CloseRequestResponse::KeepWindowShown
            }
            rfd::MessageDialogResult::No => slint::CloseRequestResponse::HideWindow,
            _ => slint::CloseRequestResponse::KeepWindowShown,
        }
    }
}

/// 페이지 크기 표로 썸네일 크기와 위치를 다시 계산한다
fn layout_thumbs(st: &mut State) {
    st.thumb_sizes.clear();
    st.thumb_ys.clear();
    let mut y = 6.0;
    for i in 0..st.sizes.len() {
        let (w, h) = st.sizes[i];
        let th = (THUMB_W * h / w).min(THUMB_MAX_H);
        let tw = th * w / h;
        st.thumb_sizes.push((tw.min(THUMB_W), th));
        st.thumb_ys.push(y);
        y += th + THUMB_ROW_EXTRA;
    }
    st.thumbs_content_h = y + 6.0;
}

/// y 좌표가 속한(또는 바로 위의) 항목 번호
fn page_at(ys: &[f32], y: f32) -> usize {
    match ys.binary_search_by(|v| v.partial_cmp(&y).unwrap_or(std::cmp::Ordering::Equal)) {
        Ok(i) => i,
        Err(0) => 0,
        Err(i) => i - 1,
    }
}

/// 엔진이 보낸 결과 대기열. 창이 만들어지기 전에 도착한 결과도 잃지 않도록 여기에 쌓아 둔다.
static EVENTS: Mutex<VecDeque<Evt>> = Mutex::new(VecDeque::new());

/// 엔진 스레드에서 호출: 결과를 쌓고 UI 스레드를 깨운다
fn dispatch(evt: Evt) {
    if let Ok(mut queue) = EVENTS.lock() {
        queue.push_back(evt);
    }
    let _ = slint::invoke_from_event_loop(drain_events);
}

/// UI 스레드에서 호출: 쌓인 결과를 순서대로 처리
fn drain_events() {
    with_app(|app| loop {
        let evt = EVENTS.lock().ok().and_then(|mut q| q.pop_front());
        let Some(evt) = evt else { break };
        match evt {
            Evt::Opened { doc_id, path, sizes, encrypted } => app.on_opened(doc_id, path, sizes, encrypted),
            Evt::NeedPassword { doc_id, wrong } => app.on_need_password(doc_id, wrong),
            Evt::OpenFailed { doc_id, message } => app.on_open_failed(doc_id, message),
            Evt::Page { doc_id, index, scale, buf } => app.on_page(doc_id, index, scale, buf),
            Evt::Thumb { doc_id, index, buf } => app.on_thumb(doc_id, index, buf),
            Evt::Hits { doc_id, gen, index, rects } => app.on_hits(doc_id, gen, index, rects),
            Evt::SearchDone { doc_id, gen } => app.on_search_done(doc_id, gen),
            Evt::SearchNote { doc_id, gen, note } => app.on_search_note(doc_id, gen, note),
            Evt::Changed { doc_id, page, can_undo, dirty } => app.on_changed(doc_id, page, can_undo, dirty),
            Evt::Restructured { doc_id, sizes, focus, can_undo, dirty } => {
                app.on_restructured(doc_id, sizes, focus, can_undo, dirty)
            }
            Evt::EditFailed { doc_id, message } => app.on_edit_failed(doc_id, message),
            Evt::TextFound { doc_id, page, rect, info } => app.on_text_found(doc_id, page, rect, info),
            Evt::Saved { doc_id, path, error, encrypted } => {
                if error.is_none() {
                    if let Some(ui) = app.ui() {
                        ui.set_doc_encrypted(encrypted);
                    }
                }
                app.on_saved(doc_id, path, error)
            }
            Evt::TaskDone { result, open } => app.on_task_done(result, open),
            Evt::Progress { message } => app.toast(&message),
        }
    });
}

fn main() -> Result<(), slint::PlatformError> {
    trace::init();
    // 1.x(파이썬 버전)의 우클릭 메뉴가 넘기던 인자도 그대로 받는다
    let args: Vec<String> = std::env::args()
        .skip(1)
        .filter(|a| a != "--new-process")
        .map(|a| if a == "--merge-pdfs" || a == "--merge-images" { "--merge".to_string() } else { a })
        .collect();
    let selftest_dir = args.iter().position(|a| a == "--selftest").and_then(|i| args.get(i + 1).cloned());
    let search_arg = args.iter().position(|a| a == "--search").and_then(|i| args.get(i + 1).cloned());
    let password_arg = args.iter().position(|a| a == "--password").and_then(|i| args.get(i + 1).cloned());
    // --merge 뒤에 오는 파일들은 합치기 창에 올린다
    let merge_args: Vec<String> = args
        .iter()
        .position(|a| a == "--merge")
        .map(|i| args[i + 1..].iter().take_while(|a| !a.starts_with("--")).cloned().collect())
        .unwrap_or_default();
    let has_merge = args.iter().any(|a| a == "--merge");

    // 우클릭 메뉴 등록/해제만 하고 끝내는 실행
    let flag_value = |name: &str| args.iter().position(|a| a == name).and_then(|i| args.get(i + 1).cloned());
    let quiet = args.iter().any(|a| a == "--quiet");
    let registry_base = flag_value("--registry-base").unwrap_or_else(|| shell::DEFAULT_REGISTRY_BASE.to_string());
    for (flag, registering) in [("--register", true), ("--unregister", false)] {
        if !args.iter().any(|a| a == flag) {
            continue;
        }
        let exe = std::env::current_exe().map(|p| p.to_string_lossy().into_owned()).unwrap_or_default();
        let result = if registering { shell::register(&registry_base, &exe) } else { shell::unregister(&registry_base) };
        if !quiet {
            let text = match (&result, registering) {
                (Ok(_), true) => "탐색기 우클릭 메뉴를 등록했습니다.\n\nPDF: BossPDF(Rust)로 열기 / 합치기\n이미지: BossPDF(Rust)로 합치기\n\n윈도우 11에서는 '추가 옵션 표시' 안에 나타납니다.".to_string(),
                (Ok(n), false) => format!("탐색기 우클릭 메뉴를 지웠습니다. (항목 {n}개)"),
                (Err(e), _) => format!("레지스트리를 바꾸지 못했습니다: {e}"),
            };
            rfd::MessageDialog::new().set_title("BossPDF").set_description(text).set_buttons(rfd::MessageButtons::Ok).show();
        }
        std::process::exit(if result.is_ok() { 0 } else { 1 });
    }

    // 합치기: 이미 합치기 창을 띄운 프로세스가 있으면 파일만 넘기고 끝낸다
    let merge_args = if has_merge {
        match shell::collect_merge(&merge_args) {
            Some(files) => files,
            None => return Ok(()),
        }
    } else {
        merge_args
    };
    // 합치기용 파일 인자는 "열 문서"로 착각하지 않게 인자 목록에서 뺀다
    let args: Vec<String> = match args.iter().position(|a| a == "--merge") {
        Some(i) => {
            let n = args[i + 1..].iter().take_while(|a| !a.starts_with("--")).count();
            args.iter().enumerate().filter(|(k, _)| *k < i || *k > i + n).map(|(_, a)| a.clone()).collect()
        }
        None => args,
    };
    let pdf_arg = args.iter().find(|a| a.to_lowercase().ends_with(".pdf")).cloned();
    // 같은 문서를 이미 열어 둔 창이 있으면 그 창을 앞으로 가져오고 끝낸다
    if let Some(path) = &pdf_arg {
        if selftest_dir.is_none() && !has_merge && shell::activate_existing(path) {
            return Ok(());
        }
    }

    fonts::install();
    let (tx, rx) = mpsc::channel::<Req>();
    std::thread::Builder::new()
        .name("pdf-engine".into())
        .stack_size(16 * 1024 * 1024)
        .spawn(move || engine::run(rx, dispatch))
        .expect("엔진 스레드를 시작할 수 없습니다");

    // 창을 만들기 전에 문서 열기부터 요청해 둔다 (창 준비와 문서 분석이 동시에 진행됨)
    trace::mark("엔진 스레드 시작");
    let mut initial = State::default();
    if let Some(path) = pdf_arg {
        initial.doc_id = 1;
        initial.pending_path = Some(path.clone());
        let _ = tx.send(Req::Open { doc_id: 1, path, password: password_arg });
    }
    let ui = AppWindow::new()?;
    trace::mark("창 생성");

    // 저장해 둔 설정 적용. 자동 점검은 늘 같은 조건에서 돌도록 기본값을 쓴다
    // (환경 변수로 설정 파일을 따로 지정했을 때는 자동 점검에서도 읽고 쓴다)
    let persist_settings = selftest_dir.is_none() || std::env::var_os("BOSSPDF_SETTINGS_FILE").is_some();
    if persist_settings {
        let saved = settings::load();
        ui.global::<Theme>().set_dark(saved.dark);
        ui.set_sidebar_visible(saved.sidebar);
        if let Some((w, h)) = saved.size {
            ui.window().set_size(slint::LogicalSize::new(w, h));
        }
        if let Some((x, y)) = saved.position {
            ui.window().set_position(slint::PhysicalPosition::new(x, y));
        }
        if saved.maximized {
            ui.window().set_maximized(true);
        }
    }
    ui.invoke_apply_theme();
    let app = Rc::new(App {
        ui: ui.as_weak(),
        tx,
        st: RefCell::new(initial),
        pages_model: Rc::new(VecModel::default()),
        thumbs_model: Rc::new(VecModel::default()),
        toast_timer: slint::Timer::default(),
        fonts: RefCell::new(None),
        merge_files: RefCell::new(Vec::new()),
        pending_tasks: std::cell::Cell::new(0),
        doc_claim: RefCell::new(None),
        merge_poll: slint::Timer::default(),
        persist_settings,
        update: RefCell::new(None),
        update_installer: RefCell::new(None),
    });
    ui.set_pages(ModelRc::from(app.pages_model.clone()));
    ui.set_thumbs(ModelRc::from(app.thumbs_model.clone()));
    APP.with(|a| *a.borrow_mut() = Some(app.clone()));

    ui.on_open_clicked(|| with_app(|app| app.pick_and_open()));
    ui.on_view_changed(|| with_app(|app| app.refresh_view()));
    ui.on_thumbs_view_changed(|| with_app(|app| app.refresh_thumbs()));
    ui.on_zoom_in(|| with_app(|app| app.zoom_by(ZOOM_STEP)));
    ui.on_zoom_out(|| with_app(|app| app.zoom_by(1.0 / ZOOM_STEP)));
    ui.on_zoom_fit(|| with_app(|app| app.set_zoom(None)));
    ui.on_search_edited(|text| with_app(|app| app.start_search(text.as_str())));
    ui.on_search_next(|| with_app(|app| app.step_hit(1)));
    ui.on_search_prev(|| with_app(|app| app.step_hit(-1)));
    ui.on_search_closed(|| with_app(|app| app.start_search("")));
    ui.on_goto_page(|text| {
        if let Ok(n) = text.trim().parse::<usize>() {
            with_app(|app| app.goto_page(n.saturating_sub(1)));
        }
    });
    ui.on_thumb_clicked(|index| with_app(|app| app.goto_page(index.max(0) as usize)));
    ui.on_password_submitted(|text| {
        with_app(|app| {
            let path = app.st.borrow().pending_path.clone();
            if let Some(path) = path {
                app.open_path(path, Some(text.to_string()));
            }
        })
    });
    ui.on_edit_rect(|page, x0, y0, x1, y1| {
        with_app(|app| {
            let tool = app.ui().map(|ui| ui.get_tool()).unwrap_or(0);
            app.edit_rect(page.max(0) as usize, tool, x0, y0, x1, y1);
        })
    });
    ui.on_pen_start(|page, x, y| with_app(|app| app.pen_start(page.max(0) as usize, x, y)));
    ui.on_pen_move(|x, y| with_app(|app| app.pen_move(x, y)));
    ui.on_pen_end(|| with_app(|app| app.pen_end()));
    ui.on_text_accepted(|page, x, y, text, replacing| {
        with_app(|app| app.commit_text(page.max(0) as usize, x, y, text.as_str(), replacing))
    });
    ui.on_need_fonts(|| with_app(|app| drop(app.font_catalog())));
    ui.on_page_rotate(|page, delta| with_app(|app| app.rotate_page(page.max(0) as usize, delta)));
    ui.on_page_move(|page, where_| with_app(|app| app.move_page_by(page.max(0) as usize, where_)));
    ui.on_page_delete(|page| with_app(|app| app.ask_delete_page(page.max(0) as usize)));
    ui.on_thumb_drag(|page, y| with_app(|app| app.thumb_drag(page.max(0) as usize, y)));
    ui.on_thumb_drop(|| with_app(|app| app.thumb_drop()));
    ui.on_print(|| with_app(|app| app.print_from_ui()));
    ui.on_export_run(|| with_app(|app| app.export_from_ui()));
    ui.on_merge_add(|| with_app(|app| app.merge_pick_files()));
    ui.on_merge_remove(|index| with_app(|app| app.merge_remove(index.max(0) as usize)));
    ui.on_merge_move(|index, delta| with_app(|app| app.merge_move(index.max(0) as usize, delta)));
    ui.on_merge_run(|| with_app(|app| app.merge_from_ui()));
    ui.on_settings_changed(|| with_app(|app| app.save_settings()));
    ui.set_app_version(updater::VERSION.into());
    ui.on_check_update(|| with_app(|app| app.check_updates(true)));
    ui.on_update_start(|| with_app(|app| app.start_update()));
    ui.on_save_unlocked(|| with_app(|app| app.save_unlocked_from_ui()));
    ui.on_undo(|| with_app(|app| app.undo()));
    ui.on_save(|| with_app(|app| app.save(None)));
    ui.on_save_as(|| with_app(|app| app.save_as()));
    ui.window().on_close_requested(|| {
        let app = APP.with(|a| a.borrow().clone());
        app.map(|app| app.on_close_requested()).unwrap_or_default()
    });
    ui.on_password_cancelled(|| {
        with_app(|app| {
            if let Some(ui) = app.ui() {
                ui.set_ask_password(false);
            }
        })
    });

    if has_merge {
        app.merge_add(merge_args);
        ui.set_merge_open(true);
        app.start_merge_polling();
    }

    // 시작하고 잠시 뒤에 새 버전이 있는지 조용히 확인한다 (자동 점검 중에는 하지 않음)
    let update_timer = slint::Timer::default();
    if selftest_dir.is_none() {
        update_timer.start(slint::TimerMode::SingleShot, std::time::Duration::from_millis(2500), || {
            with_app(|app| app.check_updates(false))
        });
    }

    let _selftest = selftest_dir.map(|dir| selftest::start(app.clone(), dir, search_arg.unwrap_or_default()));

    drain_events(); // 창을 만드는 동안 먼저 도착한 결과 처리
    trace::mark("이벤트 루프 진입");
    ui.run()
}
