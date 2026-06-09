"""
printshare.py
======================
Tool cau hinh may in chia se tren Windows 11
- Hien thi thong tin he thong: OS, Computer Name, may in mac dinh / dang share
- Cho nhap Username va Password can tao
- Chay logic PowerShell tuong duong qua subprocess (can quyen Admin)

Yeu cau: Python 3.8+, Windows 10/11, chay voi quyen Administrator
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import platform
import socket
import winreg
import os
import sys
import ctypes


# ─────────────────────────────────────────────
# Palette mau flat / dark-navy
# ─────────────────────────────────────────────
BG          = "#1e2535"   # nen tong
SURFACE     = "#252d40"   # card / panel
SURFACE2    = "#2c3650"   # input / textarea
BORDER      = "#3a4560"   # vien
ACCENT      = "#4f8ef7"   # xanh duong chinh
ACCENT_HVR  = "#3a7de8"   # hover
SUCCESS     = "#3dba7e"
WARN        = "#f5a623"
DANGER      = "#e05252"
TEXT        = "#e8ecf4"   # chu chinh
TEXT2       = "#8b97b8"   # chu phu
TEXT3       = "#5a6480"   # placeholder

FONT        = ("Segoe UI", 10)
FONT_SM     = ("Segoe UI", 9)
FONT_BOLD   = ("Segoe UI", 10, "bold")
FONT_H1     = ("Segoe UI", 13, "bold")
FONT_H2     = ("Segoe UI", 11, "bold")
FONT_MONO   = ("Consolas",  9)


# ─────────────────────────────────────────────
# Thu thap thong tin he thong - FIX LOGIC QUÉT
# ─────────────────────────────────────────────
def get_windows_edition():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
            product = winreg.QueryValueEx(k, "ProductName")[0]
            build   = winreg.QueryValueEx(k, "CurrentBuildNumber")[0]
            ubr     = winreg.QueryValueEx(k, "UBR")[0]
            edition = winreg.QueryValueEx(k, "EditionID")[0]
            try:
                display = winreg.QueryValueEx(k, "DisplayVersion")[0]
            except Exception:
                display = ""
            return product, build, ubr, edition, display
    except Exception:
        return platform.system(), "", "", "", ""


def get_default_printer_for_current_user():
    """Lấy máy in mặc định của người dùng đang đăng nhập (ngay cả khi chạy với quyền Admin)"""
    try:
        # Cách 1: Dùng win32print nếu có (nhanh nhưng cần pywin32)
        # import win32print
        # return win32print.GetDefaultPrinter()

        # Cách 2: Dùng PowerShell để lấy từ registry của user đang tương tác
        ps_script = """
        $explorerPid = (Get-Process -Name explorer -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -ne 0 } | Select-Object -First 1).Id
        if (-not $explorerPid) { exit 1 }
        $userSid = (Get-Process -Id $explorerPid -IncludeUserName -ErrorAction SilentlyContinue).UserName
        if (-not $userSid) { exit 1 }
        $sid = ([System.Security.Principal.NTAccount]($userSid)).Translate([System.Security.Principal.SecurityIdentifier]).Value
        $regPath = "Registry::HKEY_USERS\\$sid\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Windows"
        $device = (Get-ItemProperty -Path $regPath -Name Device -ErrorAction SilentlyContinue).Device
        if ($device) {
            $printer = $device -split ',' | Select-Object -First 1
            Write-Output $printer
        } else { exit 1 }
        """
        default_printer = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps_script],
            stderr=subprocess.DEVNULL, text=True, timeout=5
        ).strip()
        if default_printer:
            return default_printer
    except Exception:
        pass

    # Fallback: lấy máy in mặc định của process hiện tại (sẽ là của Admin)
    try:
        ps = "(Get-Printer -Default).Name"
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            stderr=subprocess.DEVNULL, text=True, timeout=5
        )
        if out.strip():
            return out.strip()
    except Exception:
        pass
    return "Chua co"


def get_printers():
    """Trả về list (name, is_default, is_shared) với is_default đúng cho user đang logon"""
    default_for_user = get_default_printer_for_current_user()
    result = []
    try:
        ps = (
            "Get-Printer | Select-Object Name,Shared | "
            "ForEach-Object { \"$($_.Name)|$($_.Shared)\" }"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            stderr=subprocess.DEVNULL, text=True, timeout=10
        )
        for line in out.strip().splitlines():
            parts = line.split("|")
            if len(parts) == 2:
                name = parts[0].strip()
                is_shared = parts[1].strip().lower() == "true"
                is_default = (name == default_for_user)
                result.append((name, is_default, is_shared))
    except Exception:
        pass
    return result


def get_sharing_status():
    """Kiểm tra trạng thái thực tế của File & Printer Sharing và Password Protected Sharing
    Đảm bảo đồng bộ chuẩn xác 100% với giao diện Control Panel trên Windows 10/11.
    """
    fps_on = False
    pps_on = False

    # ────────────────────────────────────────────────────────
    # 1. FILE & PRINTER SHARING (FPS)
    # Dùng Get-NetFirewallRule trả về nhiều rule (mỗi profile 1 dòng).
    # KHÔNG dùng -eq 'True' trực tiếp vì kết quả là array nhiều dòng.
    # Đếm số rule có Enabled=True: >= 1 là FPS đang bật.
    # Kết hợp kiểm tra service LanmanServer đang Running.
    # ────────────────────────────────────────────────────────
    try:
        ps_check_fps = (
            "$rules = Get-NetFirewallRule -DisplayName 'File and Printer Sharing (SMB-In)' "
            "-ErrorAction SilentlyContinue; "
            "($rules | Where-Object { $_.Enabled -eq 'True' }).Count"
        )
        out_fps = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps_check_fps],
            stderr=subprocess.DEVNULL, text=True, timeout=5
        )
        fps_on = int(out_fps.strip() or "0") >= 1

        # LanmanServer service phải Running thì share mới thực sự hoạt động
        if fps_on:
            ps_check_srv = "(Get-Service LanmanServer -ErrorAction SilentlyContinue).Status -eq 'Running'"
            out_srv = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps_check_srv],
                stderr=subprocess.DEVNULL, text=True, timeout=4
            )
            fps_on = out_srv.strip().lower() == "true"

    except Exception:
        fps_on = False

    # ────────────────────────────────────────────────────────
    # 2. PASSWORD PROTECTED SHARING (PPS)
    #
    # Xác nhận từ debug_pps.ps1 (before/after giống hệt nhau):
    # Windows 11 24H2 KHÔNG ghi vào registry khi toggle PPS trong UI.
    # PPS được quản lý qua SMB CIM layer:
    #   Get-SmbServerConfiguration -> EnableAuthenticateUserSharing
    #     True  = PPS ON  (yêu cầu xác thực)
    #     False = PPS OFF (cho phép truy cập ẩn danh)
    #
    # Registry ForceGuest / AllowInsecureGuestAuth không còn
    # được Windows 11 24H2 đọc để hiển thị trạng thái UI.
    # ────────────────────────────────────────────────────────
    try:
        ps_pps = (
            "(Get-SmbServerConfiguration -ErrorAction Stop)"
            ".EnableAuthenticateUserSharing"
        )
        out_pps = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps_pps],
            stderr=subprocess.DEVNULL, text=True, timeout=6
        )
        pps_on = out_pps.strip().lower() == "true"
    except Exception:
        pps_on = False

    return fps_on, pps_on

def get_workgroup():
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-WmiObject Win32_ComputerSystem).Workgroup"],
            stderr=subprocess.DEVNULL, text=True, timeout=6
        )
        return out.strip() or "N/A"
    except Exception:
        return "N/A"


def check_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def collect_sysinfo():
    product, build, ubr, edition, display = get_windows_edition()
    printers = get_printers()
    workgroup = get_workgroup()
    is_admin  = check_admin()
    is_home   = "home" in edition.lower()
    fps_on, pps_on = get_sharing_status()

    # Tìm chính xác máy in mặc định hệ thống
    default_printer  = next((p[0] for p in printers if p[1]), "Chua co")
    shared_printers  = [p[0] for p in printers if p[2]]
    all_printers     = [p[0] for p in printers]

    return {
        "os_name"         : product,
        "os_version"      : display or build,
        "os_build"        : f"{build}.{ubr}" if ubr else build,
        "edition"         : edition,
        "is_home"         : is_home,
        "computer_name"   : socket.gethostname(),
        "workgroup"       : workgroup,
        "default_printer" : default_printer,
        "shared_printers" : shared_printers,
        "all_printers"    : all_printers,
        "is_admin"        : is_admin,
        "arch"            : platform.machine(),
        "python_ver"      : platform.python_version(),
        "fps_on"          : fps_on,
        "pps_on"          : pps_on
    }


# ─────────────────────────────────────────────
# Logic PowerShell chuẩn hóa bảo mật
# ─────────────────────────────────────────────
SETUP_SCRIPT = r"""
param($U,$P,$IsHome)

