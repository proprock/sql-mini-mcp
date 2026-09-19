# Исполнимый roadmap `sql-mini-mcp`

Этот файл предназначен для последовательной реализации младшей моделью. Это набор небольших
заданий с явными границами, файлами, тестами и критериями завершения, а не перечень заголовков.
Архитектурные решения не пересматриваются внутри задач без отдельного ADR и согласования.

## 0. Как работать с roadmap

### Обозначения статуса

- `[x]` — код и обязательные локальные проверки задачи завершены в указанной ветке.
- `[~]` — существует рабочая заготовка, но acceptance criteria или milestone gate не выполнены.
- `[ ]` — задача не начата либо её результат не подтверждён.

Наличие файла или теста не означает, что задача завершена. Integration-задача считается
завершённой только после реального запуска против соответствующей СУБД. Security gate нельзя
закрывать процентом coverage или mutation score: каждый значимый surviving mutant должен быть
объяснён либо убит тестом.

### Обязательный цикл каждой задачи

1. Проверить текущую ветку и `git status --short`; не затрагивать посторонние изменения.
2. Прочитать связанные разделы `ARCHITECTURE.md`, `CONVENTIONS.md`, `SECURITY.md` и `CHECKS.md`.
3. Найти затрагиваемые symbols через codebase-memory-mcp; `rg` использовать для конфигов, строк и
   документации либо если graph tools не дали результата.
4. Сначала добавить или уточнить focused test, затем внести минимальную реализацию.
5. Выполнить focused test и обязательный fast gate соответствующего milestone.
6. Выполнить `git diff --check` и просмотреть diff на утечки secrets, SQL, token или DB errors.
7. Сделать один task-scoped Conventional Commit. Не смешивать соседние пункты roadmap.
8. Обновить статус только после выполнения всех `Done when` текущей задачи.

### Общие запреты

- Не добавлять HTTP transport, PostgreSQL, views или unrestricted SQL в MVP.
- Не использовать ORM; разрешены SQLAlchemy Core и Inspector.
- Не передавать caller SQL непосредственно в DBAPI/SQLAlchemy execution sink.
- Не логировать credentials, expanded URL, SQL parameters, plaintext PII или tokens.
- Не возвращать raw DB errors наружу.
- Не ослаблять reject rule ради прохождения одного теста.
- Не начинать Milestone 2B до рабочего `execute_sql`, а Milestone 2 — до закрытия metadata MVP.

## Текущее состояние веток

- `feature/sqlserver-metadata`: Milestone 0 и основная реализация Milestone 1.
- `feature/sqlserver-pii-sql`: изолированная заготовка Milestone 2. Она не готова к merge, пока не
  пройдены все задачи 2A и обязательный gate 2B.
- На текущей машине fast gate Milestone 1 проходит: Ruff, ty, 17 tests. Live SQL Server test был
  skipped, потому что `SQL_MINI_MCP_TEST_SQLSERVER_URL` не задан. Поэтому весь Milestone 1 пока
  имеет статус `[~]`, несмотря на готовность кода.

---

# Milestone 0 — правила проекта и воспроизводимая среда

Цель: получить минимальный репозиторий, в котором следующая модель однозначно понимает архитектуру,
границы безопасности, workflow и команды проверки.

## 0.1 [x] Зафиксировать архитектуру и границы MVP

**Ветка:** `feature/sqlserver-metadata`

**Изменения:**

- Создать `ARCHITECTURE.md` с цепочкой
  `MCPServer -> DatabaseService -> EngineRegistry -> Inspector/Core -> DBAPI`.
- Зафиксировать `DatabaseService` как единственный application facade.
- Зафиксировать, что vendor-specific metadata живёт только в `DatabaseExtras`.
- Описать milestones: SQL Server metadata, SQL Server PII-safe SQL, MySQL/MariaDB.
- Явно вынести PostgreSQL, HTTP, views и unrestricted SQL за границы MVP.

**Done when:** архитектура не требует чтения исходного чата и не содержит альтернативных,
невыбранных вариантов реализации.

