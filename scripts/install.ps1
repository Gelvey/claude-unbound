param(
    [switch] $VoiceNim,
    [switch] $VoiceLocal,
    [switch] $VoiceAll,
    [string] $TorchBackend = "",
    [switch] $DryRun,
    [switch] $Help,
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]] $RemainingArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Default install target for Claude Unbound.
# Clones the repo to ~/claude-unbound and creates wrapper .cmd files in
# ~/.local/bin/ that invoke `uv run` from the live source tree. This
# ensures source changes are picked up immediately without reinstalling.
#
# Can be overridden via $env:FCC_REPO_URL. When install.ps1 is executed
# from inside a git checkout whose `origin` remote is NOT
# Gelvey/claude-unbound, the installer refuses to silently fall back to the
# canonical URL — pass $env:FCC_REPO_URL pointing at the fork that
# publishes the repository.
$DefaultRepoHttpsUrl = "https://github.com/Gelvey/claude-unbound"

$PythonVersion = "3.14.0"
$MinUvVersion = "0.11.0"
$UvInstallUrl = "https://astral.sh/uv/install.ps1"

function Show-Usage {
    @"
Usage: install.ps1 [options]

Installs Claude Code and Codex if missing, installs or updates uv, Python 3.14.0, and Claude Unbound.

Options:
  -VoiceNim              Install NVIDIA NIM voice transcription support.
  -VoiceLocal            Install local Whisper voice transcription support.
  -VoiceAll              Install all voice transcription backends.
  -TorchBackend VALUE    Use a uv PyTorch backend, such as cu130. Requires local voice.
  -DryRun                Print commands without running them.
  -Help                  Show this help text.

Environment:
  `$env:FCC_REPO_URL = '<https url>'
      Overrides the install source for the Claude Unbound repository.
      Required when running from a non-upstream fork clone (otherwise the
      installer aborts with an error). The git+ prefix is stripped
      automatically for backward compatibility.
  `$env:FCC_REPO_DIR = '<path>'
      Overrides the clone target directory. Default: ~/claude-unbound.
"@
}

function Write-Step {
    param([string] $Message)

    Write-Host ""
    Write-Host "==> $Message"
}

function Format-Argument {
    param([string] $Value)

    if ($Value -match '^[A-Za-z0-9_./:@%+=,\[\]-]+$') {
        return $Value
    }

    return "'" + ($Value -replace "'", "''") + "'"
}

function Invoke-InstallCommand {
    param(
        [string] $FilePath,
        [string[]] $Arguments = @()
    )

    $parts = @($FilePath) + $Arguments
    $commandText = ($parts | ForEach-Object { Format-Argument ([string] $_) }) -join " "
    Write-Host "+ $commandText"

    if (-not $DryRun) {
        & $FilePath @Arguments
    }
}

function Invoke-UvInstaller {
    Write-Host "+ irm $UvInstallUrl | iex"

    if (-not $DryRun) {
        Invoke-RestMethod $UvInstallUrl | Invoke-Expression
    }
}

function Add-PathEntry {
    param([string] $PathEntry)

    if ([string]::IsNullOrWhiteSpace($PathEntry)) {
        return
    }

    $separator = [IO.Path]::PathSeparator
    $entries = @()
    if (-not [string]::IsNullOrEmpty($env:Path)) {
        $entries = $env:Path -split [regex]::Escape([string] $separator)
    }

    if ($entries -notcontains $PathEntry) {
        $env:Path = "$PathEntry$separator$env:Path"
    }
}

function Add-UvToPath {
    Add-PathEntry (Join-Path $HOME ".local\bin")
    Add-PathEntry (Join-Path $HOME ".cargo\bin")
}

function Assert-CommandAvailable {
    param([string] $Name)

    if ((-not $DryRun) -and (-not (Get-Command $Name -ErrorAction SilentlyContinue))) {
        throw "$Name is required. Install it first, then rerun this installer."
    }
}