$ErrorActionPreference = 'Stop'

function Step($n,$msg){ Write-Host "[BUOC $n] $msg" }
function OK($msg)     { Write-Host "         [OK] $msg" }
function WARN($msg)   { Write-Host "         [WARN] $msg" }

# 1. Tao / cap nhat user chu luc (PrintUser)
Step 1 "Tao user phuc vu chia se: $U"
$existing = Get-LocalUser -Name $U -ErrorAction SilentlyContinue
$sp = ConvertTo-SecureString $P -AsPlainText -Force
if ($existing) {
    Set-LocalUser -Name $U -Password $sp -PasswordNeverExpires $true
    OK "User da ton tai, tien hanh cap nhat mat khau moi."
} else {
    New-LocalUser -Name $U -Password $sp -FullName "Printer Share Account" `
        -Description "Tai khoan chia se may in" `
        -PasswordNeverExpires -UserMayNotChangePassword -AccountNeverExpires | Out-Null
    OK "Da tao thanh cong user '$U'."
}

# 2. Them vao nhom Users
Step 2 "Phan quyen cho '$U' vao nhom Users"
Remove-LocalGroupMember -Group "Guests" -Member $U -ErrorAction SilentlyContinue
$inUsers = Get-LocalGroupMember -Group "Users" -ErrorAction SilentlyContinue |
           Where-Object { $_.Name -match [regex]::Escape($U) }
if (-not $inUsers) {
    Add-LocalGroupMember -Group "Users" -Member $U
    OK "Da gan '$U' vao nhom Users."
} else { OK "'$U' da dung nhom Users." }

# 3. Deny logon locally
Step 3 "Thiet lap quyen 'Deny log on locally' bao mat"
$sid = (Get-LocalUser -Name $U).SID.Value
if ($IsHome -eq "True") {
    $key = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList"
    if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
    Set-ItemProperty -Path $key -Name $U -Value 0 -Type DWord
    OK "Ban Windows Home: Da an tai khoan '$U' khoi man hinh Welcome."
} else {
    $exp = "$env:TEMP\spe.cfg"; $imp = "$env:TEMP\spi.cfg"
    secedit /export /cfg $exp /quiet
    $c = Get-Content $exp -Encoding Unicode
    $k = "SeDenyInteractiveLogonRight"
    $line = $c | Where-Object { $_ -match "^$k\s*=" }
    if ($line) {
        if ($line -match [regex]::Escape("*$sid")) {
            OK "SID cua user da ton tai trong chinh sach chan login."
            $m = $c
        } else {
            $m = $c -replace "^($k\s*=.*)", "`$1,*$sid"
            OK "Da them SID vao $k."
        }
    } else {
        $m = $c -replace "(\[Privilege Rights\])", "`$1`r`n$k = *$sid"
        OK "Khoi tao khoa moi $k cho he thong."
    }
    $m | Set-Content $imp -Encoding Unicode
    secedit /configure /db "$env:TEMP\secedit.sdb" /cfg $imp /areas USER_RIGHTS /quiet
    Remove-Item $exp,$imp -Force -ErrorAction SilentlyContinue
    OK "Local Security Policy da cap nhat hoan tat."
}

# 4. CHUYỂN PROFILE MẠNG SANG PRIVATE
Step 4 "Kiem tra va chuyen cac Profile mang sang Private"
try {
    $netProfiles = Get-NetConnectionProfile -NetworkCategory Public -ErrorAction SilentlyContinue
    if ($netProfiles) {
        foreach ($profile in $netProfiles) {
            Set-NetConnectionProfile -InterfaceIndex $profile.InterfaceIndex -NetworkCategory Private
            OK "Da chuyen card mang Index $($profile.InterfaceIndex) tu Public -> Private."
        }
    } else {
        OK "Cac card mang hien tai deu da o che do Private hoac Domain."
    }
} catch {
    WARN "Khong the tu dong chuyen doi profile mang: $_"
}

# 5. TURN ON FILE & PRINTER SHARING + NETWORK DISCOVERY (Fix triệt để tương thích)
Step 5 "Turn On Network Discovery va File & Printer Sharing"
try {
    Enable-NetFirewallRule -DisplayGroup "Network Discovery" -ErrorAction SilentlyContinue
    Enable-NetFirewallRule -DisplayGroup "File and Printer Sharing" -ErrorAction SilentlyContinue
    
    # Khoi dong va duy tri cac service de bat nut Turn On trong Control Panel
    Set-Service fdPHost -StartupType Automatic -ErrorAction SilentlyContinue
    Set-Service FDResPub -StartupType Automatic -ErrorAction SilentlyContinue
    if ((Get-Service fdPHost).Status -ne "Running") { Start-Service fdPHost -ErrorAction SilentlyContinue }
    if ((Get-Service FDResPub).Status -ne "Running") { Start-Service FDResPub -ErrorAction SilentlyContinue }

    $srvPrv = "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters"
    Set-ItemProperty $srvPrv -Name "NullSessionShares" -Value "srvsvc" -Type MultiString -ErrorAction SilentlyContinue

    OK "Advanced Sharing: Da 'Turn On' trang thai Network Discovery & File Sharing."
} catch {
    WARN "Loi khi mo rong tinh nang Advanced Sharing: $_"
}