## 0.2 [x] Создать документы для выполнения задач агентами

**Изменения:**

- Создать компактный `AGENTS.md` с routing, TDD, discovery order и quality expectations.
- Создать `CONVENTIONS.md`, `SECURITY.md`, `CHECKS.md`, `WORKFLOW.md`.
- Сохранить существующий `CLAUDE.md` без перезаписи.
- Добавить исключение `!/ROADMAP.agents.md` после общего ignore для `*.agents.md`.

**Done when:** все документы tracked; `git check-ignore ROADMAP.agents.md` не считает roadmap
ignored; правила не дублируют друг друга противоречивым образом.

## 0.3 [x] Инициализировать Python-проект и quality tooling

**Файлы:** `pyproject.toml`, `uv.lock`, `.pre-commit-config.yaml`, `src/sql_mini_mcp/__init__.py`.

**Изменения:**

- Поддержать Python `>=3.12,<3.15`.
- Добавить runtime dependencies текущего milestone. Код следующего milestone не должен попасть в
  metadata branch, даже если dependency объявлена заранее.
- Настроить Ruff, ty, pytest, pytest-cov и prek.
- Добавить console script `sql-mini-mcp = sql_mini_mcp.__main__:main`.
- Исключить `.venv`, coverage, pytest, Ruff, Hypothesis, mutmut и codebase-memory caches.

**Проверки:**

```powershell
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run ty check
```

**Done when:** чистый checkout устанавливается через `uv sync`; команды не зависят от глобального
Python package state.

---

# Milestone 1 — рабочий SQL Server metadata MVP

Цель: stdio MCP server с шестью typed metadata tools. Caller не может выполнять произвольный SQL.
Engines ленивые, bounded, корректно освобождаются; ошибки и secrets не пересекают public boundary.

## 1.1 [x] Реализовать строгую конфигурацию

**Файлы:** `src/sql_mini_mcp/config.py`, `tests/unit/test_config.py`,
`sql-mini-mcp.example.yaml`.

**Реализация:**

- Описать strict Pydantic models `AppConfig`, `RuntimeConfig`, `ServerConfig`, `PiiConfig`,
  `PiiRule`; неизвестные поля отклонять.
- Поддержать `version: 1`, runtime limits и mapping `servers` по alias.
- Для embedded `${NAME}` подставлять env variable с URL encoding.
- Если весь `connection_url` равен `${NAME}`, разрешить готовый SQLAlchemy URL без повторного
  encoding.
- Не хранить expanded URL и decoded keys в обычных строковых representations.
- Проверить dialect/driver: SQL Server использует `mssql+pyodbc`.
- `metadata` alias не требует PII config; `pii_safe` требует `pii_key_env`, rules и base64 key ровно
  32 bytes.
- Key принадлежит одному server alias. Отклонять одинаковые decoded keys у разных aliases.
- Ошибки чтения YAML/env/model validation преобразовывать в `CONFIG_ERROR` без secret value.

**Обязательные тесты:**

- embedded interpolation и URL encoding специальных символов;
- whole-value URL interpolation;
- missing env, неизвестное поле, неверная версия/driver;
- invalid base64 и длина key не 32 bytes;
- `pii_safe` без key/rules;
- одинаковый key у двух aliases;
- error string и model repr не содержат password/key.

**Done when:** `uv run pytest tests/unit/test_config.py -q` проходит; example config успешно
проходит `sql-mini-mcp --check-config` с тестовыми env variables.

## 1.2 [x] Описать public models и безопасные ошибки

**Файлы:** `src/sql_mini_mcp/models.py`, `src/sql_mini_mcp/errors.py`,
`tests/unit/test_errors.py`.

**Реализация:**

- Создать typed response models для servers, databases, tables, columns, PK, FK, unique indexes,
  ordinary indexes и stored procedures.
- Column definition содержит `name`, `native_type`, `nullable`, `length`, `precision`, `scale`,
  `autoincrement`, `identity`, `computed`, `default`.
