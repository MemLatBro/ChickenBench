# =====================================================================
# ChickenBench Runner v1.0.8  (Windows PowerShell 5.1, run via CB_Run.bat)
#
# Drives Angel's "CS2 FPS BENCHMARK DUST2" (workshop 3240880604) in a loop:
#   - launches CS2 with -condebug (console written to console.log)
#   - in-game commands: writes them to cfg\cb_cmd.cfg and presses ONE bound key
#     (bind pgdn "exec cb_cmd"); every batch ends with "exec cb_ack_n" (a file that does
#     not exist on purpose): CS2 logs "[InputService] exec: couldn't exec ... cb_ack_n"
#     to console.log, which confirms the batch. ([Console]-channel echo lines are NOT
#     written to console.log once Angel's map has run, so echo cannot be used.)
#   - key binds do not fire in the main menu, so the map is loaded by typing one
#     line into the console:  hideconsole; exec cb_init; map_workshop 3240880604 de_dust2
#   - each lap: mp_restartgame 1 -> (chicken sweep) count, spawn THIS lap's 50 new
#     chickens during Angel's ~7 s countdown and confirm them -> PresentMon captures the
#     flythrough from 9 s -> chicken count -> next lap. Chickens survive mp_restartgame,
#     so they accumulate within a pass. Cleared once at the start of each pass.
#   - two sweep modes: chicken count (0..500) or host_timescale (1x..12x)
# Results go to .\Results\<date>_<label>_<mode>\  (one CSV per lap + laps.csv).
# Analyse with CB_Analyze.bat.
# =====================================================================

$ErrorActionPreference = 'Stop'
$Version = '1.0.8'
$Root    = Split-Path -Parent $PSScriptRoot

# ---------- Elevation (PresentMon needs admin to read ETW events) ----------
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Requesting administrator rights (PresentMon needs them)...'
    Start-Process powershell.exe -Verb RunAs -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-File', "`"$PSCommandPath`"")
    exit
}

# ---------- Settings ----------
function Read-Settings([string]$path) {
    $s = @{}
    foreach ($line in Get-Content -LiteralPath $path) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith(';') -or $t.StartsWith('#')) { continue }
        $i = $t.IndexOf('=')
        if ($i -lt 1) { continue }
        $s[$t.Substring(0, $i).Trim()] = $t.Substring($i + 1).Trim()
    }
    return $s
}

$SettingsPath = Join-Path $Root 'config\cb_settings.ini'
if (-not (Test-Path -LiteralPath $SettingsPath)) { throw "config\cb_settings.ini not found: $SettingsPath" }
$S = Read-Settings $SettingsPath

$CS2Dir      = $S['CS2Dir']
$SteamExe    = $S['SteamExe']
$WorkshopId  = $S['WorkshopId']
$MapName     = $S['MapName']
$BindKey     = $S['BindKey'].ToUpper()
$CapStart    = [double]$S['CaptureStart']
$CapEnd      = [double]$S['CaptureEnd']
$RestartAt   = [double]$S['RestartAt']
$SpawnConfirmBy = [double]$S['SpawnConfirmBy']    # game seconds after round start (capture starts at CaptureStart)
$ChickenTol    = [double]$S['ChickenTolerancePct'] / 100.0
$ClearAtPassStart = ($S['ClearChickensAtPassStart'] -ne '0')   # default on; 0 = never send the chicken-kill commands
$StageSize     = 50
$CfgDir      = Join-Path $CS2Dir 'game\csgo\cfg'
$ConsoleLog  = Join-Path $CS2Dir 'game\csgo\console.log'
$CmdCfg      = Join-Path $CfgDir 'cb_cmd.cfg'

# Bind key table: name -> CS2 key name, virtual-key code, scan code, extended-key flag.
# Page Down / Insert / Home / End / Delete / Page Up are "extended" keys (E0 prefix):
# without the extended flag Windows reports them as numpad keys.
$KeyTable = @{
    PGDN = @('pgdn', 0x22, 0x51, $true);  PGUP = @('pgup', 0x21, 0x49, $true)
    INS  = @('ins',  0x2D, 0x52, $true);  DEL  = @('del',  0x2E, 0x53, $true)
    HOME = @('home', 0x24, 0x47, $true);  END  = @('end',  0x23, 0x4F, $true)
    F9   = @('F9',   0x78, 0x43, $false); F10  = @('F10',  0x79, 0x44, $false)
    F11  = @('F11',  0x7A, 0x57, $false); F12  = @('F12',  0x7B, 0x58, $false)
}
if (-not $KeyTable.ContainsKey($BindKey)) { throw "BindKey in cb_settings.ini must be one of: $(($KeyTable.Keys | Sort-Object) -join ', ') (got '$BindKey')." }
$Key = $KeyTable[$BindKey]
$BindLine = 'bind {0} "exec cb_cmd"' -f $Key[0]

