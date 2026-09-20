[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs = @()
)

# Release matrix: SQL Server, MySQL and MariaDB together. Runs every live suite
# (tests/integration) plus the cross-engine matrix with all three servers configured.
$ErrorActionPreference = "Stop"
$sqlserverCompose = Join-Path $PSScriptRoot "..\compose.sqlserver.yml"
$mysqlCompose = Join-Path $PSScriptRoot "..\compose.mysql.yml"
$exitCode = 1
$mysqlServices = @{
    mysql   = "SQL_MINI_MCP_TEST_MYSQL_URL"
    mariadb = "SQL_MINI_MCP_TEST_MARIADB_URL"
}

function Get-ContainerPassword($composeFile, $service, $variable) {
    $containerId = docker compose -f $composeFile ps -aq $service
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect the $service container."
    }
    if ($containerId) {
        $entry = docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' $containerId |
            Where-Object { $_ -like "$variable=*" } |
            Select-Object -First 1
        if (-not $entry) {
            throw "The existing $service container has no configured password."
        }
        return $entry.Substring($variable.Length + 1)
    }
    return $null
}

try {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon is not ready. Start Docker Desktop and retry."
    }

    $env:SQL_MINI_MCP_DOCKER_SA_PASSWORD = "SqlMiniMcpProbe!A1"
    $env:SQL_MINI_MCP_DOCKER_ROOT_PASSWORD = "SqlMiniMcpProbe1"

    $saPassword = Get-ContainerPassword $sqlserverCompose "sqlserver" "MSSQL_SA_PASSWORD"
    if (-not $saPassword) {
        $saPassword = "SqlMiniMcp!A1" + [Guid]::NewGuid().ToString("N")
    }
    $rootPassword = Get-ContainerPassword $mysqlCompose "mysql" "MYSQL_ROOT_PASSWORD"
    if (-not $rootPassword) {
        $rootPassword = "SqlMiniMcp" + [Guid]::NewGuid().ToString("N")
    }
    $env:SQL_MINI_MCP_DOCKER_SA_PASSWORD = $saPassword
    $env:SQL_MINI_MCP_DOCKER_ROOT_PASSWORD = $rootPassword

    docker compose -f $sqlserverCompose up -d --wait
    if ($LASTEXITCODE -ne 0) {
        throw "SQL Server container did not become healthy."
    }
    docker compose -f $mysqlCompose up -d --wait
    if ($LASTEXITCODE -ne 0) {
        throw "MySQL/MariaDB containers did not become healthy."
    }

    $portLine = docker compose -f $sqlserverCompose port sqlserver 1433
    if ($LASTEXITCODE -ne 0 -or -not $portLine) {
        throw "Could not determine the SQL Server host port."
    }
    $port = ($portLine.Trim() -split ":")[-1]
    $env:SQL_MINI_MCP_TEST_SQLSERVER_URL = (
        "mssql+pyodbc://sa:{0}@127.0.0.1:{1}/master" +
        "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes"
    ) -f [Uri]::EscapeDataString($saPassword), $port

    foreach ($service in $mysqlServices.Keys) {
        $portLine = docker compose -f $mysqlCompose port $service 3306
        if ($LASTEXITCODE -ne 0 -or -not $portLine) {
            throw "Could not determine the $service host port."
        }
        $port = ($portLine.Trim() -split ":")[-1]
        Set-Item -Path ("Env:" + $mysqlServices[$service]) -Value (
            "mysql+pymysql://root:{0}@127.0.0.1:{1}/mysql" -f [Uri]::EscapeDataString($rootPassword), $port
        )
    }

    $auditDir = Join-Path ([IO.Path]::GetTempPath()) "sql-mini-mcp-audit"
    Remove-Item $auditDir -Recurse -Force -ErrorAction SilentlyContinue
    $env:SQL_MINI_MCP_AUDIT_DIR = $auditDir

    uv run pytest tests/integration -m integration -v @PytestArgs
    $exitCode = $LASTEXITCODE
    if (Test-Path $auditDir) {
        Write-Host "Audit artifacts: $auditDir"
    }
}
finally {
    foreach ($name in $mysqlServices.Values) {
        Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue
    }
    Remove-Item Env:SQL_MINI_MCP_TEST_SQLSERVER_URL -ErrorAction SilentlyContinue
    Remove-Item Env:SQL_MINI_MCP_AUDIT_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:SQL_MINI_MCP_DOCKER_SA_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:SQL_MINI_MCP_DOCKER_ROOT_PASSWORD -ErrorAction SilentlyContinue
}

exit $exitCode