- Создать `DomainError(code, public_message, hint, retryable, correlation_id)` и полный enum codes.
- Неожиданная ошибка получает generic public message и новый correlation ID.

**Обязательные тесты:** serialization contract, aliases вроде public `schema`, стабильный error
format, наличие correlation ID и отсутствие внутренних exception details.

**Done when:** public model JSON не зависит от SQLAlchemy objects и не содержит secrets.

## 1.3 [~] Реализовать lazy bounded `EngineRegistry`

**Файлы:** `src/sql_mini_mcp/db/registry.py`, `tests/unit/test_registry.py`.

**Реализация:**

- Cache key: `(server alias, database)`; engines создаются только при первом обращении.
- Использовать thread-safe LRU с `engine_cache_size` и `dispose()` evicted engine.
- Передавать `pool_size`, `max_overflow`, `pool_timeout`, `pool_pre_ping=true`, LIFO.
- Ограничить все DB operations одним AnyIO `CapacityLimiter`.
- Выполнять sync SQLAlchemy/DBAPI operations через `anyio.to_thread.run_sync`.
- Не разделять Connection, Inspector, cursor или result между потоками.
- Для pyodbc задавать cursor statement timeout из runtime config.
- `dispose()` закрывает все cached engines и очищает registry.

**Обязательные тесты:** lazy creation, reuse одного key, LRU eviction, dispose всех engines,
unknown alias, concurrency peak не выше limit, timeout hook.

**Done when:** тест реально запускает несколько concurrent operations и подтверждает заданный
предел, а lifespan test подтверждает вызов `dispose()`.

**Текущий gap:** lazy/LRU/dispose/concurrency тесты есть; ещё нужны focused tests для unknown alias,
cursor timeout hook и disposal именно через MCP lifespan.

## 1.4 [~] Реализовать portable table reflection

**Файлы:** `src/sql_mini_mcp/db/reflection.py`, unit tests с fake/mock Inspector.

**Реализация:**

- Использовать SQLAlchemy Inspector для base tables и table definition.
- Нормализовать columns, PK, FK, unique constraints и indexes в public models.
- Не возвращать SQLAlchemy `TypeEngine` или dialect objects наружу.
- Для SQL Server перечислять user schemas, исключая `sys`, `INFORMATION_SCHEMA` и системные схемы.
- Table без schema разрешать только при одном case-insensitive совпадении.
- При нескольких совпадениях возвращать `AMBIGUOUS_OBJECT` с безопасным списком schemas.
- При отсутствии вернуть `NOT_FOUND`.

**Обязательные тесты:** полная нормализация column attributes, composite PK/FK, duplicate table
names в разных schemas, case-insensitive lookup, schema-qualified lookup, отсутствующая таблица.

**Done when:** `get_table_definition` одним ответом возвращает все пять групп metadata.

**Текущий gap:** implementation присутствует, но отдельного unit suite с fake Inspector для полной
нормализации PK/FK/unique/index/column attributes пока нет.

## 1.5 [~] Реализовать SQL Server extras

**Файлы:** `src/sql_mini_mcp/db/extras.py`, `src/sql_mini_mcp/db/sqlserver.py`.

**Реализация:**

- Определить минимальный `DatabaseExtras` protocol только для непереносимых операций.
- Реализовать `list_databases`, `list_stored_procedures`, `get_stored_procedure`.
- Использовать bind parameters для filters/lookup; не собирать SQL из caller strings.
- Definition может быть `null`, если у credentials нет permission видеть текст.
- Применять `max_definition_chars`, возвращая `DEFINITION_TOO_LARGE`.

**Обязательные тесты:** normalization rows, case-insensitive filtering, schema filter, missing and
ambiguous procedure, definition unavailable/oversized.

**Done when:** vendor SQL находится только в SQL Server extras и не просачивается в service/MCP.

**Текущий gap:** implementation присутствует, но row normalization, permissions и
definition-size paths ещё не закрыты focused unit tests.

## 1.6 [~] Реализовать `DatabaseService` facade

