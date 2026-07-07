param(
    [switch] $DryRun,
    [switch] $Help,
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]] $RemainingArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$PackageName = "free-claude-code"
$FccHomeDirname = ".fcc"
$FccCommands = @(
    "fcc-server",
    "fcc-claude",
    "fcc-codex",
    "fcc-init",
    "free-claude-code"
)
$RepoDir = if (-not [string]::IsNullOrEmpty($env:FCC_REPO_DIR)) {
    $env:FCC_REPO_DIR
} else {
    Join-Path $HOME "claude-unbound"
}
$McpRouterDir = Join-Path $HOME ".mcp-router"

function Show-Usage {
    @"
Usage: uninstall.ps1 [options]

Removes Claude Unbound: wrapper scripts, repository clone, MCP Router state,
and the ~/.fcc/ config directory.
Does not remove uv, Claude Code, Codex, or the uv-managed Python runtime.

Options:
  -DryRun                Print commands without running them.
  -Help                  Show this help text.

Environment:
  `$env:FCC_REPO_DIR = '<path>'
      Override the repository directory to remove. Default: ~/claude-unbound.
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

function Test-MissingUvToolError {
    param([string] $Output)

    $normalized = $Output.ToLowerInvariant()
    return (
        $normalized.Contains("not installed") -or
        $normalized.Contains("no tool") -or
        $normalized.Contains("nothing to uninstall")
    )
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

function Assert-NoFccProcessesRunning {
    $running = @()

    foreach ($commandName in $FccCommands) {
        $processes = @(Get-Process -Name $commandName -ErrorAction SilentlyContinue)
        if ($processes.Count -gt 0) {
            $running += $commandName
        }
    }

    if ($running.Count -gt 0) {
        throw "Claude Unbound is still running ($($running -join ', ')). Stop those processes, then rerun uninstall."
    }
}

# Remove wrapper .cmd files from ~/.local/bin/.
function Remove-WrapperScripts {
    $binDir = Join-Path $HOME ".local\bin"
    foreach ($cmd in $FccCommands) {
        $cmdPath = Join-Path $binDir "$cmd.cmd"
        if (Test-Path -LiteralPath $cmdPath) {
            $commandText = @("Remove-Item", "-LiteralPath", (Format-Argument $cmdPath), "-Force") -join " "
            Write-Host "+ $commandText"
            if (-not $DryRun) {
                Remove-Item -LiteralPath $cmdPath -Force
            }
            Write-Host "Removed wrapper: $cmdPath"
        }
    }
}

# Remove the old uv tool installation (fallback for pre-existing installs).
function Uninstall-FreeClaudeCode {
    Add-UvToPath

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "uv not found on PATH; skipping uv tool uninstall."
        return
    }

    Write-Host "+ uv tool uninstall $PackageName"
    if (-not $DryRun) {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $output = (& uv tool uninstall $PackageName 2>&1 | Out-String).Trim()
            $exitCode = $LASTEXITCODE
            if ($exitCode -eq 0) {
                return
            }
            if (Test-MissingUvToolError -Output $output) {
                Write-Host "Claude Unbound uv tool not installed or already removed; skipping uv tool uninstall."
                return
            }
            if (-not [string]::IsNullOrWhiteSpace($output)) {
                [Console]::Error.WriteLine($output)
            }
            throw "uv tool uninstall $PackageName failed with exit code $exitCode; aborting before deleting ~/.fcc."
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
}

# Remove MCP Router state directory (~/.mcp-router/).
# This is relevant even on Windows if WSL was used with the MCP Router.
function Remove-McpRouterState {
    if (-not (Test-Path -LiteralPath $McpRouterDir)) {
        Write-Host "No MCP Router state at $McpRouterDir; skipping."
        return
    }

    $commandText = @(
        "Remove-Item",
        "-LiteralPath",
        (Format-Argument $McpRouterDir),
        "-Recurse",
        "-Force"
    ) -join " "
    Write-Host "+ $commandText"

    if (-not $DryRun) {
        Remove-Item -LiteralPath $McpRouterDir -Recurse -Force
    }
    Write-Host "Removed MCP Router state: $McpRouterDir"
}

# Remove the repository clone. In dev mode, only the junction is removed
# (the user's working copy is preserved). In clone mode, the entire
# directory is removed after verifying it looks like our repo.
function Remove-RepoClone {
    $installModeFile = Join-Path $HOME "$FccHomeDirname\.install_mode"
    $installMode = ""
    if (Test-Path -LiteralPath $installModeFile) {
        $installMode = (Get-Content -LiteralPath $installModeFile -ErrorAction SilentlyContinue).Trim()
    }

    if ($installMode -eq "dev") {
        # Dev mode: repo dir is a junction. Remove junction, not target.
        if (Test-Path -LiteralPath $RepoDir) {
            $item = Get-Item -LiteralPath $RepoDir -ErrorAction SilentlyContinue
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                # It's a junction — safe to remove
                [IO.Directory]::Delete($RepoDir, $false)  # remove junction only
                Write-Host "Removed junction $RepoDir (your working copy is untouched)."
            }
        }
        return
    }

    if (-not (Test-Path -LiteralPath $RepoDir)) {
        Write-Host "No repository at $RepoDir; skipping."
        return
    }

    # Safety: verify it looks like our repo before deleting
    $gitDir = Join-Path $RepoDir ".git"
    $isOurRepo = $false
    if (Test-Path $gitDir) {
        Push-Location $RepoDir
        try {
            $originProbe = & git remote get-url origin 2>$null
            if ($LASTEXITCODE -eq 0 -and $originProbe -match "claude-unbound") {
                $isOurRepo = $true
            }
        } finally {
            Pop-Location
        }
    }

    if ($isOurRepo) {
        $commandText = @(
            "Remove-Item",
            "-LiteralPath",
            (Format-Argument $RepoDir),
            "-Recurse",
            "-Force"
        ) -join " "
        Write-Host "+ $commandText"

        if (-not $DryRun) {
            Remove-Item -LiteralPath $RepoDir -Recurse -Force
        }
        Write-Host "Removed repository clone: $RepoDir"
    } else {
        Write-Host "WARNING: $RepoDir does not look like a Claude Unbound clone; not removing."
        Write-Host "Remove it manually if you are sure."
    }
}

function Purge-FccHome {
    $fccHome = Join-Path $HOME $FccHomeDirname
    if (-not (Test-Path -LiteralPath $fccHome)) {
        Write-Host "No FCC config directory at $fccHome; skipping purge."
        return
    }

    $commandText = @(
        "Remove-Item",
        "-LiteralPath",
        (Format-Argument $fccHome),
        "-Recurse",
        "-Force"
    ) -join " "
    Write-Host "+ $commandText"

    if (-not $DryRun) {
        Remove-Item -LiteralPath $fccHome -Recurse -Force
    }
}

if ($Help) {
    Show-Usage
    return
}

if ($RemainingArgs.Count -gt 0) {
    Show-Usage
    throw "Unknown option: $($RemainingArgs -join ' ')"
}

Write-Step "Checking for running Claude Unbound processes"
Assert-NoFccProcessesRunning

Write-Step "Removing wrapper scripts"
Remove-WrapperScripts

Write-Step "Removing old uv tool installation (if any)"
Uninstall-FreeClaudeCode

Write-Step "Removing MCP Router state"
Remove-McpRouterState

Write-Step "Removing repository clone"
Remove-RepoClone

Write-Step "Purging FCC config and data from ~/.fcc"
Purge-FccHome

Write-Host ""
Write-Host "Claude Unbound has been removed."
Write-Host "uv, Claude Code, Codex, and the uv-managed Python runtime were left installed."
