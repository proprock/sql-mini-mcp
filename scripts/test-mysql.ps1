[CmdletBinding()]
param(
    [switch]$Reset,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs = @()
)

$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "..\compose.mysql.yml"
$exitCode = 1
$services = @{
    mysql   = "SQL_MINI_MCP_TEST_MYSQL_URL"
    mariadb = "SQL_MINI_MCP_TEST_MARIADB_URL"
}

try {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon is not ready. Start Docker Desktop and retry."
    }

    $env:SQL_MINI_MCP_DOCKER_ROOT_PASSWORD = "SqlMiniMcpProbe1"
    if ($Reset) {
        docker compose -f $composeFile down --volumes --remove-orphans
        exit $LASTEXITCODE
    }

    $containerId = docker compose -f $composeFile ps -aq mysql
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect the MySQL container."
    }
    if ($containerId) {
        $passwordEntry = docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' $containerId |
            Where-Object { $_ -like "MYSQL_ROOT_PASSWORD=*" } |
            Select-Object -First 1
        if (-not $passwordEntry) {
            throw "The existing MySQL container has no configured root password."
        }
        $password = $passwordEntry.Substring("MYSQL_ROOT_PASSWORD=".Length)
    }
    else {
        $password = "SqlMiniMcp" + [Guid]::NewGuid().ToString("N")
    }
    $env:SQL_MINI_MCP_DOCKER_ROOT_PASSWORD = $password

    docker compose -f $composeFile up -d --wait
    if ($LASTEXITCODE -ne 0) {
        throw "MySQL/MariaDB containers did not become healthy."
    }

    foreach ($service in $services.Keys) {
        $portLine = docker compose -f $composeFile port $service 3306
        if ($LASTEXITCODE -ne 0 -or -not $portLine) {
            throw "Could not determine the $service host port."
        }
        $port = ($portLine.Trim() -split ":")[-1]
        $encodedPassword = [Uri]::EscapeDataString($password)
        Set-Item -Path ("Env:" + $services[$service]) -Value (
            "mysql+pymysql://root:{0}@127.0.0.1:{1}/mysql" -f $encodedPassword, $port
        )
    }

    uv run pytest tests/integration/mysql -m integration -v @PytestArgs
    $exitCode = $LASTEXITCODE
}
finally {
    foreach ($name in $services.Values) {
        Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue
    }
    Remove-Item Env:SQL_MINI_MCP_DOCKER_ROOT_PASSWORD -ErrorAction SilentlyContinue
}

exit $exitCode