function Invoke-ProbeCommand {
    param(
        [string] $FilePath,
        [string[]] $Arguments = @()
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    try {
        $output = & $FilePath @Arguments 2>$null
        return [pscustomobject] @{
            ExitCode = $LASTEXITCODE
            Output = ($output | Out-String)
        }
    }
    catch {
        return [pscustomobject] @{
            ExitCode = 1
            Output = ""
        }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Get-InstalledUvVersion {
    $version = ""

    $selfVersionProbe = Invoke-ProbeCommand -FilePath "uv" -Arguments @("self", "version", "--short")
    if ($selfVersionProbe.ExitCode -eq 0) {
        $version = $selfVersionProbe.Output.Trim()
    }

    if ([string]::IsNullOrWhiteSpace($version)) {
        $versionProbe = Invoke-ProbeCommand -FilePath "uv" -Arguments @("--version")
        if (($versionProbe.ExitCode -eq 0) -and ($versionProbe.Output -match '^uv\s+([^\s]+)')) {
            $version = $Matches[1]
        }
    }

    if ([string]::IsNullOrWhiteSpace($version)) {
        throw "Unable to determine uv version."
    }

    return $version
}

function Test-UvVersionAtLeast {
    param(
        [string] $Version,
        [string] $Minimum
    )

    $normalizedVersion = $Version -replace '[-+].*$', ''
    $normalizedMinimum = $Minimum -replace '[-+].*$', ''
    return ([version] $normalizedVersion) -ge ([version] $normalizedMinimum)
}

function Test-UvVersionSatisfiesMinimum {
    $version = Get-InstalledUvVersion
    return Test-UvVersionAtLeast -Version $version -Minimum $MinUvVersion
}

function Assert-MinUvVersion {
    if ($DryRun) {
        return
    }

    $version = Get-InstalledUvVersion
    if (-not (Test-UvVersionAtLeast -Version $version -Minimum $MinUvVersion)) {
        throw "uv $MinUvVersion or newer is required; found uv $version. Upgrade uv with its installer or package manager, then rerun this installer."
    }
}

function Test-UvSelfUpdateSupported {
    $probe = Invoke-ProbeCommand -FilePath "uv" -Arguments @("self", "update", "--dry-run")
    return $probe.ExitCode -eq 0
}

function Test-UvInstalledByScoop {
    if (-not (Get-Command scoop -ErrorAction SilentlyContinue)) {
        return $false
    }

    $probe = Invoke-ProbeCommand -FilePath "scoop" -Arguments @("list", "uv")
    return ($probe.ExitCode -eq 0) -and ($probe.Output -match '(^|\s)uv(\s|$)')
}

function Test-UvInstalledByWinget {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        return $false
    }

    $probe = Invoke-ProbeCommand -FilePath "winget" -Arguments @("list", "--id", "astral-sh.uv", "-e")
    return ($probe.ExitCode -eq 0) -and ($probe.Output -match 'astral-sh\.uv')
}

function Test-UvInstalledByPipx {
    if (-not (Get-Command pipx -ErrorAction SilentlyContinue)) {
        return $false
    }

    $probe = Invoke-ProbeCommand -FilePath "pipx" -Arguments @("list")
    return ($probe.ExitCode -eq 0) -and ($probe.Output -match '(?m)\bpackage uv\b')
}

function Test-UvInstalledInActiveVirtualenv {
    if ([string]::IsNullOrWhiteSpace($env:VIRTUAL_ENV)) {
        return $false
    }

    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCommand) {
        return $false
    }

    $uvPath = [IO.Path]::GetFullPath($uvCommand.Source)
    $venvPath = ([IO.Path]::GetFullPath($env:VIRTUAL_ENV)).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $nativePrefix = "$venvPath$([IO.Path]::DirectorySeparatorChar)"
    $alternatePrefix = "$venvPath$([IO.Path]::AltDirectorySeparatorChar)"

    return $uvPath.StartsWith($nativePrefix, [StringComparison]::OrdinalIgnoreCase) -or
        $uvPath.StartsWith($alternatePrefix, [StringComparison]::OrdinalIgnoreCase)
}

function Update-ExistingUv {
    if (Test-UvSelfUpdateSupported) {
        Invoke-InstallCommand -FilePath "uv" -Arguments @("self", "update")
        return
    }

    if (Test-UvInstalledByScoop) {
        Invoke-InstallCommand -FilePath "scoop" -Arguments @("update", "uv")
        return
    }

    if (Test-UvInstalledByWinget) {
        Invoke-InstallCommand -FilePath "winget" -Arguments @(
            "upgrade",
            "--id",
            "astral-sh.uv",
            "-e",
            "--accept-package-agreements",
            "--accept-source-agreements"
        )
        return
    }

    if (Test-UvInstalledByPipx) {
        Invoke-InstallCommand -FilePath "pipx" -Arguments @("upgrade", "uv")
        return
    }

    if (Test-UvInstalledInActiveVirtualenv) {
        Invoke-InstallCommand -FilePath "python" -Arguments @("-m", "pip", "install", "--upgrade", "uv")
        return
    }

    if (Test-UvVersionSatisfiesMinimum) {
        Write-Host "uv is already installed and satisfies >=$MinUvVersion; skipping automatic uv update because the install source was not detected."
        return
    }

    $version = "unknown"
    try {
        $version = Get-InstalledUvVersion
    }
    catch {
        $version = "unknown"
    }
    throw "uv $MinUvVersion or newer is required; found uv $version. The existing uv install source was not detected. Upgrade uv manually with the package manager that installed it, then rerun this installer."
}

# Resolve the HTTPS clone URL for the Claude Unbound repository.
# Priority (highest first):
#   1. $env:FCC_REPO_URL override (always wins; strips git+ prefix for
#      backward compatibility).
#   2. Inside a git checkout whose `origin` remote is Gelvey/claude-unbound
#      -> use the canonical URL.
#   3. Inside a git checkout whose `origin` remote is anything ELSE
#      (i.e. a different fork) -> REFUSE silent fallback. Print a clear
#      error pointing at $env:FCC_REPO_URL so the user does not
#      unknowingly install a different repo's code.
#   4. Not inside a git checkout (e.g. `irm ... | iex`) -> use canonical
#      URL.
function Resolve-RepoHttpsUrl {
    if (-not [string]::IsNullOrWhiteSpace($env:FCC_REPO_URL)) {
        # Strip git+ prefix if present (backward compat with old FCC_REPO_URL values)
        $url = $env:FCC_REPO_URL -replace '^git\+', ''
        return $url
    }

    $scriptInfo = $MyInvocation.MyCommand.Path
    $scriptDirectory = if ($scriptInfo) { Split-Path -Parent $scriptInfo } else { "." }
    try {
        $scriptDirectory = (Resolve-Path -LiteralPath $scriptDirectory -ErrorAction Stop).ProviderPath
    } catch {
        $scriptDirectory = "."
    }

    if (Get-Command git -ErrorAction SilentlyContinue) {
        $insideWorkTree = Invoke-ProbeCommand -FilePath "git" -Arguments @(
            "-C", $scriptDirectory, "rev-parse", "--is-inside-work-tree"
        )
        if ($insideWorkTree.ExitCode -eq 0) {
            $originProbe = Invoke-ProbeCommand -FilePath "git" -Arguments @(
                "-C", $scriptDirectory, "config", "--get", "remote.origin.url"
            )
            $originUrl = if ($originProbe.ExitCode -eq 0) { $originProbe.Output.Trim() } else { "" }

            if (-not [string]::IsNullOrWhiteSpace($originUrl)) {
                if ($originUrl -match "Gelvey/claude-unbound") {
                    return $DefaultRepoHttpsUrl
                }
                [Console]::Error.WriteLine("error: non-canonical fork clone detected.")
                [Console]::Error.WriteLine("error: git origin: $originUrl")
                [Console]::Error.WriteLine("error: refusing to silently fall back to the canonical install URL.")
                [Console]::Error.WriteLine("error: re-run with `$env:FCC_REPO_URL pointing at the fork that publishes the repo, e.g.")
                [Console]::Error.WriteLine("error:   `$env:FCC_REPO_URL = 'https://github.com/YourUser/your-fork'")
                throw "non-canonical clone detected; FCC_REPO_URL is required"
            }
        }
    }

    return $DefaultRepoHttpsUrl
}

# Resolve the actual repository directory. If running from inside a git
# repo, returns that repo's toplevel. Otherwise returns the standard
# clone location.
function Resolve-RepoDir {
    $scriptInfo = $MyInvocation.MyCommand.Path
    $scriptDirectory = if ($scriptInfo) { Split-Path -Parent $scriptInfo } else { "." }
    try {
        $scriptDirectory = (Resolve-Path -LiteralPath $scriptDirectory -ErrorAction Stop).ProviderPath
    } catch {
        $scriptDirectory = "."
    }

    if (Get-Command git -ErrorAction SilentlyContinue) {
        $toplevelProbe = Invoke-ProbeCommand -FilePath "git" -Arguments @(
            "-C", $scriptDirectory, "rev-parse", "--show-toplevel"
        )
        if ($toplevelProbe.ExitCode -eq 0) {
            $toplevel = $toplevelProbe.Output.Trim()
            if (-not [string]::IsNullOrWhiteSpace($toplevel)) {
                return $toplevel
            }
        }
    }

    # Standard location
    $repoDir = if (-not [string]::IsNullOrEmpty($env:FCC_REPO_DIR)) {
        $env:FCC_REPO_DIR
    } else {
        Join-Path $HOME "claude-unbound"
    }
    return $repoDir
}

function Install-ClaudeIfMissing {
    if (Get-Command claude -ErrorAction SilentlyContinue) {
        Write-Host "Claude Code already found on PATH; skipping install."
        return
    }

    Assert-CommandAvailable "npm"
    Invoke-InstallCommand -FilePath "npm" -Arguments @("install", "-g", "@anthropic-ai/claude-code")
}

function Install-CodexIfMissing {
    if (Get-Command codex -ErrorAction SilentlyContinue) {
        Write-Host "Codex already found on PATH; skipping install."
        return
    }

    Assert-CommandAvailable "npm"
    Invoke-InstallCommand -FilePath "npm" -Arguments @("install", "-g", "@openai/codex")
}

function Install-OrUpdateUv {
    Add-UvToPath

    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Update-ExistingUv
        Assert-MinUvVersion
        return
    }

    Invoke-UvInstaller
    Add-UvToPath

    if ((-not $DryRun) -and (-not (Get-Command uv -ErrorAction SilentlyContinue))) {
        throw "uv was installed, but it is not available on PATH. Open a new terminal or add uv's bin directory to PATH."
    }

    Assert-MinUvVersion
}

