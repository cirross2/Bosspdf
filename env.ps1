# BossPDF 빌드 환경 (러스트 도구는 E:\다운로드\rust에 설치되어 있고 시스템 PATH에는 등록하지 않음)
# 사용: . .\env.ps1  →  cargo build --release
$env:RUSTUP_HOME = 'E:\다운로드\rust\rustup'
$env:CARGO_HOME = 'E:\다운로드\rust\cargo'
$env:LIBCLANG_PATH = 'E:\다운로드\rust\libclang\libclang-18.1.1.data\platlib\clang\native'
if ($env:PATH -notlike '*E:\다운로드\rust\cargo\bin*') { $env:PATH = "E:\다운로드\rust\cargo\bin;$env:PATH" }
