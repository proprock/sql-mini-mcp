[CmdletBinding()]
param(
    [switch]$Reset,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs = @()
)

$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "..\compose.sqlserver.yml"
$exitCode = 1

try {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon is not ready. Start Docker Desktop and retry."
    }

    $env:SQL_MINI_MCP_DOCKER_SA_PASSWORD = "SqlMiniMcpProbe!A1"
    if ($Reset) {
        docker compose -f $composeFile down --volumes --remove-orphans
        exit $LASTEXITCODE
    }

    $containerId = docker compose -f $composeFile ps -aq sqlserver
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect the SQL Server container."
    }
    if ($containerId) {
        $passwordEntry = docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' $containerId |
            Where-Object { $_ -like "MSSQL_SA_PASSWORD=*" } |
            Select-Object -First 1
        if (-not $passwordEntry) {
            throw "The existing SQL Server container has no configured SA password."
        }
        $password = $passwordEntry.Substring("MSSQL_SA_PASSWORD=".Length)
    }
    else {
        $password = "SqlMiniMcp!A1" + [Guid]::NewGuid().ToString("N")
    }
    $env:SQL_MINI_MCP_DOCKER_SA_PASSWORD = $password

    docker compose -f $composeFile up -d --wait
    if ($LASTEXITCODE -ne 0) {
        throw "SQL Server container did not become healthy."
    }

    $portLine = docker compose -f $composeFile port sqlserver 1433
    if ($LASTEXITCODE -ne 0 -or -not $portLine) {
        throw "Could not determine the SQL Server host port."
    }
    $port = ($portLine.Trim() -split ":")[-1]
    $encodedPassword = [Uri]::EscapeDataString($password)
    $env:SQL_MINI_MCP_TEST_SQLSERVER_URL = (
        "mssql+pyodbc://sa:{0}@127.0.0.1:{1}/master" +
        "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes"
    ) -f $encodedPassword, $port

    uv run pytest tests/integration/sqlserver -m integration -v @PytestArgs
    $exitCode = $LASTEXITCODE
}
finally {
    Remove-Item Env:SQL_MINI_MCP_TEST_SQLSERVER_URL -ErrorAction SilentlyContinue
    Remove-Item Env:SQL_MINI_MCP_DOCKER_SA_PASSWORD -ErrorAction SilentlyContinue
}

exit $exitCode