# Clone or update the Claude Unbound repository.
# In dev mode (running from inside the repo), creates a junction so
# wrappers have a stable path. In standard mode, clones or updates.
function Clone-OrUpdateRepo {
    param(
        [string] $RepoDir,
        [string] $RepoUrl
    )

    $actualRepoDir = Resolve-RepoDir
    $fccHome = Join-Path $HOME ".fcc"

    if ($actualRepoDir -ne $RepoDir) {
        # Developer mode: script is running from inside the repo.
        # Create a junction so the wrappers have a stable path.
        if ((Test-Path $RepoDir) -and (-not (Test-Path $RepoDir -Type Container))) {
            throw "$RepoDir exists but is not a directory. Remove it or set `$env:FCC_REPO_DIR."
        }
        if (-not (Test-Path $RepoDir)) {
            Invoke-InstallCommand -FilePath "cmd" -Arguments @("/c", "mklink", "/J", $RepoDir, $actualRepoDir)
        }
        # Record dev mode for uninstall.ps1
        New-Item -ItemType Directory -Path $fccHome -Force | Out-Null
        Set-Content -Path (Join-Path $fccHome ".install_mode") -Value "dev"
        return
    }

    # Standard mode: clone or update
    New-Item -ItemType Directory -Path $fccHome -Force | Out-Null
    Set-Content -Path (Join-Path $fccHome ".install_mode") -Value "clone"

    if (Test-Path (Join-Path $RepoDir ".git")) {
        Write-Host "Repository already exists at $RepoDir; updating..."
        if (-not $DryRun) {
            Push-Location $RepoDir
            try {
                & git pull --ff-only 2>$null
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "WARNING: git pull failed (local modifications?). Continuing with existing checkout."
                }
            } finally {
                Pop-Location
            }
        }
    } else {
        if (Test-Path $RepoDir) {
            throw "$RepoDir exists but is not a git repository. Remove it manually and rerun."
        }
        Invoke-InstallCommand -FilePath "git" -Arguments @("clone", $RepoUrl, $RepoDir)
    }
}