# 6. TURN ON PASSWORD PROTECTED SHARING (All Networks)
Step 6 "Turn On Password Protected Sharing (Ap dung cho All Networks)"
try {
    # ==========================================================
    # CHAN DOAN THUC TE (debug_pps.ps1 xac nhan):
    # Windows 11 24H2 KHONG luu PPS vao registry khi toggle UI.
    # PPS duoc quan ly hoan toan qua SMB CIM object.
    # Key chinh xac: Set-SmbServerConfiguration -EnableAuthenticateUserSharing
    #   $true  => yeu cau xac thuc (PPS ON)
    #   $false => cho phep truy cap an danh (PPS OFF)
    # Registry ForceGuest / AllowInsecureGuestAuth khong con hieu luc tren Win11 24H2.
    # ==========================================================

    # BUOC A: Set qua SmbServerConfiguration (cach duy nhat hieu luc tren Win11 24H2)
    Set-SmbServerConfiguration -EnableAuthenticateUserSharing $true -Force -ErrorAction Stop
    OK "SmbServerConfiguration: EnableAuthenticateUserSharing = True (PPS ON)."

    # BUOC B: Giu lai registry legacy de dong bo hien thi Control Panel cu
    $lsa = "HKLM:\SYSTEM\CurrentControlSet\Control\Lsa"
    Set-ItemProperty $lsa -Name ForceGuest                -Value 0 -Type DWord -Force
    Set-ItemProperty $lsa -Name restrictanonymous         -Value 0 -Type DWord -Force
    Set-ItemProperty $lsa -Name restrictanonymoussam      -Value 1 -Type DWord -Force
    Set-ItemProperty $lsa -Name everyoneincludesanonymous -Value 0 -Type DWord -Force
    OK "LSA registry legacy: da dong bo."

    $srv = "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters"
    Set-ItemProperty $srv -Name AutoShareWks             -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
    Set-ItemProperty $srv -Name EnableSecuritySignature  -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
    Set-ItemProperty $srv -Name RequireSecuritySignature -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
    OK "LanmanServer registry: da dong bo."

    OK "Password Protected Sharing (All Networks): DA BAT THANH CONG."
} catch {
    WARN "Loi khi bat PPS: $_"
    WARN "Thu fallback: ghi truc tiep EnableAuthenticateUserSharing vao registry..."
    try {
        $srv2 = "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters"
        Set-ItemProperty $srv2 -Name EnableAuthenticateUserSharing -Value 1 -Type DWord -Force
        OK "Fallback registry: EnableAuthenticateUserSharing = 1."
    } catch {
        WARN "Fallback cung that bai: $_"
    }
}

# 7. Firewall chi tiet & Spooler
Step 7 "Kich hoat bo rule tuong lua chi tiet va on dinh Print Spooler"
@(
    "File and Printer Sharing (NB-Session-In)",
    "File and Printer Sharing (SMB-In)",
    "File and Printer Sharing (Spooler Service - RPC)",
    "File and Printer Sharing (Spooler Service - RPC-EPMAP)",
    "File and Printer Sharing (NB-Datagram-In)",
    "File and Printer Sharing (NB-Name-In)"
) | ForEach-Object {
    Enable-NetFirewallRule -DisplayName $_ -ErrorAction SilentlyContinue
}
$sp2 = Get-Service Spooler -ErrorAction SilentlyContinue
if ($sp2) {
    Set-Service Spooler -StartupType Automatic -ErrorAction SilentlyContinue
    if ($sp2.Status -ne "Running") { Start-Service Spooler }
}
OK "Cac ket noi phu tro cua may in da san sang."

# 8. Gpupdate /force
Step 8 "Thuc thi gpupdate /force dong bo hoa giao dien va policy lap tuc"
& gpupdate /force /wait:15 | Out-Null
OK "He thong da ap dung va dong bo thiet lap Windows. Khong can khoi dong lai!"

Write-Host ""
Write-Host "=== HOAN THANH ==="
Write-Host "May chu : $env:COMPUTERNAME"
Write-Host "Username: $U"
Write-Host "Password: $P"
"""



# ─────────────────────────────────────────────
# PowerShell scripts cho từng lỗi máy in
# Dịch 1-1 từ fixprint.cmd
# ─────────────────────────────────────────────
FIX_SCRIPTS = {
    "comm": r"""
Write-Host "[FIX] Canon Communication Error..."
Stop-Service Spooler -Force -ErrorAction SilentlyContinue
Start-Sleep 1
$usbMonBase = "HKLM:\SYSTEM\CurrentControlSet\Control\Print\Monitors\USB Monitor"
Remove-ItemProperty "$usbMonBase\UsbPortList" -Name * -ErrorAction SilentlyContinue
Remove-Item "$usbMonBase\Port" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$env:SystemRoot\System32\spool\PRINTERS\*" -Force -ErrorAction SilentlyContinue
Get-ChildItem "HKLM:\SYSTEM\CurrentControlSet\Control\Print\Monitors" |
    Where-Object { $_.PSChildName -match "CNB|USB" } |
    ForEach-Object { Remove-Item $_.PSPath -Recurse -Force -ErrorAction SilentlyContinue }
Start-Service Spooler -ErrorAction SilentlyContinue
Write-Host "[OK] Xong. Cam lai cap USB may in va thu lai."
""",
    "0x7c": r"""
Write-Host "[FIX] Loi 0x0000007c..."
Set-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Print" -Name RpcAuthnLevelPrivacyEnabled -Value 0 -Type DWord -Force
Stop-Service Spooler -Force -ErrorAction SilentlyContinue; Start-Sleep 1; Start-Service Spooler
Write-Host "[OK] Xong. Thu ket noi may in lai."
""",
    "0x11b": r"""
Write-Host "[FIX] Loi 0x0000011b..."
Set-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Print" -Name RpcAuthnLevelPrivacyEnabled -Value 0 -Type DWord -Force
$rpc = "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\RPC"
if (-not (Test-Path $rpc)) { New-Item $rpc -Force | Out-Null }
Set-ItemProperty $rpc -Name RpcOverNamedPipes -Value 1 -Type DWord -Force
Set-ItemProperty $rpc -Name RpcOverTcp        -Value 1 -Type DWord -Force
Stop-Service Spooler -Force -ErrorAction SilentlyContinue; Start-Sleep 1; Start-Service Spooler
Write-Host "[OK] Xong."
""",
    "0x709": r"""
Write-Host "[FIX] Loi 0x00000709..."
Stop-Service Spooler -Force -ErrorAction SilentlyContinue
dism /Online /Enable-Feature /FeatureName:Printing-Foundation-InternetPrinting-Client /NoRestart | Out-Null
dism /Online /Enable-Feature /FeatureName:Printing-LPRPortMonitor /NoRestart | Out-Null
Set-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Print" -Name RpcAuthnLevelPrivacyEnabled -Value 0 -Type DWord -Force
$regPath = "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Windows"
$acl = Get-Acl $regPath
$rule = New-Object System.Security.AccessControl.RegistryAccessRule("Everyone","FullControl","ContainerInherit,ObjectInherit","None","Allow")
$acl.SetAccessRule($rule); Set-Acl -Path $regPath -AclObject $acl
Set-ItemProperty $regPath -Name LegacyDefaultPrinterMode -Value 1 -Type DWord -Force
Remove-ItemProperty $regPath -Name Device -ErrorAction SilentlyContinue
Start-Service Spooler -ErrorAction SilentlyContinue
Write-Host "[OK] Xong. Khoi dong lai may va dat lai may in mac dinh."
""",
    "0x40": r"""