# ---------- Keyboard + window helpers (SendInput with scan codes) ----------
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class CBInput {
    [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT { public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Explicit)] struct INPUTUNION { [FieldOffset(0)] public MOUSEINPUT mi; [FieldOffset(0)] public KEYBDINPUT ki; }
    [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type; public INPUTUNION u; }
    [DllImport("user32.dll", SetLastError = true)] static extern uint SendInput(uint n, INPUT[] inputs, int size);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);

    public static uint ForegroundPid() { uint pid; GetWindowThreadProcessId(GetForegroundWindow(), out pid); return pid; }

    public static bool TryFocus(IntPtr h) {
        if (h == IntPtr.Zero) return false;
        if (IsIconic(h)) ShowWindow(h, 9);
        keybd_event(0x12, 0, 0, UIntPtr.Zero);      // tap ALT so Windows allows the focus change
        keybd_event(0x12, 0, 2, UIntPtr.Zero);
        SetForegroundWindow(h);
        return GetForegroundWindow() == h;
    }

    static uint One(ushort vk, ushort scan, uint flags) {
        INPUT[] a = new INPUT[1];
        a[0].type = 1; a[0].u.ki.wVk = vk; a[0].u.ki.wScan = scan; a[0].u.ki.dwFlags = flags;
        return SendInput(1, a, Marshal.SizeOf(typeof(INPUT)));
    }

    // Like a real keyboard: scan code (+ extended flag for nav-cluster keys), key down, hold, key up.
    public static uint PressKey(ushort vk, ushort scan, bool extended) {
        uint f = 0x0008 | (extended ? 0x0001u : 0u);          // KEYEVENTF_SCANCODE [| EXTENDEDKEY]
        uint sent = One(vk, scan, f);
        System.Threading.Thread.Sleep(50);
        sent += One(vk, scan, f | 0x0002);                    // KEYUP
        return sent;
    }

    // Types text as characters (KEYEVENTF_UNICODE), like AutoHotkey's {Text} mode.
    public static void TypeText(string s) {
        foreach (char ch in s) {
            One(0, ch, 0x0004);
            One(0, ch, 0x0004 | 0x0002);
            System.Threading.Thread.Sleep(8);
        }
    }
}
'@

# ---------- Logging ----------
$script:RunLog = $null
function Write-Log([string]$msg, [switch]$Quiet, [string]$Color = 'Gray') {
    $line = '{0}  {1}' -f (Get-Date -Format 'HH:mm:ss.fff'), $msg
    if (-not $Quiet) { Write-Host $line -ForegroundColor $Color }
    if ($script:RunLog) { Add-Content -LiteralPath $script:RunLog -Value $line }
}
function Stop-Run([string]$msg) {
    Write-Log "ERROR: $msg" -Color Red
    Write-Host ''
    Write-Host 'Stopped. Fix the problem above and run CB_Run.bat again.' -ForegroundColor Red
    exit 1
}

# ---------- console.log tail + state tracking ----------
$script:LogPos = 0
$script:LogPartial = ''
$script:SpawnSeen = $null      # last 'Using spawn points configuration' (= round start)
$script:MenuSeen = $null       # last change to main menu (= disconnected)
$script:InGameSeen = $null     # last change to in-game
$script:LastFound = -1         # last 'Found N matches.' from ent_find
$script:LastAck = -1           # last 'cb_ack_n' seen (exec error line written by each batch)
$script:InitSeen = $null       # last 'execing cb_init' (= typed console line was executed)

function Get-NewLogLines {
    $out = @()
    if (-not (Test-Path -LiteralPath $ConsoleLog)) { return $out }
    $fs = [System.IO.File]::Open($ConsoleLog, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]'ReadWrite, Delete')
    try {
        if ($fs.Length -lt $script:LogPos) { $script:LogPos = 0 }   # file was recreated
        if ($fs.Length -eq $script:LogPos) { return $out }
        [void]$fs.Seek($script:LogPos, [System.IO.SeekOrigin]::Begin)
        $sr = New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8)
        $text = $sr.ReadToEnd()
        $script:LogPos = $fs.Position     # bytes actually read (not Length: the file may have grown meanwhile)
    } finally { $fs.Close() }
    $text = $script:LogPartial + $text
    $parts = $text -split "`r?`n"
    $script:LogPartial = $parts[$parts.Count - 1]
    if ($parts.Count -gt 1) { $out = $parts[0..($parts.Count - 2)] }
    return $out
}

