//! 개발용 자동 점검: `bosspdf.exe 문서.pdf --selftest <폴더> [--search 단어]`
//! 문서를 열고 → 가운데 페이지로 이동 → 검색 → 확대 → 편집(형광펜·가리기·텍스트·손글씨)
//! → 실행 취소 → 다른 이름으로 저장을 차례로 수행하면서 단계마다 창 화면을 PNG로 저장하고
//! 소요 시간을 report.txt에 남긴 뒤 종료한다.
//! 편집은 창에 마우스·키보드 이벤트를 직접 넣어서, 실제 입력과 같은 경로로 시험한다.
//! 원본 문서는 건드리지 않고 <폴더>/edited.pdf로만 저장한다.

use std::cell::RefCell;
use std::rc::Rc;
use std::time::{Duration, Instant};

use mupdf::{Colorspace, ImageFormat, Pixmap};
use slint::platform::{Key, PointerEventButton, WindowEvent};
use slint::{ComponentHandle, LogicalPosition, Model, SharedString, Timer, TimerMode};

use crate::App;

const RAIL_W: f32 = 46.0;
const SIDEBAR_W: f32 = 168.0;

struct Run {
    app: Rc<App>,
    dir: String,
    query: String,
    started: Instant,
    step: u32,
    step_started: Instant,
    settle_ticks: u32,
    report: Vec<String>,
}

pub fn start(app: Rc<App>, dir: String, query: String) -> Timer {
    let _ = std::fs::create_dir_all(&dir);
    let run = RefCell::new(Run {
        app,
        dir,
        query,
        started: Instant::now(),
        step: 0,
        step_started: Instant::now(),
        settle_ticks: 0,
        report: Vec::new(),
    });
    let timer = Timer::default();
    timer.start(TimerMode::Repeated, Duration::from_millis(50), move || tick(&mut run.borrow_mut()));
    timer
}

/// 화면이 안정됐는지: 문서가 열려 있고, 요청한 페이지가 모두 그려졌고, 검색·편집·저장이 끝났는지
fn settled(run: &Run) -> bool {
    let st = run.app.st.borrow();
    !st.sizes.is_empty()
        && st.pending_renders == 0
        && !st.search_running
        && !st.rows.is_empty()
        && st.pending_edits == 0
        && !st.saving
        && run.app.pending_tasks.get() == 0
}

fn snapshot(run: &Run, name: &str) -> String {
    let Some(ui) = run.app.ui() else { return "창 없음".into() };
    let buf = match ui.window().take_snapshot() {
        Ok(b) => b,
        Err(e) => return format!("스냅샷 실패: {e}"),
    };
    let (w, h) = (buf.width() as i32, buf.height() as i32);
    let saved = (|| -> Result<(), mupdf::Error> {
        let mut pixmap = Pixmap::new_with_w_h(&Colorspace::device_rgb(), w, h, true)?;
        let stride = pixmap.stride() as usize;
        let src = buf.as_bytes();
        let dst = pixmap.samples_mut();
        for row in 0..h as usize {
            let line = &src[row * w as usize * 4..(row + 1) * w as usize * 4];
            dst[row * stride..row * stride + line.len()].copy_from_slice(line);
        }
        pixmap.save_as(&format!("{}/{}.png", run.dir, name), ImageFormat::PNG)
    })();
    match saved {
        Ok(()) => format!("{name}.png ({w}x{h})"),
        Err(e) => format!("저장 실패: {e}"),
    }
}

/// 페이지 안의 비율 위치(fx, fy)를 창 좌표로 바꾼다
fn page_point(app: &App, page: usize, fx: f32, fy: f32) -> Option<LogicalPosition> {
    let ui = app.ui()?;
    let row = (0..app.pages_model.row_count()).filter_map(|i| app.pages_model.row_data(i)).find(|r| r.index == page as i32)?;
    let left = RAIL_W + if ui.get_sidebar_visible() { SIDEBAR_W } else { 0.0 };
    Some(LogicalPosition::new(
        left + row.x + ui.get_scroll_x() + row.w * fx,
        row.y + ui.get_scroll_y() + row.h * fy,
    ))
}