**Файл:** `src/sql_mini_mcp/service.py`.

**Реализация:**

- Реализовать `list_servers`, `list_databases`, `list_tables`, `get_table_definition`,
  `list_stored_procedures`, `get_stored_procedure`.
- Все database operations направлять через `EngineRegistry.run`.
- Применять case-insensitive substring `name_contains` без pagination.
- Преобразовать operational/permission/timeout/SQLAlchemy ошибки в public `DomainError`.
- Не использовать `logger.exception` для DB exceptions: traceback может содержать SQL/params.
- Unexpected exceptions логировать только с correlation ID и generic context.

**Обязательные тесты:** filters, ambiguity, unknown server, access denied, timeout, connection
failure, unexpected exception redaction и отсутствие secret/SQL в log capture.

**Done when:** ни один MCP handler не обращается к Engine/Inspector/extras напрямую.

**Текущий gap:** покрыты table ambiguity и case-insensitive resolution; error mapping, filters и
log-redaction paths требуют отдельных тестов.

## 1.7 [~] Реализовать stdio MCP server и CLI

**Файлы:** `src/sql_mini_mcp/mcp_server.py`, `src/sql_mini_mcp/__main__.py`,
`tests/contract/test_mcp_tools.py`.

**Реализация:**

- Использовать официальный MCP SDK v2, typed tools и structured output.
- Lifespan создаёт `EngineRegistry`/`DatabaseService` и всегда вызывает `dispose()`.
- Зарегистрировать ровно шесть tools Milestone 1:
  `list_servers`, `list_databases`, `list_tables`, `get_table_definition`,
  `list_stored_procedures`, `get_stored_procedure`.
- Поставить read-only annotations.
- Исправимые `DomainError` преобразовать в `ToolError`; unexpected details не выдавать.
- CLI принимает `--config`, env `SQL_MINI_MCP_CONFIG`, `--check-config` и запускает stdio.
- Configuration error печатать в stderr без traceback и завершать кодом 2.

**Обязательные тесты:** in-process MCP Client видит точные names/input schemas; `list_servers`
возвращает structured content; unknown alias становится tool error без password; lifespan dispose;
CLI valid/invalid config exit codes.

**Done when:** metadata branch не регистрирует `execute_sql` даже для `pii_safe` alias.

**Текущий gap:** in-process tool list/structured output/error contract проверены; ещё нужны CLI
exit-code tests и явная проверка `registry.dispose()` при завершении lifespan.

## 1.8 [~] Выполнить реальный SQL Server integration gate

**Файл fixture:** `tests/integration/sqlserver/`.

**Подготовка:**

- Использовать отдельную disposable database и least-privilege test credential.
- Передать URL только через `SQL_MINI_MCP_TEST_SQLSERVER_URL`.
- Fixture создаёт уникальные schemas, одинаковые table names в двух schemas, FK/unique/index,
  procedure с definition и procedure без VIEW DEFINITION permission, если среда позволяет.
- Cleanup должен быть идемпотентным и не затрагивать не-test objects.

**Проверки:**

- Все шесть tools через настоящий MCP Client, а не прямой service call.
- Base table reflection и native SQL Server types.
- Schema ambiguity, case-insensitive filter, missing object.
- Permission denied, hidden definition, invalid database, statement timeout.
- Несколько concurrent calls и отсутствие shared cursor/connection errors.
- После shutdown все pools disposed.

**Команды:**

```powershell
uv run pytest tests/unit tests/contract -m "not integration"
uv run pytest tests/integration/sqlserver -m integration -v
uv run ruff format --check .
uv run ruff check .
uv run ty check
git diff --check
```

**Done when:** integration command завершился без skip и README содержит реально проверенную setup
инструкцию. Сейчас fixture создан, но live run не выполнен — задача остаётся `[~]`.

## Milestone 1 acceptance