# Create wrapper .cmd files in ~/.local/bin/ that invoke uv run from the
# live source tree. This ensures source changes are picked up immediately.
function Create-Wrappers {
    $repoDir = if (-not [string]::IsNullOrEmpty($env:FCC_REPO_DIR)) {
        $env:FCC_REPO_DIR
    } else {
        Join-Path $HOME "claude-unbound"
    }
    $binDir = Join-Path $HOME ".local\bin"
    New-Item -ItemType Directory -Path $binDir -Force | Out-Null

    foreach ($cmd in @("fcc-server", "fcc-claude", "fcc-codex", "fcc-init", "free-claude-code")) {
        $wrapperPath = Join-Path $binDir "$cmd.cmd"
        $wrapperContent = @"
@echo off
REM Auto-generated by install.ps1 — edits will be overwritten on next install.
pushd "$repoDir"
uv run --project "$repoDir" $cmd %*
popd
"@
        Set-Content -Path $wrapperPath -Value $wrapperContent -Encoding ascii
        Write-Host "Created wrapper: $wrapperPath"
    }
}

# Install voice extras into the project venv via uv sync.
function Sync-RepoExtras {
    $repoDir = if (-not [string]::IsNullOrEmpty($env:FCC_REPO_DIR)) {
        $env:FCC_REPO_DIR
    } else {
        Join-Path $HOME "claude-unbound"
    }

    $extras = @()
    if ($VoiceAll) {
        $extras = @("voice", "voice_local")
    } elseif ($VoiceNim -and $VoiceLocal) {
        $extras = @("voice", "voice_local")
    } elseif ($VoiceNim) {
        $extras = @("voice")
    } elseif ($VoiceLocal) {
        $extras = @("voice_local")
    }

    $syncArgs = @("sync", "--directory", $repoDir)
    foreach ($extra in $extras) {
        $syncArgs += @("--extra", $extra)
    }
    if (-not [string]::IsNullOrWhiteSpace($TorchBackend)) {
        $syncArgs += @("--torch-backend", $TorchBackend)
    }

    Invoke-InstallCommand -FilePath "uv" -Arguments $syncArgs
}