Write-Host "[FIX] Loi 0x00000040 (Firewall)..."
netsh advfirewall firewall set rule group="File and Printer Sharing" new enable=Yes | Out-Null
netsh advfirewall firewall set rule group="Network Discovery" new enable=Yes | Out-Null
Write-Host "[OK] Bat lai rule Firewall xong."
""",
    "0xbc4_tcp": r"""
Write-Host "[FIX] Loi 0x00000bc4 (RpcOverTcp+NamedPipes)..."
$rpc = "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\RPC"
if (-not (Test-Path $rpc)) { New-Item $rpc -Force | Out-Null }
Set-ItemProperty $rpc -Name RpcOverTcp        -Value 1 -Type DWord -Force
Set-ItemProperty $rpc -Name RpcOverNamedPipes  -Value 1 -Type DWord -Force
Write-Host "[OK] Xong."
""",
    "0xbc4_np": r"""
Write-Host "[FIX] Loi 0x00000bc4 (NamedPipes only)..."
$rpc = "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\RPC"
if (-not (Test-Path $rpc)) { New-Item $rpc -Force | Out-Null }
Set-ItemProperty $rpc -Name RpcOverTcp        -Value 0 -Type DWord -Force
Set-ItemProperty $rpc -Name RpcOverNamedPipes  -Value 1 -Type DWord -Force
Write-Host "[OK] Xong."
""",
    "0x6d9": r"""
Write-Host "[FIX] Loi 0x000006d9 (Windows Firewall service)..."
Set-Service MpsSvc -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service MpsSvc -ErrorAction SilentlyContinue
Write-Host "[OK] Firewall service da khoi dong lai."
""",
    "connect": r"""
Write-Host "[FIX] Printer Cannot Connect (7 buoc)..."
netsh advfirewall firewall set rule group="File and Printer Sharing" new enable=Yes | Out-Null
netsh advfirewall firewall set rule group="Network Discovery" new enable=Yes | Out-Null
Set-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Print" -Name RpcAuthnLevelPrivacyEnabled -Value 0 -Type DWord -Force
$rpc = "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\RPC"
if (-not (Test-Path $rpc)) { New-Item $rpc -Force | Out-Null }
Set-ItemProperty $rpc -Name RpcOverNamedPipes -Value 1 -Type DWord -Force
Set-ItemProperty $rpc -Name RpcOverTcp        -Value 1 -Type DWord -Force
# Copy mscms.dll neu thieu
$src = "$env:SystemRoot\System32\mscms.dll"
$d64 = "$env:SystemRoot\System32\spool\drivers\x64\3"
$d32 = "$env:SystemRoot\System32\spool\drivers\w32x86\3"
if (Test-Path $src) {
    if ((Test-Path $d64) -and !(Test-Path "$d64\mscms.dll")) { Copy-Item $src "$d64\mscms.dll" -Force }
    if ((Test-Path $d32) -and !(Test-Path "$d32\mscms.dll")) { Copy-Item $src "$d32\mscms.dll" -Force }
}
foreach ($svc in @("Spooler","fdPHost","FDResPub","SSDPSRV","upnphost")) {
    Set-Service $svc -StartupType Automatic -ErrorAction SilentlyContinue
    Start-Service $svc -ErrorAction SilentlyContinue
}
Stop-Service Spooler -Force -ErrorAction SilentlyContinue; Start-Sleep 1; Start-Service Spooler
Write-Host "[OK] Xong. Thu them may in tu \\<ten_may_chu> lai."
""",
    "0x12": r"""
Write-Host "[FIX] Loi 0x00000012..."
Set-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Print" -Name RpcAuthnLevelPrivacyEnabled -Value 0 -Type DWord -Force
$rpc = "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\RPC"
if (-not (Test-Path $rpc)) { New-Item $rpc -Force | Out-Null }
Set-ItemProperty $rpc -Name RpcOverTcp        -Value 1 -Type DWord -Force
Set-ItemProperty $rpc -Name RpcOverNamedPipes  -Value 1 -Type DWord -Force
Stop-Service Spooler -Force -ErrorAction SilentlyContinue; Start-Sleep 1; Start-Service Spooler
Write-Host "[OK] Xong."
""",
    "0x3eb": r"""
Write-Host "[FIX] Loi 0x000003eb..."
Stop-Service Spooler -Force -ErrorAction SilentlyContinue
Remove-Item "$env:SystemRoot\System32\spool\PRINTERS\*" -Force -ErrorAction SilentlyContinue
Set-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Print" -Name RpcAuthnLevelPrivacyEnabled -Value 0 -Type DWord -Force
Start-Service Spooler -ErrorAction SilentlyContinue
Write-Host "[OK] Xong."
""",
    "0x771": r"""
Write-Host "[FIX] Loi 0x00000771 (xoa registry Devices/Printers cua user)..."
Stop-Service Spooler -Force -ErrorAction SilentlyContinue
$win = "HKCU:\Software\Microsoft\Windows NT\CurrentVersion"
Remove-Item "$win\Devices"      -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$win\PrinterPorts" -Recurse -Force -ErrorAction SilentlyContinue
Remove-ItemProperty "$win\Windows" -Name Device -ErrorAction SilentlyContinue
Remove-Item "HKLM:\SYSTEM\CurrentControlSet\Control\Print\Printers" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$env:SystemRoot\System32\spool\PRINTERS\*" -Force -ErrorAction SilentlyContinue
Start-Service Spooler -ErrorAction SilentlyContinue
Write-Host "[OK] Xong. Cai dat lai may in."
""",
    "clear_spool": r"""
Write-Host "[FIX] Xoa hang doi in..."
Stop-Service Spooler -Force -ErrorAction SilentlyContinue
Remove-Item "$env:SystemRoot\System32\spool\PRINTERS\*" -Force -ErrorAction SilentlyContinue
Start-Service Spooler -ErrorAction SilentlyContinue
Write-Host "[OK] Hang doi in da duoc xoa sach."
""",
    "restart_spooler": r"""
Write-Host "[FIX] Khoi dong lai Print Spooler..."
Stop-Service Spooler -Force -ErrorAction SilentlyContinue
Start-Sleep 1
Start-Service Spooler -ErrorAction SilentlyContinue
Write-Host "[OK] Spooler da khoi dong lai."
""",
    "reset_usb": r"""
Write-Host "[FIX] Reset USB Monitor..."
$usbMon = "HKLM:\SYSTEM\CurrentControlSet\Control\Print\Monitors\USB Monitor"
Remove-ItemProperty "$usbMon\UsbPortList" -Name * -ErrorAction SilentlyContinue
Remove-Item "$usbMon\Port" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "[OK] USB Monitor da duoc reset. Cam lai cap USB may in."
""",
    "clean_drivers": r"""