- Fast gate зелёный.
- SQL Server integration suite проходит без skip.
- В MCP tool list ровно шесть metadata tools.
- Invalid config/permissions/timeouts не раскрывают credentials, URL или DB error text.
- `execute_sql` и security package отсутствуют в metadata merge diff.
- После review ветка может быть squash-merged; только затем Milestone 2 branch обновляется от неё.

---

# Milestone 2A — SQL Server PII-safe `execute_sql`

Цель: разрешить только небольшой `SELECT` subset, отделить validation от execution и токенизировать
configured PII. Наличие working draft не означает пригодность к merge.

## 2.1 [~] Подготовить отдельную ветку и security test layout

**Ветка:** `feature/sqlserver-pii-sql`, основанная на завершённом Milestone 1.

**Изменения:**

- Добавить `sqlglot`, `cryptography`, Hypothesis; `mutmut` только не на Windows.
- Создать `src/sql_mini_mcp/security/` с модулями `parser.py`, `schema.py`, `policy.py`,
  `tokens.py`, `validated_query.py`, `executor.py`.
- Создать отдельные `tests/security/` и `tests/security/corpus/`.
- Не регистрировать tool до готовности parser, policy, execution boundary и focused tests.

**Done when:** baseline Milestone 1 tests проходят неизменными; security modules не меняют metadata
tools. Draft существует, но задача остаётся `[~]` до обновления от принятого M1.

## 2.2 [~] Реализовать resource limits и parse-exactly-one

**Файл:** `security/parser.py`.

**Порядок:**

1. До parser проверить `max_sql_chars`.
2. Parse с dialect `tsql`.
3. Требовать ровно один statement и root `SELECT`.
4. После parse посчитать AST nodes, joins и items каждого `IN`.
5. Любую parser/tokenizer/internal validation ошибку превратить в `QUERY_REJECTED`.

**Boundary tests:** ровно limit и limit+1 для chars/nodes/joins/IN; empty input; comments only;
semicolon variants; arbitrary Unicode; parser не должен падать unexpected exception.

**Done when:** rejected input не вызывает schema lookup и execution sink.

## 2.3 [~] Реализовать raw-AST allowlist с fail-closed default

**Разрешить только:** local base tables, direct columns/aliases, literals, `COUNT(*)` без GROUP BY,
INNER/LEFT JOIN с ON, WHERE AND/OR/comparison/IN/IS NULL, ORDER BY direct non-PII column, TOP.

**Явно запретить:** non-SELECT/multiple statements, CTE, subqueries, derived tables, set operations,
DISTINCT/GROUP/HAVING, other aggregates/functions/UDF/windows/CASE, SELECT INTO, variables/temp
tables, cross-database/four-part identifiers, linked servers, OPENROWSET/OPENQUERY, APPLY,
PIVOT/UNPIVOT, hints/OPTION, WAITFOR, FOR XML/JSON и неизвестные nodes.

**Требование:** новый SQLGlot node отклоняется по умолчанию. Raw AST проверяется до transformations.

**Done when:** table-driven allow/reject suite покрывает каждый пункт отдельным named case.

## 2.4 [~] Реализовать schema loading и object resolution

**Файл:** `security/schema.py`.

**Реализация:**

- Из raw AST извлечь только table identifiers; не доверять qualification до lookup.
- Разрешать только tables текущей database и reflected user schema.
- Unqualified SQL Server table разрешать только при одном case-insensitive match.
- Reject отсутствующие/system/cross-database objects.
- Построить минимальную SQLGlot schema map только для referenced tables.
- Schema cache должен быть bounded и не смешивать aliases/databases.

**Tests:** duplicate names, quoted/bracket identifiers, reserved words, Unicode/case variations,
system schema, catalog qualifier, stale/missing column.

**Done when:** qualification никогда не добавляет объект, не подтверждённый reflection.

## 2.5 [~] Выполнить qualification, star expansion и output lineage

**Реализация:**

- После raw allowlist вызвать SQLGlot qualification с подготовленной schema.
- Раскрыть `*` и `table.*`; повторно проверить limits после transformation.
- Для output column определить один source `(schema, table, column)` либо разрешённый `COUNT(*)`.
- Alias меняет output name, но не source lineage.
- Duplicate labels допустимы только при сохранении позиционной lineage; иначе reject.
- Unknown/ambiguous lineage всегда `QUERY_REJECTED`.

