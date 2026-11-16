# 실제 화면에서 ☰ 메뉴와 툴팁을 확인한다: 앱을 띄우고, 진짜 마우스 입력으로 누르고, 화면을 캡처한다.
# (자동 점검의 창 스냅샷에는 윈도우 기본 메뉴가 찍히지 않기 때문)
param([string]$Exe, [string]$Pdf, [string]$OutDir)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class U32 {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
    [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    // 프로세스의 보이는 최상위 창 중 가장 큰 것
    public static IntPtr MainVisibleWindow(uint pid) {
        IntPtr best = IntPtr.Zero; long bestArea = 0;
        EnumWindows((h, l) => {
            uint p; GetWindowThreadProcessId(h, out p);
            if (p == pid && IsWindowVisible(h)) {
                RECT r; GetWindowRect(h, out r);
                long area = (long)(r.R - r.L) * (r.B - r.T);
                if (area > bestArea) { bestArea = area; best = h; }
            }
            return true;
        }, IntPtr.Zero);
        return bestArea > 40000 ? best : IntPtr.Zero;
    }
}
'@
[U32]::SetProcessDPIAware() | Out-Null
New-Item -ItemType Directory -Force $OutDir | Out-Null

function Capture($hwnd, $name) {
    $r = New-Object U32+RECT; [U32]::GetWindowRect($hwnd, [ref]$r) | Out-Null
    $w = $r.R - $r.L; $h = $r.B - $r.T
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size $w, $h))
    $g.Dispose(); $bmp.Save((Join-Path $OutDir $name)); $bmp.Dispose()
}
# 창 안의 논리 좌표(96dpi 기준)를 화면 좌표로
function ToScreen($hwnd, $x, $y) {
    $scale = [U32]::GetDpiForWindow($hwnd) / 96.0
    $p = New-Object U32+POINT; $p.X = [int]($x * $scale); $p.Y = [int]($y * $scale)
    [U32]::ClientToScreen($hwnd, [ref]$p) | Out-Null
    return $p
}

$saved = New-Object U32+POINT; [U32]::GetCursorPos([ref]$saved) | Out-Null
$env:BOSSPDF_SETTINGS_FILE = Join-Path $OutDir 'settings.ini'   # 사용자의 실제 설정을 건드리지 않는다
$proc = Start-Process $Exe -ArgumentList "`"$Pdf`"" -PassThru
try {
    $hwnd = [IntPtr]::Zero
    foreach ($i in 1..80) { Start-Sleep -Milliseconds 100; $hwnd = [U32]::MainVisibleWindow([uint32]$proc.Id); if ($hwnd -ne [IntPtr]::Zero) { break } }
    if ($hwnd -eq [IntPtr]::Zero) { throw '창을 찾지 못했습니다' }
    Start-Sleep -Milliseconds 1800
    [U32]::SetForegroundWindow($hwnd) | Out-Null; Start-Sleep -Milliseconds 300

    # 1) 툴팁: '페이지 내보내기' 단추 위에 마우스를 올린다 (조금 움직여 줘야 hover가 잡힌다)
    $p = ToScreen $hwnd 23 194
    [U32]::SetCursorPos($p.X - 3, $p.Y) | Out-Null; Start-Sleep -Milliseconds 60
    [U32]::SetCursorPos($p.X, $p.Y) | Out-Null
    Start-Sleep -Milliseconds 350
    Capture $hwnd 'real_tooltip.png'

    # 2) ☰ 메뉴: 단추를 누른다
    $p = ToScreen $hwnd 23 22
    [U32]::SetCursorPos($p.X - 2, $p.Y) | Out-Null; Start-Sleep -Milliseconds 60
    [U32]::SetCursorPos($p.X, $p.Y) | Out-Null; Start-Sleep -Milliseconds 120
    [U32]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 40
    [U32]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 600
    Capture $hwnd 'real_menu.png'

    # 3) '보기' 하위 메뉴 위로 마우스를 옮긴다 (메뉴 항목 높이를 모르므로 화면을 보고 판단)
    [System.Windows.Forms.SendKeys]::SendWait('{DOWN 9}{RIGHT}')
    Start-Sleep -Milliseconds 500
    Capture $hwnd 'real_submenu.png'
    [System.Windows.Forms.SendKeys]::SendWait('{ESC}{ESC}{ESC}')
    Start-Sleep -Milliseconds 300
    'captured'
} finally {
    [U32]::SetCursorPos($saved.X, $saved.Y) | Out-Null
    $proc.Refresh(); if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    Remove-Item Env:BOSSPDF_SETTINGS_FILE -ErrorAction SilentlyContinue
}