function Update-State {
    foreach ($l in Get-NewLogLines) {
        if ($l -match 'cb_ack_(\d+)') { $n = [int]$Matches[1]; if ($n -gt $script:LastAck) { $script:LastAck = $n } }
        elseif ($l -match 'execing cb_init') { $script:InitSeen = Get-Date }
        elseif ($l -match 'Using spawn points configuration') { $script:SpawnSeen = Get-Date }
        elseif ($l -match 'Found (\d+) matches') { $script:LastFound = [int]$Matches[1] }
        elseif ($l -match '-> CSGO_GAME_UI_STATE_MAINMENU') { $script:MenuSeen = Get-Date }
        elseif ($l -match '-> CSGO_GAME_UI_STATE_INGAME') { $script:InGameSeen = Get-Date }
    }
}

function Wait-Cond([scriptblock]$cond, [double]$timeoutSec) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        Update-State
        if (& $cond) { return $true }
        Start-Sleep -Milliseconds 30
    }
    Update-State
    return [bool](& $cond)
}

function Wait-UntilTime([datetime]$t) {
    while ((Get-Date) -lt $t) {
        Update-State
        $left = ($t - (Get-Date)).TotalMilliseconds
        if ($left -gt 50) { Start-Sleep -Milliseconds 50 } elseif ($left -gt 0) { Start-Sleep -Milliseconds ([int]$left) }
    }
}

# ---------- Sending commands (cfg file + bound key + echo acknowledgement) ----------
$script:AckSeq = 0
function Get-CS2Window {
    $p = Get-Process -Name cs2 -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero } | Select-Object -First 1
    if ($p) { return $p }
    return $null
}

function Confirm-Focus {
    # Never press a key unless CS2 is the active window.
    $warned = $false
    while ($true) {
        $p = Get-CS2Window
        if (-not $p) { Stop-Run 'The CS2 window is gone (did CS2 crash or close?).' }
        if ([CBInput]::ForegroundPid() -eq [uint32]$p.Id) { return }
        [void][CBInput]::TryFocus($p.MainWindowHandle)
        Start-Sleep -Milliseconds 200
        if ([CBInput]::ForegroundPid() -eq [uint32]$p.Id) { return }
        if (-not $warned) {
            Write-Log '  CS2 is not the active window. Click on the CS2 window - waiting (no keys are sent until it is active)...' -Color Yellow
            [console]::Beep(800, 300)
            $warned = $true
        }
        Start-Sleep -Milliseconds 500
    }
}

function Send-Cmds([string[]]$cmds, [int]$timeoutMs = 2500, [int]$tries = 3) {
    $script:AckSeq++
    $n = $script:AckSeq
    $lines = @('hideconsole') + $cmds + @("exec cb_ack_$n")
    [System.IO.File]::WriteAllText($CmdCfg, (($lines -join "`r`n") + "`r`n"), [System.Text.Encoding]::ASCII)
    foreach ($c in $cmds) { Write-Log "  > $c" -Quiet }
    for ($t = 1; $t -le $tries; $t++) {
        Confirm-Focus
        $pressed = Get-Date
        [void][CBInput]::PressKey([uint16]$Key[1], [uint16]$Key[2], [bool]$Key[3])
        if (Wait-Cond { $script:LastAck -ge $n } ($timeoutMs / 1000.0)) { return $pressed }
        Write-Log ("  no acknowledgement for batch {0} (try {1}/{2})" -f $n, $t, $tries) -Quiet
    }
    return $null
}
function Send-Cmd([string]$cmd) { return (Send-Cmds @($cmd)) }

# ---------- PresentMon ----------
function Find-PresentMon {
    if ($S['PresentMonExe']) {
        if (Test-Path -LiteralPath $S['PresentMonExe']) { return $S['PresentMonExe'] }
        Stop-Run "PresentMonExe in cb_settings.ini does not exist: $($S['PresentMonExe'])"
    }
    $found = Get-ChildItem -LiteralPath (Join-Path $Root 'tools') -Filter 'PresentMon*.exe' -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    if ($found) { return $found.FullName }
    return $null
}