**Tests:** joins с одинаковыми names, qualified/unqualified stars, aliases, alias rename, duplicate
labels и ambiguity.

**Done when:** PII policy получает lineage structure, а не повторно интерпретирует SQL text.

## 2.6 [~] Реализовать per-server key registry и AES-GCM token codec

**Файл:** `security/tokens.py`.

**Format:** `pii:v1:<base64url(nonce || ciphertext || tag)>`, AES-256-GCM, random 96-bit nonce.

**Реализация:**

- Codec создаётся только для выбранного alias и никогда не перебирает другие keys.
- AAD содержит protocol version и точный server alias.
- Payload — versioned tagged JSON поддерживаемых scalar types; `NULL` не токенизируется.
- Canonical base64url, максимальная token length и строгая payload schema.
- Malformed, wrong-key, wrong-alias, truncated и auth failure возвращают один
  `INVALID_PII_TOKEN` без oracle details.
- `repr` codec/registry не содержит key; plaintext/token не логируются.

**Tests:** round-trip типов, random nonce, alias isolation, same-key different alias, bit-flips,
arbitrary bytes/Unicode/oversized input, key rotation.

**Done when:** token одного alias нельзя использовать другим даже при одинаковом key.

## 2.7 [~] Реализовать PII policy над resolved AST

**Разрешить protected column только:** direct projection; projection с alias; слева от `=` или `IN`,
когда каждое значение — token текущего alias.

**Запретить:** plaintext predicate, protected JOIN key, ORDER BY, arithmetic, CAST/function/CASE,
aggregate, token в другой expression, unknown/ambiguous lineage.

**Tests:** отдельный case для каждой позиции; смешанный IN с token и plaintext; alias rename; same
column name в joined tables; rule database `*` и exact database.

**Done when:** решение основывается на source lineage и configured rules, не на output label.

## 2.8 [~] Реализовать token-to-bind rewrite и sealed `ValidatedQuery`

**Файлы:** `security/validated_query.py`, части `policy.py`/`executor.py`.

**Реализация:**

- После policy validation заменить token literals на SQLGlot placeholders.
- Decrypted values хранить отдельно в bind parameter mapping.
- Выполнить final AST allowlist после rewrite.
- Сгенерировать SQL только из final AST.
- `ValidatedQuery` содержит AST, generated SQL, binds, output plan, row limit, alias/database.
- Создание доступно только internal factory после pipeline; executor принимает только этот type.
- `repr`/serialization не показывают token и plaintext parameters.

**Critical test:** PII со строкой `x'; DROP TABLE Canary;--` после decrypt остаётся одним bind value;
payload отсутствует в generated SQL.

**Done when:** raw SQL невозможно передать в executor через public API.

## 2.9 [~] Реализовать bounded executor и result encoding

**Файл:** `security/executor.py`.

**Реализация:**

- Проверить `1 <= max_rows <= hard_max_rows`; default берётся из config.
- Для SQL Server применить TOP/cap на AST до final validation/generation.
- Выполнить generated SQL и отдельные binds через SQLAlchemy Core.
- Получить не более `max_rows + 1`, чтобы выставить `truncated` без unbounded buffering.
- Protected cells tokenизировать согласно output plan; `NULL` оставить null.
- Неподдерживаемые result types кодировать по явному contract либо вернуть controlled error.
- Statement timeout задаёт server config, caller его не меняет.

**Tests:** row cap/truncated, invalid limits, protected markers отсутствуют в response, positional
column metadata, DB error redaction, timeout.

**Done when:** recording connection подтверждает generated SQL и отдельный params mapping.

## 2.10 [~] Зарегистрировать `execute_sql` в service и MCP

**Файлы:** `service.py`, `mcp_server.py`, contract tests.

**Реализация:**

