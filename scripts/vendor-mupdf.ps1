# mupdf-sys / mupdf 0.8.0을 vendor 폴더로 복사하고 필요한 수정을 적용한다.
# (Cargo.toml의 [patch.crates-io]가 이 폴더들을 사용)
#
#  1. C 래퍼의 C23 빈 초기화 `{}` 5곳 → `{0}`  (이 PC의 MSVC 17.4가 못 읽음)
#  2. MSVC의 C 헤더에 없는 max_align_t 정의 추가
#  3. 글꼴 부분 포함 함수 pdf_subset_fonts를 쓸 수 있게 래퍼와 메서드 추가
#     (원본 패키지는 문서 포인터를 비공개로 두어 직접 호출할 수 없음)
#
# 사용: . .\env.ps1 ; cargo fetch ; .\scripts\vendor-mupdf.ps1
# 다시 만들려면 vendor 폴더를 지우고 실행한다.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Copy-Crate($name) {
    $src = Get-ChildItem "$env:CARGO_HOME\registry\src\*\$name-0.8.0" -Directory | Select-Object -First 1
    if (-not $src) { throw "$name-0.8.0 소스를 찾을 수 없습니다. 먼저 cargo fetch를 실행하세요." }
    $dst = Join-Path $root "vendor\$name"
    if (Test-Path $dst) { Write-Host "이미 있음: $dst"; return $null }
    New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
    Copy-Item $src.FullName $dst -Recurse
    return $dst
}

# ---------------------------------------------------------------- mupdf-sys
$sys = Copy-Crate 'mupdf-sys'
if ($sys) {
    $count = 0
    Get-ChildItem "$sys\wrapper\*.c" | ForEach-Object {
        $text = [IO.File]::ReadAllText($_.FullName)
        $fixed = $text.Replace(', {},', ', {0},')
        if ($fixed -ne $text) { [IO.File]::WriteAllText($_.FullName, $fixed, $utf8); $count++ }
    }

    [IO.File]::AppendAllText("$sys\src\lib.rs", @'

// [BossPDF 패치] MSVC의 C 헤더에는 max_align_t가 없어 bindgen이 만들어 주지 않는다.
// x64 MSVC의 malloc 정렬(16바이트)에 맞춰 직접 정의한다.
#[cfg(target_env = "msvc")]
#[allow(non_camel_case_types)]
#[repr(C, align(16))]
#[derive(Clone, Copy)]
pub struct max_align_t {
    _data: [u8; 16],
}
'@, $utf8)

    [IO.File]::AppendAllText("$sys\wrapper\pdf_document.c", @'

/* [BossPDF patch] Subset every embedded font to the glyphs actually used on the pages. */
void mupdf_pdf_subset_fonts(fz_context *ctx, pdf_document *pdf, mupdf_error_t **errptr)
{
    TRY_CATCH_VOID(pdf_subset_fonts(ctx, pdf, 0, NULL));
}
'@, $utf8)
    Write-Host "vendor\mupdf-sys 준비 완료 (고친 C 파일 ${count}개)"
}

# ---------------------------------------------------------------- mupdf
$hi = Copy-Crate 'mupdf'
if ($hi) {
    [IO.File]::AppendAllText("$hi\src\pdf\document.rs", @'

// [BossPDF 패치] 글꼴 부분 포함
impl PdfDocument {
    /// 문서에 들어 있는 글꼴을 실제로 쓰인 글자만 남기도록 줄인다 (MuPDF `pdf_subset_fonts`).
    /// 줄인 글꼴로는 새 글자를 더 쓸 수 없으므로, 저장 직전의 사본에만 쓴다.
    pub fn subset_fonts(&mut self) -> Result<(), Error> {
        unsafe { ffi_try!(mupdf_pdf_subset_fonts(context(), self.inner)) }
    }
}
'@, $utf8)
    Write-Host "vendor\mupdf 준비 완료"
}