function Start-Capture([string]$outCsv, [int]$secs, [string]$stem) {
    $argLine = $S['PresentMonArgs'].Replace('{out}', $outCsv).Replace('{secs}', [string]$secs)
    $o = Join-Path $script:RunDir ("logs\" + $stem + '_pm_out.txt')
    $e = Join-Path $script:RunDir ("logs\" + $stem + '_pm_err.txt')
    return Start-Process -FilePath $script:PMExe -ArgumentList $argLine -PassThru -NoNewWindow -RedirectStandardOutput $o -RedirectStandardError $e
}

# ---------- Map load / recovery ----------
# Key binds do not fire in the main menu, so the map is loaded by typing one line
# into the console. The line also hides the console (an open console blocks binds)
# and runs cb_init.cfg, which sets the bind. Returns $true when the map is up.
function Invoke-LoadMap {
    $line = 'hideconsole; exec cb_init; map_workshop {0} {1}' -f $WorkshopId, $MapName
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        $script:InGameSeen = $null
        $script:SpawnSeen = $null
        $script:InitSeen = $null
        Confirm-Focus
        if ($attempt -eq 2) {
            Write-Log '  The console was not open. Pressing the console key (~) and typing again...' -Color Yellow
            [void][CBInput]::PressKey(0xC0, 0x29, $false)      # the ` / ~ key (toggleconsole)
            Start-Sleep -Milliseconds 600
        }
        Update-State
        $sent = Get-Date
        [CBInput]::TypeText($line)
        Start-Sleep -Milliseconds 150
        [void][CBInput]::PressKey(0x0D, 0x1C, $false)          # Enter
        Write-Log "  typed into the console: $line" -Quiet
        # The line starts with 'exec cb_init', which logs 'execing cb_init' at once.
        # If that does not appear, the text went nowhere (console closed): retry.
        if (-not (Wait-Cond { $script:InitSeen -and $script:InitSeen -gt $sent } 6)) {
            Write-Log "  Typed line was not executed (attempt $attempt of 2)." -Color Yellow
            continue
        }
        Write-Log '  Map command accepted. Waiting for the map to load...'
        if (Wait-Cond { ($script:InGameSeen -and $script:InGameSeen -gt $sent) -or ($script:SpawnSeen -and $script:SpawnSeen -gt $sent) } 120) {
            Write-Log 'Map loaded. Letting it settle for 8 s...'
            Start-Sleep -Seconds 8
            return $true
        }
        Write-Log '  Map command was accepted but no map-loaded line appeared within 2 minutes.' -Color Yellow
        return $false
    }
    return $false
}

function Invoke-ManualMapLoad {
    Write-Host ''
    Write-Host 'Could not load the map automatically. Please do it by hand:' -ForegroundColor Yellow
    Write-Host "  1. In CS2 open the console (~) and type:   map_workshop $WorkshopId $MapName" -ForegroundColor Yellow
    Write-Host '  2. When the benchmark intro starts, close the console with the ~ key (NOT Escape).' -ForegroundColor Yellow
    Write-Host '  3. Come back here and press Enter. (Then click on CS2 when you hear the beep.)' -ForegroundColor Yellow
    $r = Read-Host 'Press Enter when the map is loaded, or Q to quit'
    if ($r -eq 'Q' -or $r -eq 'q') { Stop-Run 'Map not loaded.' }
    Start-Sleep -Seconds 3
}

# ---------- Chickens ----------
function Get-ChickenCount {
    $script:LastFound = -1
    if (-not (Send-Cmds @('ent_find chicken') 3000)) { return -1 }
    if (Wait-Cond { $script:LastFound -ge 0 } 1.5) { return $script:LastFound }
    return -1
}

function Get-StageCmds([int]$fromStage, [int]$toStage) {
    if ($toStage -lt $fromStage) { return @() }
    return @($fromStage..$toStage | ForEach-Object { 'exec cb_s{0:D2}' -f $_ })
}

# Spawn stages and wait until the count reaches $target (or the deadline), then settle.
# Returns the last count seen (-1 if never read).
function Invoke-Spawn([string[]]$stageCmds, [int]$target, [datetime]$deadline) {
    if ($stageCmds.Count -eq 0) { return -2 }
    if (-not (Send-Cmds $stageCmds 5000)) { Write-Log '  WARNING: chicken spawn batch not acknowledged.' -Color Yellow }
    $n = -1
    while ((Get-Date) -lt $deadline) {
        $n = Get-ChickenCount
        if ($n -ge $target) { break }
        Start-Sleep -Milliseconds 300
    }
    if ($n -lt $target) { Write-Log ("  WARNING: spawn not confirmed before the deadline (count {0}, wanted {1})." -f $n, $target) -Color Yellow }
    return $n
}

# Remove every chicken and (optionally) build up to $level again. Used at the start of
# each pass and after a map reload. Not timed against a lap.
function Set-ChickenLevel([int]$level) {
    if ($ClearAtPassStart) {
        [void](Send-Cmds @('ent_fire chicken kill', 'ent_remove_all chicken') 3000)
        Start-Sleep -Milliseconds 500
    }
    $n = Get-ChickenCount
    if ($n -gt 0) { Write-Log "  WARNING: $n chickens already exist (expected 0)." -Color Yellow }
    if ($level -gt 0) {
        $cmds = Get-StageCmds 1 ([int]($level / $StageSize))
        $n = Invoke-Spawn $cmds $level ((Get-Date).AddSeconds(45))
    }
    Write-Log ("  Chickens ready: {0} (target {1})" -f $n, $level)
}

# Reload the map from in-game through the bound key (typing is only safe in the main menu).
# A freshly loaded map has no chickens, so this gives later passes a clean start without
# sending any chicken-kill commands.
function Invoke-ReloadInGame {
    $script:InGameSeen = $null
    $script:SpawnSeen = $null
    $sent = Get-Date
    [void](Send-Cmds @(("map_workshop {0} {1}" -f $WorkshopId, $MapName)) 3000 1)
    if (Wait-Cond { ($script:InGameSeen -and $script:InGameSeen -gt $sent) -or ($script:SpawnSeen -and $script:SpawnSeen -gt $sent) } 120) {
        Write-Log 'Map reloaded. Letting it settle for 8 s...'
        Start-Sleep -Seconds 8
        return $true
    }
    Write-Log '  WARNING: the map reload was not confirmed; continuing on the current map.' -Color Yellow
    return $false
}

# ---------- One lap ----------
function Invoke-Lap([string]$mode, [int]$level, [int]$pass, [string]$label, [string[]]$spawnStages = @()) {
    $scale = 1.0
    if ($mode -eq 'timescale') { $scale = [double]$level }
    $stem = '{0}_{1}_{2}_p{3}' -f $label, $mode, $level, $pass
    $csv = Join-Path $script:RunDir ("frames\" + $stem + '.csv')

    $script:SpawnSeen = $null
    $lapSent = Send-Cmds @('sv_cheats 1', 'fps_max 0', ("host_timescale {0}" -f $scale), 'mp_restartgame 1')
    if (-not $lapSent) {
        return [pscustomobject]@{ label = $label; mode = $mode; level = $level; pass = $pass; timescale = $scale
            chickens_expected = ''; chickens_found = ''; round_start_detected = 0; capture_seconds = 0
            lap_start = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); frames_csv = ''; status = 'no_ack'
            note = ''; chickens_after_restart = ''; chickens_after_spawn = '' }
    }

    # Round start (t0). mp_restartgame 1 waits 1 game-second.
    # The round-start line is a [Console] line and may not reach console.log; if it does not
    # appear, use the runner's own clock (key press + 1 game-second restart delay).
    $t0Detected = Wait-Cond { $script:SpawnSeen -and $script:SpawnSeen -gt $lapSent } (1.5 + 1 / $scale)
    if ($t0Detected) { $t0 = $script:SpawnSeen } else {
        $t0 = $lapSent.AddSeconds(1 / $scale)
        Write-Log '  round start timed from the key press (round-start line not in console.log)' -Quiet
    }

    # Chicken sweep: count what survived the restart, then add THIS lap's new chickens now,
    # during Angel's ~7 s countdown (as in v1.0.3, which lost none), and confirm they all
    # exist before the capture starts. Only the new 50 are spawned, so the burst is small.
    $afterRestart = ''; $haveRestartCount = $false
    $afterSpawn = '';   $spawnTarget = -1; $spawnNote = ''
    if ($mode -eq 'chickens') {
        Wait-UntilTime ($t0.AddSeconds(0.5))
        $c = Get-ChickenCount
        if ($c -ge 0) { $afterRestart = $c; $haveRestartCount = $true }
        if ($spawnStages.Count -gt 0) {
            $base = $level - $StageSize * $spawnStages.Count
            if ($haveRestartCount) { $base = [int]$afterRestart }
            $spawnTarget = $base + $StageSize * $spawnStages.Count
            $got = Invoke-Spawn $spawnStages $spawnTarget ($t0.AddSeconds($SpawnConfirmBy))
            if ($got -ge 0) { $afterSpawn = $got }
            $spawnNote = "spawned $($StageSize * $spawnStages.Count) after the restart: $got chickens before the capture (wanted $spawnTarget)"
            Write-Log "  $spawnNote"
        } else {
            $afterSpawn = $afterRestart
        }
    }

    # Capture the flythrough
    $capSecs = [int][math]::Max(1, [math]::Floor(($CapEnd - $CapStart) / $scale))
    Wait-UntilTime ($t0.AddSeconds($CapStart / $scale))
    $pm = Start-Capture $csv $capSecs $stem

    # Let the capture finish completely before anything else happens
    Wait-UntilTime ($t0.AddSeconds($CapEnd / $scale))
    if (-not $pm.WaitForExit(5000)) {
        Write-Log '  WARNING: PresentMon still running after the capture window; stopping it.' -Color Yellow
        try { $pm.Kill() } catch {}
    }

    # Chicken count at the end of THIS lap (after the capture; nothing is spawned here any more)
    $found = ''
    $haveCount = $false
    if ($mode -eq 'chickens') {
        $c = Get-ChickenCount
        if ($c -ge 0) { $found = $c; $haveCount = $true }
    }
    Wait-UntilTime ($t0.AddSeconds($RestartAt / $scale))

    $status = 'ok'
    if ($script:MenuSeen -and $script:MenuSeen -gt $lapSent) { $status = 'disconnected' }
    elseif (-not (Test-Path -LiteralPath $csv) -or (Get-Item -LiteralPath $csv).Length -lt 1024) { $status = 'no_frames' }
    elseif ($spawnTarget -ge 0 -and ($afterSpawn -eq '' -or [int]$afterSpawn -lt $spawnTarget)) { $status = 'spawn_unconfirmed' }
    elseif ($mode -eq 'chickens' -and $haveCount -and ([int]$found -lt [math]::Floor($level * (1 - $ChickenTol)))) { $status = 'chickens_lost' }
    elseif ($mode -eq 'chickens' -and $haveCount -and ([int]$found -gt [math]::Ceiling($level * (1 + $ChickenTol)))) { $status = 'chickens_extra' }

    return [pscustomobject]@{
        label = $label; mode = $mode; level = $level; pass = $pass; timescale = $scale
        chickens_expected = $(if ($mode -eq 'chickens') { $level } else { '' })
        chickens_found = $found
        round_start_detected = [int][bool]$t0Detected
        capture_seconds = $capSecs
        lap_start = $lapSent.ToString('yyyy-MM-dd HH:mm:ss')
        frames_csv = ('frames\' + $stem + '.csv')
        status = $status
        note = $spawnNote
        chickens_after_restart = $afterRestart
        chickens_after_spawn = $afterSpawn
    }
}

# =====================================================================
# Menu
# =====================================================================
Clear-Host
Write-Host "ChickenBench v$Version" -ForegroundColor Cyan
Write-Host "  Angel's CS2 FPS BENCHMARK DUST2, looped, with PresentMon capture"
Write-Host ''
Write-Host ("  [1] Chicken sweep    {0}" -f ($S['ChickenLevels'] -replace ',', ' / '))
Write-Host ("  [2] Timescale sweep  {0}" -f (($S['TimescaleLevels'] -split ',' | ForEach-Object { $_.Trim() + 'x' }) -join ' / '))
Write-Host '  [3] Quick test       one 0-chicken lap (checks command link + capture)'
Write-Host ''
$choice = Read-Host 'Choose 1, 2 or 3'
switch ($choice) {
    '1' { $mode = 'chickens';  $levels = @($S['ChickenLevels'] -split ',' | ForEach-Object { [int]$_.Trim() }) }
    '2' { $mode = 'timescale'; $levels = @($S['TimescaleLevels'] -split ',' | ForEach-Object { [int]$_.Trim() }) }
    '3' { $mode = 'chickens';  $levels = @(0) }
    default { Stop-Run "Unknown choice '$choice'." }
}

if ($choice -eq '3') { $label = 'TEST'; $passes = 1 } else {
    $label = Read-Host 'Config label (e.g. TUNED or JEDEC)'
    $label = ($label -replace '[^A-Za-z0-9_-]', '')
    if (-not $label) { Stop-Run 'A config label is required.' }
    $p = Read-Host ("Passes [{0}]" -f $S['Passes'])
    if ($p) { $passes = [int]$p } else { $passes = [int]$S['Passes'] }
    if ($passes -lt 1) { Stop-Run 'Passes must be 1 or more.' }
}

# Lap order. Timescale: alternate ascending / descending each pass to cancel drift.
# Chickens: always ascending (chickens accumulate within a pass; cleared at pass start).
$levels = @($levels | Sort-Object)
$laps = New-Object System.Collections.ArrayList
for ($pp = 1; $pp -le $passes; $pp++) {
    $order = $levels
    if ($mode -eq 'timescale' -and $pp % 2 -eq 0) { $order = $levels[($levels.Count - 1)..0] }
    foreach ($lv in $order) { [void]$laps.Add(@($pp, $lv)) }
}
$estSec = 0
foreach ($l in $laps) { $sc = 1.0; if ($mode -eq 'timescale') { $sc = [double]$l[1] }; $estSec += $RestartAt / $sc + 4 }
Write-Host ''
Write-Host ("{0} laps, about {1:N0} minutes plus CS2 start-up and map load." -f $laps.Count, (($estSec + 120) / 60)) -ForegroundColor Cyan
Write-Host 'Before you continue: same Adrenalin tuning profile as your other runs, CS2 video settings unchanged,' -ForegroundColor Yellow
Write-Host "nothing else running. Do not touch the PC while it runs: the runner presses $BindKey in the CS2 window." -ForegroundColor Yellow
[void](Read-Host 'Press Enter to start (Ctrl+C to cancel)')

# =====================================================================
# Pre-flight checks
# =====================================================================
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$script:RunDir = Join-Path $Root ("Results\{0}_{1}_{2}" -f $stamp, $label, $mode)
New-Item -ItemType Directory -Force -Path (Join-Path $script:RunDir 'frames'), (Join-Path $script:RunDir 'logs') | Out-Null
$script:RunLog = Join-Path $script:RunDir 'logs\runner.log'
Write-Log "ChickenBench v$Version  mode=$mode  label=$label  passes=$passes  levels=$($levels -join ',')"

if (-not (Test-Path -LiteralPath $SteamExe)) { Stop-Run "Steam not found at $SteamExe (edit SteamExe in cb_settings.ini)." }
if (-not (Test-Path -LiteralPath (Join-Path $CS2Dir 'game\csgo'))) { Stop-Run "CS2 not found at $CS2Dir (edit CS2Dir in cb_settings.ini)." }
$vpk = Join-Path (Split-Path (Split-Path $CS2Dir -Parent) -Parent) ("workshop\content\730\{0}\{0}_dir.vpk" -f $WorkshopId)
if (-not (Test-Path -LiteralPath $vpk)) { Stop-Run "Benchmark map not downloaded: $vpk  (subscribe to it in the Workshop and let Steam download it)." }
if ($mode -eq 'chickens') {
    foreach ($lv in $levels) { if ($lv % $StageSize -ne 0) { Stop-Run "Chicken levels must be multiples of $StageSize (got $lv)." } }
    $maxStage = [int](($levels | Measure-Object -Maximum).Maximum / $StageSize)
    for ($k = 1; $k -le $maxStage; $k++) {
        $src = Join-Path $Root ('config\cs2_cfg\cb_s{0:D2}.cfg' -f $k)
        if (-not (Test-Path -LiteralPath $src)) { Stop-Run "Missing chicken stage file in the package: $src" }
        try { Copy-Item -LiteralPath $src -Destination $CfgDir -Force } catch { Stop-Run "Cannot copy $src to $CfgDir : $($_.Exception.Message)" }
    }
    Write-Log "Installed $maxStage chicken stage files (cb_s01..cb_s$('{0:D2}' -f $maxStage)) in the CS2 cfg folder." -Quiet
}
$script:PMExe = Find-PresentMon
if (-not $script:PMExe) { Stop-Run "PresentMon not found. Put PresentMon-x.x.x-x64.exe in $(Join-Path $Root 'tools') (see README)." }
Write-Log "PresentMon: $script:PMExe"
if (-not (Get-Process -Name steam -ErrorAction SilentlyContinue)) { Stop-Run 'Steam is not running. Start Steam (not as administrator), then run again.' }
if (Get-Process -Name cs2 -ErrorAction SilentlyContinue) { Stop-Run 'CS2 is already running. Close it first so it can be started with the benchmark options.' }

# Command files: cb_init.cfg (run at launch, sets the bind) and an empty cb_cmd.cfg
try {
    [System.IO.File]::WriteAllText((Join-Path $CfgDir 'cb_init.cfg'), ("// ChickenBench v$Version - run at launch via +exec cb_init`r`n" + $BindLine + "`r`necho CB_INIT_DONE`r`n"), [System.Text.Encoding]::ASCII)
    [System.IO.File]::WriteAllText($CmdCfg, "// ChickenBench v$Version - rewritten by the runner for every command batch`r`n", [System.Text.Encoding]::ASCII)
} catch { Stop-Run "Cannot write to the CS2 cfg folder ($CfgDir): $($_.Exception.Message)" }

# Run info (hardware snapshot)
$info = @()
$info += "ChickenBench v$Version"
$info += "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$info += "Mode: $mode   Label: $label   Passes: $passes   Levels: $($levels -join ',')"
try { $info += "CPU: " + ((Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name) -join '; ') } catch {}
try { $info += "GPU: " + ((Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join '; ') } catch {}
try {
    foreach ($m in Get-CimInstance Win32_PhysicalMemory) {
        $info += ("RAM: {0} {1} GB  rated {2} MT/s  configured {3} MT/s" -f ("$($m.PartNumber)").Trim(), [math]::Round($m.Capacity / 1GB), $m.Speed, $m.ConfiguredClockSpeed)
    }
} catch {}
try { $os = Get-CimInstance Win32_OperatingSystem; $info += "Windows: $($os.Caption) build $($os.BuildNumber)" } catch {}
$info += "Settings: " + (($S.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ' | ')
$info | Set-Content -LiteralPath (Join-Path $script:RunDir 'run_info.txt')
$info | ForEach-Object { Write-Log $_ -Quiet }

# =====================================================================
# Launch CS2
# =====================================================================
if (Test-Path -LiteralPath $ConsoleLog) {
    try { Move-Item -LiteralPath $ConsoleLog -Destination ($ConsoleLog + '.prev') -Force } catch { Remove-Item -LiteralPath $ConsoleLog -Force -ErrorAction SilentlyContinue }
}
$script:LogPos = 0
Write-Log 'Starting CS2 through Steam...' -Color Cyan
Start-Process -FilePath $SteamExe -ArgumentList @('-applaunch', '730', '-condebug', '-console', '+con_enable', '1', '+exec', 'cb_init')

if (-not (Wait-Cond { [bool](Get-CS2Window) } 180)) { Stop-Run 'The CS2 window did not appear within 3 minutes.' }
Write-Log 'CS2 window is up. Waiting for the main menu...'
if (-not (Wait-Cond { $script:MenuSeen } 180)) { Write-Log '  Main menu line not seen in console.log; continuing anyway.' -Color Yellow }
Start-Sleep -Seconds 5

# Load the map (typed into the console - binds do not work in the main menu)
Write-Log "Loading map: map_workshop $WorkshopId $MapName" -Color Cyan
if (-not (Invoke-LoadMap)) { Invoke-ManualMapLoad }

# Verify the command link in-game: write a test batch, press the key, wait for the echo
Write-Log "Testing the command link ($BindKey -> exec cb_cmd)..."
$ok = Send-Cmds @('echo CB_LINK_TEST') 2500 3
while (-not $ok) {
    Write-Host ''
    Write-Host "CS2 did not respond to $BindKey (in-game)." -ForegroundColor Yellow
    Write-Host "  1. In CS2 open the console (~) and type exactly:   $BindLine" -ForegroundColor Yellow
    Write-Host '  2. Close the console with the ~ key (NOT Escape - Escape opens the pause menu, which blocks binds).' -ForegroundColor Yellow
    Write-Host '  3. Come back here and press Enter, then click on CS2 when you hear the beep.' -ForegroundColor Yellow
    $r = Read-Host 'Enter = retry, Q = quit'
    if ($r -eq 'Q' -or $r -eq 'q') { Stop-Run 'Command link not working.' }
    $ok = Send-Cmds @('echo CB_LINK_TEST') 2500 3
}
Write-Log 'Command link verified (key press -> cfg executed -> echo seen in console.log).' -Color Green

# =====================================================================
# Laps
# =====================================================================
$lapsCsv = Join-Path $script:RunDir 'laps.csv'
$i = 0
$prevLevel = 0
foreach ($l in $laps) {
    $i++
    $pass = $l[0]; $level = $l[1]
    $unit = ''; if ($mode -eq 'timescale') { $unit = 'x' } else { $unit = ' chickens' }

    # Chicken sweep: chickens accumulate within a pass. Each lap spawns only its own new
    # stages, right after its restart. Cleared once at the start of each pass.
    $spawnStages = @()
    if ($mode -eq 'chickens') {
        $isFirstOfPass = ($i -eq 1) -or ($laps[$i - 2][0] -ne $pass)
        if ($isFirstOfPass) {
            if ($pass -gt 1 -and -not $ClearAtPassStart) {
                Write-Log "Pass $pass : reloading the map for a chicken-free start (clearing is off)..." -Color Cyan
                [void](Invoke-ReloadInGame)
            }
            Write-Log "Pass $pass : clearing chickens..." -Color Cyan
            Set-ChickenLevel 0
            $prevLevel = 0
        }
        $spawnStages = Get-StageCmds ([int]($prevLevel / $StageSize) + 1) ([int]($level / $StageSize))
    }

    Write-Log ("Lap {0}/{1}: pass {2}, {3}{4}" -f $i, $laps.Count, $pass, $level, $unit) -Color Cyan
    $r = Invoke-Lap $mode $level $pass $label $spawnStages
    if ($r.status -eq 'disconnected') {
        # Back at the main menu: reload the map (typed - binds do not work there), retry once.
        # A reload removes all chickens, so the retry spawns every stage up to this level.
        Write-Log '  Lap failed (CS2 left the map). Reloading the map and retrying once...' -Color Yellow
        $script:MenuSeen = $null
        if (-not (Invoke-LoadMap)) { Invoke-ManualMapLoad }
        $retryStages = @()
        if ($mode -eq 'chickens') { $retryStages = Get-StageCmds 1 ([int]($level / $StageSize)) }
        $r = Invoke-Lap $mode $level $pass $label $retryStages
    } elseif ($r.status -eq 'no_ack') {
        # Still in-game but the restart was not confirmed: nothing was spawned; retry once.
        Write-Log '  Lap failed (command not confirmed). Retrying once...' -Color Yellow
        $r = Invoke-Lap $mode $level $pass $label $spawnStages
    }
    if ($mode -eq 'chickens') { $prevLevel = $level }
    $r | Export-Csv -LiteralPath $lapsCsv -NoTypeInformation -Append -Force
    $color = 'Green'; if ($r.status -ne 'ok') { $color = 'Yellow' }
    $extra = ''
    if ($mode -eq 'chickens') {
        $extra = "  chickens: after restart $($r.chickens_after_restart), after spawn $($r.chickens_after_spawn), at end $($r.chickens_found)"
    }
    Write-Log ("  -> {0}{1}" -f $r.status, $extra) -Color $color
}

Write-Log 'All laps done.' -Color Green
if ($S['QuitWhenDone'] -eq '1') { [void](Send-Cmds @('quit') 1000 1) }
Write-Host ''
Write-Host "Results: $script:RunDir" -ForegroundColor Cyan
Write-Host 'Run CB_Analyze.bat to build the report (after you have runs for each RAM config).' -ForegroundColor Cyan