- Разрешить tool только для `pii_safe`; для `metadata` вернуть `ACCESS_LEVEL_DENIED`.
- Не принимать statement timeout или dialect от caller.
- Пройти pipeline целиком внутри одной bounded DB operation.
- Вернуть structured `SqlResult`: columns/source/protected/encoding, rows, row_count, truncated.
- Ошибки policy/token/database перевести в public codes без internal details.

**Tests:** registration contract, metadata denial, valid projection, token predicate, rejected query
не вызывает sink, structured result schema.

**Done when:** задачи 2.2–2.10 и fast security suite проходят. Это завершает только 2A;
`execute_sql` нельзя merge до Milestone 2B.

---

# Milestone 2B — обязательный security hardening gate

Цель: активно попытаться продавить parser, policy, token isolation и execution boundary. Это не
опциональный polishing.

## 2.11 [~] Создать version-controlled adversarial SQL corpus

**Обязательные категории:** stacked/separator/comments, Unicode/quoted identifiers, cross-DB и
four-part names, linked server/openrowset/openquery, SELECT INTO/side effects, CTE/subquery/UNION,
APPLY/PIVOT/hints, variables/temp/dynamic SQL, functions/UDF/XML/JSON/aggregate exfiltration, PII
aliasing/duplicate labels, protected CASE/CAST/ORDER/JOIN, unsupported token positions,
malformed/oversized/cross-alias tokens и resource exhaustion.

Каждый case хранит input, expected error code и причину. Каждый bypass сначала добавляется как
failing regression, затем исправляется.

**Done when:** corpus runner подтверждает expected code и spy sink подтверждает zero executions.

## 2.12 [~] Добавить Hypothesis properties и профили

**Strategies:** valid restricted AST, внедрение forbidden node, identifiers/quoting/case,
whitespace/comments/parentheses, boundary sizes, arbitrary token bytes/Unicode, tampering и
SQL-looking decrypted values.

**Properties:** forbidden node rejects; unknown defaults reject; formatting не меняет decision;
alias rename не меняет lineage; generated SQL повторно parse/validate; rejected input не достигает
sink; plaintext не сериализуется; token принимает только issuing alias; parser/policy не падают.

**Profiles:** deterministic `security-fast` около 200 examples на PR и `security-deep` несколько
тысяч examples для nightly/manual gate. Минимизированные regressions переносить в corpus.

**Done when:** оба профиля проходят с воспроизводимым seed/reproduction output.

## 2.13 [ ] Запустить mutation testing только по security boundary

**Среда:** Linux CI или WSL; не запускать Docker integration suite на каждом mutant.

**Scope:** `security/parser.py`, `policy.py`, `schema.py`, `tokens.py`, `validated_query.py`,
`executor.py` и key-selection paths в `config.py`.

**Порядок:**

1. Убедиться, что fast security suite зелёный без mutation.
2. Запустить `uv run mutmut run`.
3. Получить список через `uv run mutmut results`.
4. Для каждого survivor выполнить `mutmut show` и классифицировать mutation.
5. Для security-relaxing mutation сначала добавить failing test, затем повторить focused mutants.
6. Equivalent mutant записать в `SECURITY.md`: module:line, mutation и доказательство.
7. Timeout расследовать как test isolation/performance problem, а не считать killed.

**Done when:** zero unexplained survivors; 100% killed non-equivalent mutants во всех reject,
PII detection, key/AAD, bind rewrite и execution-boundary branches. Прерванный прогон не evidence.

## 2.14 [ ] Проверить writable SQL Server attack fixture

**Fixture:** disposable database, намеренно writable credentials, canary table/schema, уникальные
PII markers, recording/audit hook, второй alias с отдельным key и test-only alias с тем же key.

**Проверки:**

- INSERT/UPDATE/DELETE/DDL и rejected SELECT не достигают cursor execution.
- Canary schema/rows до и после corpus идентичны.
- В DB попадает только generated SQL; bind values не интерполированы.
- PII markers отсутствуют в response, captured logs и errors.
- Malformed/wrong-key/wrong-alias не различимы по public error details.
- Token работает между databases одного alias, но не между aliases.

