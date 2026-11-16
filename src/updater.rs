//! 자동 업데이트: GitHub 릴리스에서 새 버전을 확인하고 설치 파일을 받아 실행한다.
//! 파이썬 버전과 같은 저장소·같은 규칙(릴리스의 Setup exe 자산)을 쓴다.
//! 네트워크는 윈도우 내장 HTTP(Windows.Web.Http)를 쓰고, 화면을 멈추지 않게 별도 스레드에서 돈다.

use windows::core::HSTRING;
use windows::Foundation::Uri;
use windows::Storage::Streams::DataReader;
use windows::Web::Http::HttpClient;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
const LATEST_RELEASE_URL: &str = "https://api.github.com/repos/cirross2/Bosspdf/releases/latest";

#[derive(Clone, Debug)]
pub struct UpdateInfo {
    pub version: String,
    pub notes: String,
    pub download_url: String,
    pub file_name: String,
    pub size: u64,
}

/// "v2.0.1" 같은 버전 문자열을 숫자 목록으로
fn parse_version(text: &str) -> Vec<u64> {
    text.trim()
        .trim_start_matches(['v', 'V'])
        .split('.')
        .map(|part| part.chars().take_while(|c| c.is_ascii_digit()).collect::<String>().parse().unwrap_or(0))
        .collect()
}

pub fn is_newer(latest: &str, current: &str) -> bool {
    let (mut a, mut b) = (parse_version(latest), parse_version(current));
    let len = a.len().max(b.len());
    a.resize(len, 0);
    b.resize(len, 0);
    a > b
}

fn client() -> windows::core::Result<HttpClient> {
    let client = HttpClient::new()?;
    // GitHub API는 User-Agent가 없으면 거절한다
    client.DefaultRequestHeaders()?.UserAgent()?.TryParseAdd(&HSTRING::from(format!("BossPDF/{VERSION}")))?;
    Ok(client)
}

/// 최신 릴리스 정보를 읽는다. 현재 버전보다 새 것이 있고 설치 파일이 붙어 있으면 Some
pub fn check() -> Result<Option<UpdateInfo>, String> {
    check_against(VERSION)
}

/// current 버전을 기준으로 확인한다 (시험할 때 낮은 버전을 넣어 내려받기까지 해 볼 수 있다)
pub fn check_against(current: &str) -> Result<Option<UpdateInfo>, String> {
    let text = (|| -> windows::core::Result<String> {
        let uri = Uri::CreateUri(&HSTRING::from(LATEST_RELEASE_URL))?;
        Ok(client()?.GetStringAsync(&uri)?.join()?.to_string())
    })()
    .map_err(|e| format!("업데이트 서버에 연결할 수 없습니다. ({})", e.message()))?;
    parse_release(&text, current)
}

/// GitHub 릴리스 JSON에서 새 버전 정보를 뽑는다 (시험하기 쉽게 네트워크와 분리)
pub fn parse_release(json: &str, current: &str) -> Result<Option<UpdateInfo>, String> {
    let data: serde_json::Value = serde_json::from_str(json).map_err(|e| format!("릴리스 정보를 읽을 수 없습니다. ({e})"))?;
    let tag = data["tag_name"].as_str().unwrap_or_default();
    if tag.is_empty() || !is_newer(tag, current) {
        return Ok(None);
    }
    let assets = data["assets"].as_array().cloned().unwrap_or_default();
    // 이름에 setup이나 bosspdf가 든 exe를 설치 파일로 본다
    let installer = assets.iter().find(|a| {
        let name = a["name"].as_str().unwrap_or_default().to_lowercase();
        name.ends_with(".exe") && (name.contains("setup") || name.contains("bosspdf"))
    });
    let Some(asset) = installer else { return Ok(None) };
    Ok(Some(UpdateInfo {
        version: tag.trim_start_matches(['v', 'V']).to_string(),
        notes: data["body"].as_str().unwrap_or_default().to_string(),
        download_url: asset["browser_download_url"].as_str().unwrap_or_default().to_string(),
        file_name: asset["name"].as_str().unwrap_or("BossPDF_Setup_Latest.exe").to_string(),
        size: asset["size"].as_u64().unwrap_or(0),
    }))
}

/// 설치 파일을 임시 폴더에 내려받고 그 경로를 돌려준다
pub fn download(info: &UpdateInfo) -> Result<String, String> {
    if !info.download_url.starts_with("https://github.com/") {
        return Err("알 수 없는 다운로드 주소입니다.".into());
    }
    let bytes = (|| -> windows::core::Result<Vec<u8>> {
        let uri = Uri::CreateUri(&HSTRING::from(info.download_url.as_str()))?;
        let buffer = client()?.GetBufferAsync(&uri)?.join()?;
        let mut bytes = vec![0u8; buffer.Length()? as usize];
        DataReader::FromBuffer(&buffer)?.ReadBytes(&mut bytes)?;
        Ok(bytes)
    })()
    .map_err(|e| format!("다운로드하지 못했습니다. ({})", e.message()))?;
    if info.size > 0 && bytes.len() as u64 != info.size {
        return Err(format!("내려받은 파일 크기가 다릅니다. ({} / {} 바이트)", bytes.len(), info.size));
    }
    // 실행 파일인지 최소한 확인한다 ("MZ"로 시작)
    if bytes.len() < 1024 || &bytes[..2] != b"MZ" {
        return Err("내려받은 파일이 설치 프로그램이 아닙니다.".into());
    }
    let name: String = info.file_name.chars().filter(|c| c.is_alphanumeric() || matches!(c, '.' | '_' | '-')).collect();
    let path = std::env::temp_dir().join(if name.to_lowercase().ends_with(".exe") { name } else { "BossPDF_Setup_Latest.exe".into() });
    std::fs::write(&path, &bytes).map_err(|e| format!("설치 파일을 저장하지 못했습니다. ({e})"))?;
    Ok(path.to_string_lossy().into_owned())
}

/// 설치 프로그램을 실행한다 (이 다음에 앱을 끝내야 설치가 파일을 바꿀 수 있다)
pub fn launch_installer(path: &str) -> Result<(), String> {
    std::process::Command::new(path).spawn().map(|_| ()).map_err(|e| format!("설치 프로그램을 실행하지 못했습니다. ({e})"))
}