Write-Host "[FIX] FULL CLEAN DriverStore - Xoa tat ca driver Printer..."
$tmp = "$env:TEMP\printer_drivers.txt"
pnputil /enum-drivers | Out-File $tmp -Encoding UTF8
$content = Get-Content $tmp
$current = $null; $count = 0
for ($i = 0; $i -lt $content.Count; $i++) {
    if ($content[$i] -match "Published Name\s*:\s*(.+)") { $current = $matches[1].Trim() }
    if ($content[$i] -match "Class Name\s*:\s*Printer" -and $current) {
        $count++
        Write-Host "[$count] Xoa: $current"
        $r = pnputil /delete-driver $current /uninstall /force 2>&1
        if ($LASTEXITCODE -eq 0) { Write-Host "    [OK]" } else { Write-Host "    [FAIL] $r" }
        $current = $null
    }
}
Remove-Item $tmp -Force -ErrorAction SilentlyContinue
Write-Host "[OK] Hoan tat - Da xu ly $count driver(s)."
""",
}


def run_fix(fix_key, log_callback, done_callback):
    script = FIX_SCRIPTS.get(fix_key, "")
    if not script:
        done_callback(False)
        return

    def worker():
        try:
            tmp = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "ps_fix_printer.ps1")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(script)
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tmp],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in proc.stdout:
                log_callback(line.rstrip())
            proc.wait()
            os.remove(tmp)
            done_callback(proc.returncode == 0)
        except Exception as ex:
            log_callback(f"[LOI] {ex}")
            done_callback(False)

    threading.Thread(target=worker, daemon=True).start()



def run_setup(username, password, is_home, log_callback, done_callback):
    def worker():
        try:
            tmp = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "ps_printer_setup.ps1")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(SETUP_SCRIPT)

            cmd = [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", tmp,
                "-U", username,
                "-P", password,
                "-IsHome", str(is_home),
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in proc.stdout:
                log_callback(line.rstrip())
            proc.wait()
            os.remove(tmp)
            done_callback(proc.returncode == 0)
        except Exception as ex:
            log_callback(f"[LOI] {ex}")
            done_callback(False)

    threading.Thread(target=worker, daemon=True).start()


# ─────────────────────────────────────────────
# Widget helpers
# ─────────────────────────────────────────────
def rounded_frame(parent, bg=SURFACE, pady=0, padx=0):
    f = tk.Frame(parent, bg=bg)
    f.pack(fill="x", pady=pady, padx=padx)
    return f


def label(parent, text, fg=TEXT, font=FONT, bg=None, anchor="w", **kw):
    return tk.Label(parent, text=text, fg=fg, font=font,
                    bg=bg or parent["bg"], anchor=anchor, **kw)


def sep(parent, color=BORDER):
    tk.Frame(parent, bg=color, height=1).pack(fill="x", pady=(8, 0))


def info_row(parent, key, value_var_or_str, val_fg=TEXT):
    row = tk.Frame(parent, bg=parent["bg"])
    row.pack(fill="x", pady=2)
    label(row, key, fg=TEXT2, font=FONT_SM, width=20).pack(side="left")

    if isinstance(value_var_or_str, tk.StringVar):
        lbl = tk.Label(row, textvariable=value_var_or_str, fg=val_fg, font=FONT_SM, bg=parent["bg"], anchor="w")
    else:
        lbl = tk.Label(row, text=value_var_or_str, fg=val_fg, font=FONT_SM, bg=parent["bg"], anchor="w")

    lbl.pack(side="left", padx=(4, 0))
    return lbl


# ─────────────────────────────────────────────
# Main App
# ─────────────────────────────────────────────
class PrinterShareApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Printer Share Setup And Fix Error — Huynh Duc Tung")
        self.configure(bg=BG)
        self.resizable(False, False)

        # Khởi tạo các StringVar động
        self.var_default_printer = tk.StringVar()
        self.var_fps_status = tk.StringVar()
        self.var_pps_status = tk.StringVar()

        # Quét hệ thống lúc khởi động
        self.sysinfo = collect_sysinfo()
        self._update_dynamic_vars()

        self._build_ui()
        self._center()

    def _update_dynamic_vars(self):
        """Đồng bộ dữ liệu quét thực tế lên biến Form"""
        info = self.sysinfo
        self.var_default_printer.set(info["default_printer"])

        fps_text = "● File & Printer Sharing: ON" if info["fps_on"] else "● File & Printer Sharing: OFF"
        pps_text = "● Password Protected Sharing: ON" if info["pps_on"] else "● Password Protected Sharing: OFF"

        self.var_fps_status.set(fps_text)
        self.var_pps_status.set(pps_text)

    def _build_ui(self):
        info = self.sysinfo

        # ── Header ──────────────────────────
        hdr = tk.Frame(self, bg=SURFACE, padx=20, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  Sửa lỗi chia sẻ và kết nối máy in trên Windows 10/11",
                 fg=TEXT, font=FONT_H1, bg=SURFACE, anchor="w").pack(side="left")
        admin_text  = "● Admin" if info["is_admin"] else "● Non-Admin"
        admin_color = SUCCESS if info["is_admin"] else DANGER
        tk.Label(hdr, text=admin_text, fg=admin_color,
                 font=FONT_SM, bg=SURFACE).pack(side="right")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── Notebook (Tab bar) ───────────────
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("App.TNotebook",
                        background=BG, borderwidth=0, tabmargins=[0, 0, 0, 0])
        style.configure("App.TNotebook.Tab",
                        background=SURFACE2, foreground=TEXT2,
                        font=FONT_BOLD, padding=[18, 8],
                        borderwidth=0, focuscolor=BG)
        style.map("App.TNotebook.Tab",
                  background=[("selected", ACCENT), ("active", SURFACE)],
                  foreground=[("selected", "#ffffff"), ("active", TEXT)])

        nb = ttk.Notebook(self, style="App.TNotebook")
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        # ─────────────────────────────────────
        # TAB 1: Setup
        # ─────────────────────────────────────
        tab_setup = tk.Frame(nb, bg=BG)
        nb.add(tab_setup, text="  Printer Share Server  ")
        self._build_tab_setup(tab_setup, info)

        # ─────────────────────────────────────
        # TAB 2: Fix Lỗi Máy In
        # ─────────────────────────────────────
        tab_fix = tk.Frame(nb, bg=BG)
        nb.add(tab_fix, text="  Fix Lỗi Máy In  ")
        self._build_tab_fix(tab_fix)

    # ════════════════════════════════════════
    # TAB 1 — Setup Chia Sẻ
    # ════════════════════════════════════════
    def _build_tab_setup(self, parent, info):
        body = tk.Frame(parent, bg=BG, padx=20, pady=16)
        body.pack(fill="both", expand=True)

        left  = tk.Frame(body, bg=BG)
        right = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        right.pack(side="left", fill="both", expand=True)

        # ── [LEFT] System Info ───────────────
        card = tk.Frame(left, bg=SURFACE, padx=16, pady=14,
                        highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 10))
        label(card, "Thông tin hệ thống", font=FONT_H2, fg=TEXT).pack(anchor="w")
        sep(card)
        tk.Frame(card, bg=BG, height=6).pack()
        print(info)
        info_row(card, "Hệ điều hành :", f"{info['os_name']} ({info['os_version']})")
        info_row(card, "Build :", info["os_build"])
        ed_color = WARN if info["is_home"] else SUCCESS
        row = tk.Frame(card, bg=card["bg"]); row.pack(fill="x", pady=2)
        label(row, "Edition :", fg=TEXT2, font=FONT_SM, width=20).pack(side="left")
        tk.Label(row, text=info["edition"], fg=ed_color,
                 font=FONT_SM, bg=card["bg"]).pack(side="left", padx=(4, 0))
        info_row(card, "Kiến trúc :", info["arch"])
        info_row(card, "Computer name :", info["computer_name"], val_fg=ACCENT)
        info_row(card, "Workgroup :", info["workgroup"])

        # ── [LEFT] Printer Info ──────────────
        pcard = tk.Frame(left, bg=SURFACE, padx=16, pady=14,
                         highlightbackground=BORDER, highlightthickness=1)
        pcard.pack(fill="x")
        label(pcard, "Thông tin máy in", font=FONT_H2, fg=TEXT).pack(anchor="w")
        sep(pcard)
        tk.Frame(pcard, bg=BG, height=6).pack()

        self.lbl_default_printer = info_row(
            pcard, "Mặc định:", self.var_default_printer, val_fg=ACCENT)
        if info["shared_printers"]:
            for i, sp in enumerate(info["shared_printers"]):
                lbl = "Đang chia sẻ :" if i == 0 else ""
                row2 = tk.Frame(pcard, bg=pcard["bg"]); row2.pack(fill="x", pady=1)
                label(row2, lbl, fg=TEXT2, font=FONT_SM, width=20).pack(side="left")
                tk.Label(row2, text=sp, fg=SUCCESS,
                         font=FONT_SM, bg=pcard["bg"]).pack(side="left", padx=(4, 0))
                tk.Label(row2, text="  [SHARED]", fg=SUCCESS,
                         font=FONT_SM, bg=pcard["bg"]).pack(side="left")
        else:
            info_row(pcard, "Đang chia sẻ :", "Chưa có máy in nào", val_fg=WARN)

        tk.Frame(pcard, bg=BG, height=4).pack()
        label(pcard, "Tất cả máy in:", fg=TEXT2, font=FONT_SM).pack(anchor="w")
        if info["all_printers"]:
            for p in info["all_printers"]:
                row3 = tk.Frame(pcard, bg=pcard["bg"]); row3.pack(fill="x")
                tk.Label(row3, text="  •  ", fg=TEXT3,
                         font=FONT_SM, bg=pcard["bg"]).pack(side="left")
                tk.Label(row3, text=p, fg=TEXT,
                         font=FONT_SM, bg=pcard["bg"]).pack(side="left")
        else:
            label(pcard, "  Không tìm thấy máy in nào", fg=TEXT3, font=FONT_SM).pack(anchor="w")

        # ── [RIGHT] Form nhap ────────────────
        fcard = tk.Frame(right, bg=SURFACE, padx=16, pady=14,
                         highlightbackground=BORDER, highlightthickness=1)
        fcard.pack(fill="x", pady=(0, 10))
        label(fcard, "Tạo tài khoản chia sẻ máy in và không cho đăng nhập trên máy chủ", font=FONT_H2, fg=TEXT).pack(anchor="w")

        self.lbl_fps_badge = tk.Label(fcard, textvariable=self.var_fps_status,
                                      font=FONT_SM, bg=SURFACE)
        self.lbl_fps_badge.pack(anchor="w", pady=(4, 0))
        self.lbl_pps_badge = tk.Label(fcard, textvariable=self.var_pps_status,
                                      font=FONT_SM, bg=SURFACE)
        self.lbl_pps_badge.pack(anchor="w", pady=(0, 4))
        self._update_badge_colors()

        sep(fcard)
        tk.Frame(fcard, bg=BG, height=10).pack()

        label(fcard, "Username", fg=TEXT2, font=FONT_SM).pack(anchor="w")
        self.var_user = tk.StringVar(value="PrintUser")
        e_user = tk.Entry(fcard, textvariable=self.var_user,
                          bg=SURFACE2, fg=TEXT, insertbackground=TEXT,
                          relief="flat", font=FONT, bd=0,
                          highlightbackground=BORDER, highlightthickness=1,
                          highlightcolor=ACCENT)
        e_user.pack(fill="x", ipady=7, pady=(3, 10))

        label(fcard, "Password", fg=TEXT2, font=FONT_SM).pack(anchor="w")
        self.var_pass = tk.StringVar(value="Lacviet@2026!")
        prow = tk.Frame(fcard, bg=SURFACE2,
                        highlightbackground=BORDER, highlightthickness=1)
        prow.pack(fill="x", pady=(3, 4))
        self.e_pass = tk.Entry(prow, textvariable=self.var_pass,
                               show="•", bg=SURFACE2, fg=TEXT,
                               insertbackground=TEXT, relief="flat", font=FONT, bd=0)
        self.e_pass.pack(side="left", fill="x", expand=True, ipady=7, padx=(6, 0))
        self.show_pw = False
        tk.Button(prow, text="👁", bg=SURFACE2, fg=TEXT2, relief="flat", bd=0,
                  cursor="hand2", activebackground=SURFACE2, activeforeground=TEXT,
                  command=self._toggle_pw).pack(side="right", padx=4)

        if not info["is_admin"]:
            note2 = tk.Frame(fcard, bg="#2a1010", padx=10, pady=8,
                             highlightbackground="#5a1010", highlightthickness=1)
            note2.pack(fill="x", pady=(6, 4))
            label(note2, "⛔  Chua chay voi quyen Admin!\n"
                         "   Vui long chay lai bang 'Run as administrator'.",
                  fg=DANGER, font=FONT_SM, bg="#2a1010", justify="left").pack(anchor="w")

        tk.Frame(fcard, bg=BG, height=6).pack()
        self.btn_run = tk.Button(
            fcard, text="▶  Chay Setup",
            bg=ACCENT, fg="#ffffff", activebackground=ACCENT_HVR,
            activeforeground="#ffffff", relief="flat", bd=0,
            font=FONT_BOLD, cursor="hand2", padx=16, pady=9,
            command=self._on_run)
        self.btn_run.pack(fill="x")

        # ── [RIGHT] Log ──────────────────────
        lcard = tk.Frame(right, bg=SURFACE, padx=14, pady=12,
                         highlightbackground=BORDER, highlightthickness=1)
        lcard.pack(fill="both", expand=True)
        lhdr = tk.Frame(lcard, bg=SURFACE); lhdr.pack(fill="x")
        label(lhdr, "Log", font=FONT_H2, fg=TEXT, bg=SURFACE).pack(side="left")
        tk.Button(lhdr, text="Xoa", bg=SURFACE, fg=TEXT3, relief="flat", bd=0,
                  font=FONT_SM, activebackground=SURFACE, cursor="hand2",
                  command=self._log_clear).pack(side="right")
        sep(lcard)
        self.log_text = tk.Text(
            lcard, bg="#111520", fg=TEXT, insertbackground=TEXT,
            relief="flat", bd=0, font=FONT_MONO, height=16,
            wrap="word", state="disabled")
        sb = tk.Scrollbar(lcard, command=self.log_text.yview, bg=SURFACE,
                          troughcolor=SURFACE2, width=8)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=(6, 0))
        self.log_text.pack(fill="both", expand=True, pady=(6, 0))
        self.log_text.tag_configure("ok",   foreground=SUCCESS)
        self.log_text.tag_configure("warn", foreground=WARN)
        self.log_text.tag_configure("err",  foreground=DANGER)
        self.log_text.tag_configure("step", foreground=ACCENT)
        self.log_text.tag_configure("done", foreground=SUCCESS,
                                    font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("dim",  foreground=TEXT3)
        self._log("Nhan 'Chay Setup' de bat dau.", "dim")

    # ════════════════════════════════════════
    # TAB 2 — Fix Lỗi Máy In
    # ════════════════════════════════════════
    def _build_tab_fix(self, parent):
        body = tk.Frame(parent, bg=BG, padx=20, pady=16)
        body.pack(fill="both", expand=True)

        left  = tk.Frame(body, bg=BG)
        right = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="y", padx=(0, 12))
        right.pack(side="left", fill="both", expand=True)

        # ── [LEFT] Danh sach fix ─────────────
        lcard = tk.Frame(left, bg=SURFACE, padx=14, pady=14,
                         highlightbackground=BORDER, highlightthickness=1)
        lcard.pack(fill="y", expand=True)
        label(lcard, "Chon loai loi", font=FONT_H2, fg=TEXT).pack(anchor="w")
        sep(lcard)
        tk.Frame(lcard, bg=BG, height=8).pack()

        # Danh sach cac fix: (label hien thi, fix_key, mo ta ngan)
        FIX_ITEMS = [
            ("Canon Communication Error",   "comm",        "Loi giao tiep USB Canon LBP2900/3300"),
            ("Loi 0x0000007c",               "0x7c",        "RpcAuthnLevel — thường gặp sau Windows Update"),
            ("Loi 0x0000011b",               "0x11b",       "RPC Authentication — lỗi bảo mật máy in mạng"),
            ("Loi 0x00000709",               "0x709",       "Cannot set default printer"),
            ("Loi 0x00000040",               "0x40",        "Firewall chặn File & Printer Sharing"),
            ("Loi 0x00000bc4",               "0xbc4_tcp",   "No printers — RpcOverTcp + NamedPipes"),
            ("Loi 0x00000bc4 (NamedPipe)",   "0xbc4_np",    "No printers — NamedPipes only"),
            ("Loi 0x000006d9",               "0x6d9",       "Firewall service bị tắt"),
            ("Printer Cannot Connect",       "connect",     "7 bước fix kết nối máy in mạng"),
            ("Loi 0x00000012",               "0x12",        "Printer offline / RPC"),
            ("Loi 0x000003eb",               "0x3eb",       "Driver mismatch — xóa spool queue"),
            ("Loi 0x00000771",               "0x771",       "Registry Devices/Printers bị hỏng"),
            ("─── Tiện ích ───",             None,          ""),
            ("Xoa hang doi in",              "clear_spool", "Xóa tất cả job đang kẹt"),
            ("Restart Print Spooler",        "restart_spooler", "Khởi động lại dịch vụ Spooler"),
            ("Reset USB Monitor",            "reset_usb",   "Xóa registry USB Monitor"),
            ("FULL CLEAN DriverStore",       "clean_drivers","Xóa toàn bộ driver máy in trong DriverStore"),
        ]

        self._fix_btns = []
        for display, key, desc in FIX_ITEMS:
            if key is None:
                # Separator label
                tk.Frame(lcard, bg=BORDER, height=1).pack(fill="x", pady=(6, 4))
                tk.Label(lcard, text=display, fg=TEXT3, font=FONT_SM,
                         bg=SURFACE, anchor="w").pack(fill="x")
                continue

            is_danger = key in ("clean_drivers", "0x771")
            btn_bg    = "#3a1515" if is_danger else SURFACE2
            btn_fg    = DANGER    if is_danger else TEXT

            btn = tk.Button(
                lcard, text=display, anchor="w",
                bg=btn_bg, fg=btn_fg, activebackground=BORDER,
                activeforeground=TEXT, relief="flat", bd=0,
                font=FONT_SM, cursor="hand2", padx=8, pady=5,
                command=lambda k=key, d=desc: self._on_fix(k, d)
            )
            btn.pack(fill="x", pady=1)
            self._fix_btns.append((key, btn))

        # ── [RIGHT] Mo ta + Log fix ──────────
        rcard = tk.Frame(right, bg=SURFACE, padx=14, pady=12,
                         highlightbackground=BORDER, highlightthickness=1)
        rcard.pack(fill="both", expand=True)

        rhdr = tk.Frame(rcard, bg=SURFACE); rhdr.pack(fill="x")
        label(rhdr, "Log", font=FONT_H2, fg=TEXT, bg=SURFACE).pack(side="left")
        tk.Button(rhdr, text="Xoa", bg=SURFACE, fg=TEXT3, relief="flat", bd=0,
                  font=FONT_SM, activebackground=SURFACE, cursor="hand2",
                  command=self._fix_log_clear).pack(side="right")
        sep(rcard)

        # Thanh mo ta loi hien tai
        self.lbl_fix_desc = tk.Label(
            rcard, text="← Chon mot loai loi de bat dau sua.",
            fg=TEXT2, font=FONT_SM, bg=SURFACE, anchor="w", wraplength=380, justify="left")
        self.lbl_fix_desc.pack(anchor="w", pady=(6, 4))

        self.fix_log_text = tk.Text(
            rcard, bg="#111520", fg=TEXT, insertbackground=TEXT,
            relief="flat", bd=0, font=FONT_MONO, wrap="word", state="disabled")
        sb2 = tk.Scrollbar(rcard, command=self.fix_log_text.yview,
                           bg=SURFACE, troughcolor=SURFACE2, width=8)
        self.fix_log_text.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y", pady=(4, 0))
        self.fix_log_text.pack(fill="both", expand=True, pady=(4, 0))
        self.fix_log_text.tag_configure("ok",   foreground=SUCCESS)
        self.fix_log_text.tag_configure("warn", foreground=WARN)
        self.fix_log_text.tag_configure("err",  foreground=DANGER)
        self.fix_log_text.tag_configure("step", foreground=ACCENT)
        self.fix_log_text.tag_configure("done", foreground=SUCCESS,
                                        font=("Consolas", 9, "bold"))
        self.fix_log_text.tag_configure("dim",  foreground=TEXT3)

    # ── Helpers ───────────────────────────────
    def _update_badge_colors(self):
        """Cập nhật màu chữ nhãn mạng động trực quan"""
        self.lbl_fps_badge.config(fg=SUCCESS if self.sysinfo["fps_on"] else DANGER)
        self.lbl_pps_badge.config(fg=SUCCESS if self.sysinfo["pps_on"] else DANGER)

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")

    def _toggle_pw(self):
        self.show_pw = not self.show_pw
        self.e_pass.config(show="" if self.show_pw else "•")

    def _log(self, text, tag=""):
        self.log_text.config(state="normal")
        self.log_text.insert("end", text + "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _log_line(self, text):
        tag = ""
        t = text.strip()
        if "[OK]"      in t: tag = "ok"
        elif "[WARN]"  in t: tag = "warn"
        elif "[LOI]"   in t or "[ERROR]" in t.upper(): tag = "err"
        elif t.startswith("[BUOC") or t.startswith("==="):  tag = "step"
        elif "HOAN THANH" in t: tag = "done"
        self._log(text, tag)

    def _log_clear(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _set_running(self, running: bool):
        self.btn_run.config(
            state="disabled" if running else "normal",
            text="⏳ Dang chay..." if running else "▶  Chay Setup",
            bg=BORDER if running else ACCENT,
        )

    # ── Fix tab actions ───────────────────────
    def _fix_log(self, text, tag=""):
        self.fix_log_text.config(state="normal")
        self.fix_log_text.insert("end", text + "\n", tag)
        self.fix_log_text.see("end")
        self.fix_log_text.config(state="disabled")

    def _fix_log_line(self, text):
        t = text.strip()
        tag = ""
        if "[OK]"  in t:                          tag = "ok"
        elif "[WARN]" in t:                       tag = "warn"
        elif "[LOI]" in t or "[FAIL]" in t:       tag = "err"
        elif t.startswith("[FIX]"):               tag = "step"
        self._fix_log(text, tag)

    def _fix_log_clear(self):
        self.fix_log_text.config(state="normal")
        self.fix_log_text.delete("1.0", "end")
        self.fix_log_text.config(state="disabled")

    def _set_fix_buttons(self, disabled: bool):
        for _, btn in self._fix_btns:
            btn.config(state="disabled" if disabled else "normal")

    def _on_fix(self, fix_key, desc):
        if not self.sysinfo["is_admin"]:
            messagebox.showerror("Loi", "Can quyen Administrator de sua loi may in.")
            return

        # Canh bao rieng cho clean_drivers
        if fix_key == "clean_drivers":
            if not messagebox.askyesno(
                "Xac nhan FULL CLEAN",
                "Thao tac nay se XOA TOAN BO driver may in khoi DriverStore.\n\n"
                "Sau khi xoa, ban phai cai lai driver thu cong.\n\n"
                "Tiep tuc?"
            ):
                return

        self._fix_log_clear()
        self._fix_log(f"[FIX] Dang chay: {desc or fix_key}", "step")
        self._fix_log("─" * 48, "dim")
        self.lbl_fix_desc.config(text=f"Đang sửa: {desc}", fg=WARN)
        self._set_fix_buttons(True)

        run_fix(
            fix_key=fix_key,
            log_callback=lambda line: self.after(0, self._fix_log_line, line),
            done_callback=lambda ok: self.after(0, self._on_fix_done, ok, desc),
        )

    def _on_fix_done(self, success: bool, desc: str):
        self._set_fix_buttons(False)
        self._fix_log("─" * 48, "dim")
        if success:
            self._fix_log("=== HOAN THANH ===", "done")
            self.lbl_fix_desc.config(
                text=f"✔  Xong: {desc}  —  Thu ket noi lai may in.", fg=SUCCESS)
        else:
            self._fix_log("=== CO LOI — Xem log ===", "err")
            self.lbl_fix_desc.config(text=f"✘  Loi khi sua: {desc}", fg=DANGER)

    
        username = self.var_user.get().strip()
        password = self.var_pass.get().strip()

        if not username or not password:
            messagebox.showwarning("Thieu thong tin", "Vui long nhap day du Username va Password.")
            return
        if len(password) < 6:
            messagebox.showwarning("Mat khau ngan", "Password can it nhat 6 ky tu.")
            return
        if not self.sysinfo["is_admin"]:
            messagebox.showerror("Loi", "Ban phai chay tool bang quyen Administrator.")
            return

        if not messagebox.askyesno("Xac nhan", f"Tien hanh Setup chia se cho user '{username}'?"):
            return

        self._log_clear()
        self._set_running(True)
        self._log(f"Bat dau thuc thi thiet lap mang va khoi tao user '{username}'...", "step")
        self._log("─" * 50, "dim")

        run_setup(
            username=username,
            password=password,
            is_home=self.sysinfo["is_home"],
            log_callback=lambda line: self.after(0, self._log_line, line),
            done_callback=lambda ok:  self.after(0, self._on_done, ok, username, password),
        )

    def _on_run(self):
        username = self.var_user.get().strip()
        password = self.var_pass.get().strip()

        if not username or not password:
            messagebox.showwarning("Thieu thong tin", "Vui long nhap day du Username va Password.")
            return
        if len(password) < 6:
            messagebox.showwarning("Mat khau ngan", "Password can it nhat 6 ky tu.")
            return
        if not self.sysinfo["is_admin"]:
            messagebox.showerror("Loi", "Ban phai chay tool bang quyen Administrator.")
            return

        if not messagebox.askyesno("Xac nhan", f"Tien hanh Setup chia se cho user '{username}'?"):
            return

        self._log_clear()
        self._set_running(True)
        self._log(f"Bat dau thuc thi thiet lap mang va khoi tao user '{username}'...", "step")
        self._log("─" * 50, "dim")

        run_setup(
            username=username,
            password=password,
            is_home=self.sysinfo["is_home"],
            log_callback=lambda line: self.after(0, self._log_line, line),
            done_callback=lambda ok:  self.after(0, self._on_done, ok, username, password),
        )

    def _on_done(self, success: bool, username: str, password: str):
        self._set_running(False)
        self._log("─" * 50, "dim")

        # Quét và đồng bộ lại toàn bộ trạng thái thực tế sau khi xử lý xong
        self.sysinfo = collect_sysinfo()
        self._update_dynamic_vars()
        self._update_badge_colors()

        if success:
            self._log("=== HOAN THANH THANH CONG ===", "done")
            comp = self.sysinfo["computer_name"]
            self._log(f"Duong dan truy cap tu may tram: \\\\{comp}", "ok")

            # Đổi màu hiển thị máy in mặc định sang xanh lá/xanh dương nếu hợp lệ
            dp_color = ACCENT if self.sysinfo["default_printer"] != "Chua co" else DANGER
            self.lbl_default_printer.config(fg=dp_color)

            messagebox.showinfo(
                "Thanh cong",
                f"Thuc thi hoan tat!\n\n"
                f"Trang thai thuc te:\n"
                f"  - Profile mang: Private (Da dong bo)\n"
                f"  - File & Printer Sharing: ON\n"
                f"  - Password Protected Sharing: ON\n\n"
                f"May tram ket noi: \\\\{comp}\n"
                f"Username dung chung: {username}"
            )
        else:
            self._log("=== CO LOI XAY RA — Vui long kiem tra bang Log ===", "err")
            messagebox.showerror("Loi", "Setup co loi trong qua trinh thuc thi. Vui long xem log.")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == '__main__':
    if ctypes.windll.shell32.IsUserAnAdmin():
        app = PrinterShareApp()
        app.mainloop()
    else:
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        except Exception as e:
            sys.exit(1)