**Done when:** fixture проходит реальной writable credential, audit artifacts приложены к review.

## 2.15 [ ] Зафиксировать security review и закрыть Milestone 2

**Обновить:** `SECURITY.md`, `CHECKS.md`, README и roadmap.

**Обязательный gate:**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest tests/unit tests/contract tests/security -m "not deep"
uv run pytest tests/integration/sqlserver -m integration
uv run pytest tests/security -m deep
```

В Linux/WSL:

```text
uv run mutmut run
uv run mutmut results
```

**Done when:** branch coverage policy/token/execution decisions 100% либо каждое исключение review;
zero unexplained mutants; corpus/deep/live проходят; canary unchanged; marker scan clean. Только
после этого `execute_sql` пригоден к merge.

---

# Milestone 3 — MySQL/MariaDB

Цель: добавить второй dialect без ослабления общей политики и без копирования security pipeline.

## 3.1 [ ] Подготовить ветку и MySQL extras

**Ветка:** `feature/mysql-metadata` от принятого Milestone 2.

**Изменения:**

- Добавить/активировать PyMySQL и `MySqlExtras` через `extras_for`.
- `schema` для MySQL/MariaDB обязан быть `null`; database соответствует их catalog model.
- Реализовать databases, procedures и `SHOW CREATE PROCEDURE`/эквивалент с safe lookup.
- Table reflection по возможности оставить общим Inspector path.
- Настроить driver timeouts через поддерживаемые PyMySQL connection arguments.

**Tests:** metadata contract против MySQL и MariaDB, schema-not-null rejection, permissions,
procedure differences, native types/indexes/FK.

**Done when:** один public contract suite проходит на трёх engines; differences документированы.

## 3.2 [ ] Адаптировать validated SQL pipeline к dialect `mysql`

**Изменения:**

- Выбирать parser/generator dialect только из trusted server config.
- Перенести общий allowlist; использовать `LIMIT` вместо SQL Server TOP.
- Сохранить запрет cross-database references.
- Проверить backticks, reserved words, comments и MySQL-specific functions/hints.
- Не дублировать policy/token/ValidatedQuery implementation.

**Tests:** общий corpus на mysql dialect плюс dialect-specific attacks; generated SQL reparse;
limit enforcement; injection-after-decrypt остаётся bind.

**Done when:** dialect differences изолированы в adapters, policy decisions остаются общими.

## 3.3 [ ] Проверить cross-engine token isolation и release matrix

**Проверки:**

- Отдельные aliases/keys для SQL Server, MySQL и MariaDB.
- Token каждого alias отвергается двумя другими тем же `INVALID_PII_TOKEN`.
- Одинаковые test keys не позволяют cross-alias decrypt из-за AAD.
- Полный metadata и SQL contract suite проходит на трёх engines.
- Security-fast запускается на PR; трёхдвижковая live matrix — на Milestone 3/release gate.

**Done when:** README содержит проверенные setup команды и версии servers/drivers; integration tests
прошли без skip; security review обновлён после dependency/dialect changes.

---

# Финальная матрица готовности

| Возможность | Ветка | Требуемое доказательство | Текущий статус |
|---|---|---|---|
| Project rules/config/core | `feature/sqlserver-metadata` | Ruff, ty, unit tests | готово |
| SQL Server metadata MCP | `feature/sqlserver-metadata` | contract + live SQL Server без skip | код готов, live gate не выполнен |
| SQL Server `execute_sql` | `feature/sqlserver-pii-sql` | unit/contract/security-fast | draft, не принят |
| Security hardening | `feature/sqlserver-pii-sql` | deep + mutation + writable canary | не выполнено |
| MySQL/MariaDB | `feature/mysql-metadata` | common contract + 3-engine matrix | не начато |

После обновления SQLGlot, cryptography, SQLAlchemy или MCP SDK повторно выполнять соответствующий
contract/security/mutation gate; старый результат не переносится автоматически на новую версию.
