fn main() {
    // 실행 파일 아이콘과 버전 정보
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let mut res = winresource::WindowsResource::new();
        res.set_icon("assets/app_icon.ico");
        res.set("ProductName", "BossPDF");
        res.set("FileDescription", "BossPDF");
        res.compile().expect("아이콘 리소스 컴파일 실패");
    }
    // 애플 스타일(cupertino) 위젯으로 화면 정의를 컴파일 (-light/-dark를 붙이지 않아야 실행 중에 테마를 바꿀 수 있다)
    let config = slint_build::CompilerConfiguration::new().with_style("cupertino".into());
    slint_build::compile_with_config("ui/app.slint", config).expect("Slint 화면 컴파일 실패");
}