if ($Help) {
    Show-Usage
    return
}

if ($RemainingArgs.Count -gt 0) {
    Show-Usage
    throw "Unknown option: $($RemainingArgs -join ' ')"
}

if ((-not [string]::IsNullOrWhiteSpace($TorchBackend)) -and (-not ($VoiceLocal -or $VoiceAll))) {
    throw "-TorchBackend requires -VoiceLocal or -VoiceAll."
}

# Resolve AFTER argv parsing (so -Help and bad-arg throws above exit first)
# and BEFORE any side-effectful step (claude/codex/uv) so a fork-context
# error aborts cleanly without touching the user's system.
$RepoHttpsUrl = Resolve-RepoHttpsUrl
$RepoDir = if (-not [string]::IsNullOrEmpty($env:FCC_REPO_DIR)) {
    $env:FCC_REPO_DIR
} else {
    Join-Path $HOME "claude-unbound"
}

Write-Step "Installing Claude Code if missing"
Install-ClaudeIfMissing

Write-Step "Installing Codex if missing"
Install-CodexIfMissing

Write-Step "Installing uv if missing, updating if present"
Install-OrUpdateUv

Write-Step "Installing Python $PythonVersion"
Invoke-InstallCommand -FilePath "uv" -Arguments @("python", "install", $PythonVersion)

Write-Step "Cloning or updating Claude Unbound repository"
Clone-OrUpdateRepo -RepoDir $RepoDir -RepoUrl $RepoHttpsUrl

Write-Step "Creating wrapper scripts"
Create-Wrappers

Write-Step "Syncing project dependencies"
Sync-RepoExtras

Write-Host ""
Write-Host "Claude Unbound is installed. Start the proxy with: fcc-server"
Write-Host "Run Claude Code with: fcc-claude"
Write-Host "Run Codex with: fcc-codex"
Write-Host ""
Write-Host "MCP Router: not available on Windows (requires Unix sockets)."
Write-Host "  Use WSL or a Linux VM for MCP Router features."