fn mouse_drag(app: &App, points: &[LogicalPosition]) {
    let Some(ui) = app.ui() else { return };
    let (Some(&first), Some(&last)) = (points.first(), points.last()) else { return };
    let window = ui.window();
    window.dispatch_event(WindowEvent::PointerMoved { position: first });
    window.dispatch_event(WindowEvent::PointerPressed { position: first, button: PointerEventButton::Left });
    for &position in &points[1..] {
        window.dispatch_event(WindowEvent::PointerMoved { position });
    }
    window.dispatch_event(WindowEvent::PointerReleased { position: last, button: PointerEventButton::Left });
}

fn type_text(app: &App, text: &str) {
    let Some(ui) = app.ui() else { return };
    let window = ui.window();
    for ch in text.chars() {
        let text: SharedString = ch.to_string().into();
        window.dispatch_event(WindowEvent::KeyPressed { text: text.clone() });
        window.dispatch_event(WindowEvent::KeyReleased { text });
    }
    let enter: SharedString = Key::Return.into();
    window.dispatch_event(WindowEvent::KeyPressed { text: enter.clone() });
    window.dispatch_event(WindowEvent::KeyReleased { text: enter });
}

fn tick(run: &mut Run) {
    if run.step == 0 && run.app.ui().map(|ui| ui.get_ask_password()).unwrap_or(false) {
        run.settle_ticks += 1;
        if run.settle_ticks >= 6 {
            let shot = snapshot(run, "0_password");
            run.report.push(format!("비밀번호 입력 창 표시됨 (화면: {shot})"));
            finish(run);
        }
        return;
    }
    // 안정 상태가 몇 틱 이어져야 다음 단계로 (화면에 실제로 그려질 시간을 준다)
    if settled(run) {
        run.settle_ticks += 1;
    } else {
        run.settle_ticks = 0;
        if run.step_started.elapsed() > Duration::from_secs(60) {
            run.report.push(format!("단계 {} 시간 초과", run.step));
            finish(run);
        }
        return;
    }
    if run.settle_ticks < 4 {
        return;
    }
    let step_ms = run.step_started.elapsed().as_millis().saturating_sub(200);
    let app = run.app.clone();
    let Some(ui) = app.ui() else {
        finish(run);
        return;
    };
    match run.step {
        0 => {
            let (pages, zoom) = {
                let st = app.st.borrow();
                (st.sizes.len(), st.zoom)
            };
            run.report.push(format!("열기: {pages}쪽 (자동 점검 시작 후 {}ms)", run.started.elapsed().as_millis().saturating_sub(200)));
            run.report.push(format!("시작 과정: {}", crate::trace::dump()));
            run.report.push(format!("배율: {:.0}%", zoom / crate::PX_PER_PT * 100.0));
            let shot = snapshot(run, "1_open");
            run.report.push(format!("화면: {shot}"));

            // 환경 변수로 고르는 짧은 시험들
            if std::env::var_os("BOSSPDF_UPDATE_CHECK").is_some() {
                let sample = r#"{"tag_name":"v9.9.9","body":"시험용","assets":[{"name":"notes.txt","size":1,"browser_download_url":"x"},{"name":"BossPDF_Setup_v9.9.9.exe","size":123,"browser_download_url":"https://github.com/cirross2/Bosspdf/releases/download/v9.9.9/BossPDF_Setup_v9.9.9.exe"}]}"#;
                run.report.push(format!("업데이트 해석(가짜 v9.9.9): {:?}", crate::updater::parse_release(sample, crate::updater::VERSION).map(|i| i.map(|i| (i.version, i.file_name, i.size)))));
                run.report.push(format!("업데이트 해석(같은 버전): {:?}", crate::updater::parse_release(&sample.replace("9.9.9", crate::updater::VERSION), crate::updater::VERSION).map(|i| i.is_some())));
                run.report.push(format!("버전 비교: 2.0.0>1.0.6 {}, 1.0.6>2.0.0 {}, 2.0.10>2.0.9 {}", crate::updater::is_newer("v2.0.0", "1.0.6"), crate::updater::is_newer("1.0.6", "2.0.0"), crate::updater::is_newer("2.0.10", "2.0.9")));
                run.report.push(format!("실제 서버 확인(현재 v{}): {:?}", crate::updater::VERSION, crate::updater::check().map(|i| i.map(|i| (i.version, i.file_name)))));
                // 내려받기 시험: 아주 낮은 버전인 척하고 지금 올라와 있는 설치 파일을 받아 본다 (실행은 하지 않음)
                if std::env::var_os("BOSSPDF_UPDATE_DOWNLOAD").is_some() {
                    let downloaded = crate::updater::check_against("0.0.1").and_then(|info| match info {
                        Some(info) => crate::updater::download(&info).map(|path| (info.version, info.size, path)),
                        None => Err("받을 릴리스가 없습니다".to_string()),
                    });
                    run.report.push(format!("내려받기: {downloaded:?}"));
                }
                ui.set_info_open(true);
                run.step = 90;
                run.step_started = Instant::now();
                run.settle_ticks = 0;
                return;
            }
            if let Some(out) = std::env::var_os("BOSSPDF_UNLOCK_TO") {
                run.report.push(format!("암호 문서 여부: {}", ui.get_doc_encrypted()));
                app.save_unlocked_to(out.to_string_lossy().into_owned());
                run.step = 91;
                run.step_started = Instant::now();
                run.settle_ticks = 0;
                return;
            }
            app.goto_page(pages / 2);
        }
        90 => {
            let shot = snapshot(run, "info_sheet");
            run.report.push(format!("정보 창: {shot}"));
            finish(run);
            return;
        }
        91 => {
            let saved = app.st.borrow().last_saved.clone();
            run.report.push(format!("암호 없이 저장: {saved:?}, 저장 뒤 암호 문서 여부: {}", ui.get_doc_encrypted()));
            finish(run);
            return;
        }
        1 => {
            let page = app.st.borrow().current_page;
            run.report.push(format!("이동: 현재 {}쪽, {step_ms}ms", page + 1));
            let shot = snapshot(run, "2_middle");
            run.report.push(format!("화면: {shot}"));
            if !run.query.is_empty() {
                ui.set_search_text(run.query.clone().into());
                ui.invoke_open_search();
                app.start_search(&run.query);
            }
        }
        2 => {
            let (total, pages_with_hits, current) = {
                let st = app.st.borrow();
                (st.hit_order.len(), st.hits.len(), st.current_hit.and_then(|c| st.hit_order.get(c).copied()))
            };
            run.report.push(format!(
                "검색 \"{}\": {total}건 ({pages_with_hits}쪽), 현재 결과 {:?}, {step_ms}ms",
                run.query,
                current.map(|(p, n)| (p + 1, n + 1))
            ));
            let shot = snapshot(run, "3_search");
            run.report.push(format!("화면: {shot}"));
            for _ in 0..3 {
                app.zoom_by(crate::ZOOM_STEP);
            }
        }
        3 => {
            let (zoom, page) = {
                let st = app.st.borrow();
                (st.zoom, st.current_page)
            };
            run.report.push(format!("확대: {:.0}%, 현재 {}쪽, {step_ms}ms", zoom / crate::PX_PER_PT * 100.0, page + 1));
            let shot = snapshot(run, "4_zoom");
            run.report.push(format!("화면: {shot}"));
            // 편집 시험 준비: 검색을 닫고 첫 페이지를 너비 맞춤으로
            app.start_search("");
            ui.set_search_visible(false);
            app.set_zoom(None);
            app.goto_page(0);
        }
        4 => {
            // 형광펜 → 가리기 → 텍스트 위치 클릭 (마우스 이벤트로)
            let drag = |a: (f32, f32), b: (f32, f32)| {
                if let (Some(p0), Some(p1)) = (page_point(&app, 0, a.0, a.1), page_point(&app, 0, b.0, b.1)) {
                    let mid = LogicalPosition::new((p0.x + p1.x) / 2.0, (p0.y + p1.y) / 2.0);
                    mouse_drag(&app, &[p0, mid, p1]);
                }
            };
            ui.set_tool(3);
            drag((0.10, 0.205), (0.62, 0.235));
            ui.set_tool(2);
            drag((0.10, 0.345), (0.45, 0.375));
            ui.set_tool(1);
            if let Some(p) = page_point(&app, 0, 0.12, 0.70) {
                mouse_drag(&app, &[p, p]);
            }
            run.report.push(format!("편집 입력 1: 형광펜·가리기 드래그, 텍스트 위치 클릭 (입력창 표시: {})", ui.get_text_page() == 0));
        }
        5 => {
            type_text(&app, "러스트 편집 OK 123");
            run.report.push("편집 입력 2: 텍스트 입력 후 Enter".to_string());
        }
        6 => {
            // 서식 바꿔 추가: 돋움(글꼴 모음의 3번째 글꼴) 20pt 굵게 파랑
            ui.set_text_font("돋움".into());
            ui.set_text_pt(20.0);
            ui.set_text_color(slint::Color::from_rgb_u8(0, 122, 255));
            if let Some(p) = page_point(&app, 0, 0.12, 0.78) {
                mouse_drag(&app, &[p, p]);
            }
            run.report.push(format!("편집 입력 3: 서식 변경(돋움 20pt 파랑) 후 위치 클릭 (글꼴 {}개 읽음)", ui.get_fonts().row_count()));
        }
        7 => {
            type_text(&app, "돋움 20pt 파랑 BLUE");
        }
        8 => {
            // 기존 텍스트 수정: 다섯째 줄을 드래그해서 읽어 온다
            ui.set_tool(5);
            if let (Some(p0), Some(p1)) = (page_point(&app, 0, 0.09, 0.300), page_point(&app, 0, 0.64, 0.333)) {
                let mid = LogicalPosition::new((p0.x + p1.x) / 2.0, (p0.y + p1.y) / 2.0);
                mouse_drag(&app, &[p0, mid, p1]);
            }
        }
        9 => {
            let st_replace = app.st.borrow().replace.as_ref().map(|r| (r.baseline, r.lineheight));
            run.report.push(format!(
                "텍스트 수정 준비: 읽은 내용 \"{}\", 서식 {} {}pt 굵게 {} 색 {:?}, 밑선 {:?}",
                ui.get_text_initial(),
                ui.get_text_font(),
                ui.get_text_pt(),
                ui.get_text_bold(),
                ui.get_text_color(),
                st_replace
            ));
            let shot = snapshot(run, "5a_editing");
            run.report.push(format!("화면: {shot}"));
            // 색만 빨강으로 바꾸고 내용을 새로 쓴다 (입력창은 전체 선택 상태라 그대로 덮어써진다)
            ui.set_text_color(slint::Color::from_rgb_u8(255, 59, 48));
            type_text(&app, "수정된 줄입니다 REPLACED");
        }
        10 => {
            // 손글씨: 물결 모양으로 그린다
            ui.set_tool(4);
            let points: Vec<LogicalPosition> = (0..=40)
                .filter_map(|i| {
                    let t = i as f32 / 40.0;
                    page_point(&app, 0, 0.15 + 0.5 * t, 0.56 + 0.025 * (t * 18.0).sin())
                })
                .collect();
            mouse_drag(&app, &points);
            run.report.push(format!("편집 입력 4: 손글씨 {}점", points.len()));
        }
        11 => {
            ui.set_tool(0);
            let (can_undo, dirty) = {
                let st = app.st.borrow();
                (st.can_undo, st.dirty)
            };
            run.report.push(format!("편집 적용됨: 실행 취소 가능 {can_undo}, 저장 필요 {dirty}, {step_ms}ms"));
            let shot = snapshot(run, "5_edit");
            run.report.push(format!("화면: {shot}"));
            app.undo(); // 마지막 편집(손글씨)을 되돌린다
        }
        12 => {
            run.report.push(format!("실행 취소(손글씨): {step_ms}ms"));
            let shot = snapshot(run, "6_undo");
            run.report.push(format!("화면: {shot}"));
            // BOSSPDF_SAVE_INPLACE가 있으면 연 파일에 덮어쓰기 저장을 시험한다 (반드시 사본으로 실행할 것)
            if std::env::var_os("BOSSPDF_SAVE_INPLACE").is_some() {
                app.save(None);
            } else {
                app.save(Some(format!("{}/edited.pdf", run.dir)));
            }
        }
        13 => {
            let (saved, dirty) = {
                let st = app.st.borrow();
                (st.last_saved.clone(), st.dirty)
            };
            run.report.push(match saved {
                Some(Ok(path)) => format!("저장: {path}, {step_ms}ms, 저장 필요 표시 {dirty}"),
                Some(Err(e)) => format!("저장 실패: {e}"),
                None => "저장 결과 없음".to_string(),
            });
            // 저장 뒤에 같은 글꼴로 처음 쓰는 글자를 더 넣는다 (저장 때 줄인 글꼴을 다시 쓰면 글자가 빠진다)
            ui.set_tool(1);
            ui.set_text_font("맑은 고딕".into());
            ui.set_text_pt(16.0);
            ui.set_text_color(slint::Color::from_rgb_u8(52, 199, 89));
            if let Some(p) = page_point(&app, 0, 0.12, 0.86) {
                mouse_drag(&app, &[p, p]);
            }
        }
        14 => {
            type_text(&app, "저장 뒤 추가: 꽃밭 햇볕 QWZ 789");
        }
        15 => {
            ui.set_tool(0);
            let shot = snapshot(run, "7_after_save_edit");
            run.report.push(format!("저장 뒤 추가 편집 화면: {shot}"));
            if std::env::var_os("BOSSPDF_SAVE_INPLACE").is_some() {
                app.save(None);
            } else {
                app.save(Some(format!("{}/edited2.pdf", run.dir)));
            }
        }
        16 => {
            let saved = app.st.borrow().last_saved.clone();
            run.report.push(match saved {
                Some(Ok(path)) => format!("두 번째 저장: {path}, {step_ms}ms"),
                Some(Err(e)) => format!("두 번째 저장 실패: {e}"),
                None => "두 번째 저장 결과 없음".to_string(),
            });
            // ---- 페이지 조작 시험: 2쪽을 시계 방향으로 돌린다
            app.rotate_page(1, 90);
        }
        17 => {
            let size = app.st.borrow().sizes.get(1).copied();
            run.report.push(format!("회전: 2쪽 크기 {size:?} (가로로 바뀌어야 함), {step_ms}ms"));
            // 돌린 쪽에 형광펜을 그어 좌표가 맞는지 본다 (왼쪽 위 1/4 영역)
            app.goto_page(1);
        }
        18 => {
            ui.set_tool(3);
            if let (Some(p0), Some(p1)) = (page_point(&app, 1, 0.10, 0.10), page_point(&app, 1, 0.40, 0.25)) {
                let mid = LogicalPosition::new((p0.x + p1.x) / 2.0, (p0.y + p1.y) / 2.0);
                mouse_drag(&app, &[p0, mid, p1]);
            }
            ui.set_tool(0);
        }
        19 => {
            let shot = snapshot(run, "8_rotated");
            run.report.push(format!("돌린 쪽에 형광펜: {shot}"));
            app.goto_page(0);
        }
        20 => {
            // 썸네일을 끌어서 1쪽을 3번째 자리로 옮긴다 (마우스 이벤트로)
            let (y0, h0, y2, h2) = {
                let st = app.st.borrow();
                (st.thumb_ys[0], st.thumb_sizes[0].1, st.thumb_ys[2], st.thumb_sizes[2].1)
            };
            let x = RAIL_W + 77.0;
            let scroll = ui.get_thumbs_scroll_y();
            let from = LogicalPosition::new(x, y0 + scroll + h0 / 2.0);
            let to_y = y2 + scroll + h2 + 20.0; // 3번째 썸네일의 아래쪽
            let points: Vec<LogicalPosition> =
                (0..=10).map(|i| LogicalPosition::new(x, from.y + (to_y - from.y) * i as f32 / 10.0)).collect();
            mouse_drag(&app, &points);
        }
        21 => {
            run.report.push(format!("끌어서 이동: 현재 {}쪽, {step_ms}ms", app.st.borrow().current_page + 1));
            let shot = snapshot(run, "9_moved");
            run.report.push(format!("화면: {shot}"));
            app.delete_page(5);
        }
        22 => {
            let count = app.st.borrow().sizes.len();
            run.report.push(format!("삭제: {count}쪽 남음, {step_ms}ms"));
            app.undo();
        }
        23 => {
            let count = app.st.borrow().sizes.len();
            run.report.push(format!("삭제 실행 취소: {count}쪽, {step_ms}ms"));
            if std::env::var_os("BOSSPDF_SAVE_INPLACE").is_some() {
                app.save(None);
            } else {
                app.save(Some(format!("{}/edited3.pdf", run.dir)));
            }
        }
        24 => {
            let saved = app.st.borrow().last_saved.clone();
            run.report.push(match saved {
                Some(Ok(path)) => format!("세 번째 저장: {path}, {step_ms}ms"),
                Some(Err(e)) => format!("세 번째 저장 실패: {e}"),
                None => "세 번째 저장 결과 없음".to_string(),
            });
            // ---- 내보내기 시험: 창 모양을 한 번 찍고, 1-3쪽과 10쪽을 새 PDF로
            ui.set_export_range_mode(2);
            ui.set_export_range("1-3, 10".into());
            ui.set_export_kind(2);
            ui.set_export_open(true);
        }
        25 => {
            let shot = snapshot(run, "10_export_sheet");
            run.report.push(format!("내보내기 창: {shot}"));
            ui.set_export_open(false);
            let count = app.st.borrow().sizes.len();
            match crate::output::parse_page_ranges("1-3, 10", count) {
                Ok(pages) => app.export_with(pages, crate::output::ExportKind::Pdf { path: format!("{}/export.pdf", run.dir) }),
                Err(e) => run.report.push(format!("쪽 범위 오류: {e}")),
            }
        }
        26 => {
            run.report.push(format!("내보내기(PDF): \"{}\", {step_ms}ms", ui.get_toast()));
            app.export_with(
                vec![0, 1],
                crate::output::ExportKind::Images { dir: format!("{}/images", run.dir), prefix: "쪽".into(), jpg: true, dpi: 100 },
            );
        }
        27 => {
            run.report.push(format!("내보내기(JPG 이미지): \"{}\", {step_ms}ms", ui.get_toast()));
            app.export_with(
                vec![0, 1, 2],
                crate::output::ExportKind::Stitched { path: format!("{}/stitched.png", run.dir), dpi: 100, spacing: 10 },
            );
        }
        28 => {
            run.report.push(format!("내보내기(이어 붙임): \"{}\", {step_ms}ms", ui.get_toast()));
            // ---- 인쇄 시험: 실제 프린터 대신 "Microsoft Print to PDF"로 파일에 인쇄한다
            // (1쪽은 돌려 둔 가로 쪽, 2·3쪽은 세로 쪽)
            let out = format!("{}\\printed.pdf", run.dir.replace('/', "\\"));
            let _ = std::fs::remove_file(&out);
            let started = app.print_to_printer("Microsoft Print to PDF", vec![0, 1, 2], Some(out));
            run.report.push(format!("인쇄 시작(PDF 프린터): {started}"));
        }
        29 => {
            run.report.push(format!("인쇄: \"{}\", {step_ms}ms", ui.get_toast()));
            // ---- 합치기 시험: 방금 만든 PDF + 이미지들 (환경 변수로 파일을 더 줄 수 있다)
            let mut files = vec![
                format!("{}/export.pdf", run.dir),
                format!("{}/1_open.png", run.dir),
                format!("{}/images/쪽_1.jpg", run.dir),
            ];
            if let Some(extra) = std::env::var_os("BOSSPDF_MERGE_EXTRA") {
                files.extend(extra.to_string_lossy().split(';').filter(|f| !f.is_empty()).map(String::from));
            }
            app.merge_add(files);
            ui.set_merge_selected(1);
            ui.set_merge_open(true);
        }
        30 => {
            let shot = snapshot(run, "11_merge_sheet");
            run.report.push(format!("합치기 창 ({}개 파일): {shot}", ui.get_merge_files().row_count()));
            ui.set_merge_open(false);
            let files = app.merge_files.borrow().clone();
            app.merge_with(files, format!("{}/merged.pdf", run.dir), crate::output::MergeOptions { fit_a4: true, margin: 20.0 });
        }
        31 => {
            let (pages, title) = (app.st.borrow().sizes.len(), ui.get_doc_title());
            run.report.push(format!("합치기: \"{}\", 합친 문서가 열림: {title} ({pages}쪽), {step_ms}ms", ui.get_toast()));
            let shot = snapshot(run, "12_merged");
            run.report.push(format!("화면: {shot}"));
            // ---- 테마: 창 크기를 바꾸고 다크 모드로 (설정 파일을 지정했으면 이 상태가 저장된다)
            ui.window().set_size(slint::LogicalSize::new(1000.0, 700.0));
        }
        32 => {
            ui.invoke_toggle_theme();
            ui.set_tool(1);
            ui.set_search_visible(true);
        }
        33 => {
            let shot = snapshot(run, "13_theme");
            let dark = ui.global::<crate::Theme>().get_dark();
            run.report.push(format!("테마 전환: 다크 {dark}, 화면 {shot}"));
            ui.set_tool(0);
            ui.set_export_open(true);
        }
        34 => {
            let shot = snapshot(run, "14_theme_sheet");
            run.report.push(format!("테마 전환 후 내보내기 창: {shot}"));
            ui.set_export_open(false);
            ui.invoke_toggle_theme();
            // ☰ 메뉴는 여기서 열지 않는다: 윈도우 기본 메뉴는 닫힐 때까지 프로그램을 붙잡아 두어 점검이 멈춘다.
            // (메뉴는 scripts\real-ui-test.ps1로 실제 화면에서 확인한다)
        }
        35 => {
            // ---- 툴팁: 레일 단추 위에 마우스를 올린다 (다음 단계까지의 0.2초 안에 떠야 한다)
            ui.window().dispatch_event(WindowEvent::PointerMoved { position: LogicalPosition::new(23.0, 207.0) });
        }
        36 => {
            let shot = snapshot(run, "16_tooltip");
            run.report.push(format!("툴팁({step_ms}ms 안에 표시): {shot}"));
            ui.window().dispatch_event(WindowEvent::PointerMoved { position: LogicalPosition::new(600.0, 400.0) });
            if std::env::var_os("BOSSPDF_BENCH").is_none() {
                finish(run);
                return;
            }
            // 큰 화면에서의 한 프레임 비용 측정 준비: 창을 3400x1380으로 키운다
            ui.window().set_size(slint::PhysicalSize::new(3400, 1380));
        }
        37 => {
            let size = ui.window().size();
            let mut times = Vec::new();
            for n in 0..24 {
                app.scroll_to(-ui.get_scroll_y() + 45.0 + n as f32);
                let t = Instant::now();
                if ui.window().take_snapshot().is_ok() {
                    times.push(t.elapsed().as_secs_f64() * 1000.0);
                }
            }
            times.sort_by(|a, b| a.partial_cmp(b).unwrap());
            let avg = times.iter().sum::<f64>() / times.len().max(1) as f64;
            run.report.push(format!(
                "프레임 비용({}x{}, 스크롤하며 전체 다시 그리기 {}회): 평균 {avg:.1}ms, 중앙값 {:.1}ms, 최대 {:.1}ms",
                size.width,
                size.height,
                times.len(),
                times.get(times.len() / 2).copied().unwrap_or(0.0),
                times.last().copied().unwrap_or(0.0)
            ));
            finish(run);
            return;
        }
        _ => {
            finish(run);
            return;
        }
    }
    run.step += 1;
    run.step_started = Instant::now();
    run.settle_ticks = 0;
}

fn finish(run: &mut Run) {
    let _ = std::fs::write(format!("{}/report.txt", run.dir), run.report.join("\n"));
    run.step = 99;
    let _ = slint::quit_event_loop();
}
