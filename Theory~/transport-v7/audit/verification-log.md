# Verification log

Дата: 2026-10-18. Репозитории: client `fe044bde937fc9801a72ccc61e23f097e7731920`; server V7 worktree `0f5267df8691aa41be993f2556cfc4b0a496b906`. Продуктовый код не редактировался. Все device проверки выполнялись на эмуляторах, не на физических телефонах.

## Повторяемые наборы

| Набор | Запуски | Результат |
|---|---:|---|
| `Native~/transport-tests` (`dotnet test`, M7_PYTHON указывает на project venv) | 3 | 85/85 каждый запуск |
| `Native~/transport-tests/e2e/run-e2e.sh` с временной PostgreSQL | 3 | 9/9 каждый запуск |
| Go `go test -p 1 ./cmd/... ./internal/... ./contracts/...` с throwaway PostgreSQL, uncached `-count=1` | 3 | pass каждый запуск |
| Go `go test -race -count=1 ./internal/transportv7` | 3 | pass каждый запуск |
| Go `go test -race -count=1 ./internal/httpapi -run '^TestV7'` с throwaway PostgreSQL | 3 | pass каждый запуск |
| Unity 6000.3.16f1 EditMode | 3 | 17/17 каждый запуск |
| Android Gradle `:analytics:test :analytics:assembleRelease --offline` | 1 | pass; AAR побайтно равен созданному AAR, SHA-256 `fb67918ff0550c37439301636eba6c19bfafd3708aefc34f0de3d23448e31d68` |
| Android device probe normal / nocatalog / kill | API 35 emulator | все три сценария pass с корректным портом |
| Android normal probe | API 37 emulator, 16 KB pages | pass |
| Dropped-range synthetic instrumentation probe | API 35 emulator | воспроизвёл потерю sequence 2 |
| Локальный .NET redirect probe | .NET 10 | 307 переслал синтетическое POST тело на другой origin |

Дополнительно: `gofmt -l .` не вернул файлов; `go vet ./...` и `go build ./...` прошли. `Native~/zstd/SHA256SUMS` совпал с тремя нативными библиотеками. Полная детерминированная пересборка native zstd библиотек не выполнялась.

## Известное несовпадение harness

Первый API 35 device запуск с портом по умолчанию 18081 не соединился с приложением, которое использует 18082. С `HTTP_PORT=18082` повтор прошёл. См. H3 в `../AUDIT.md`.

## Восстановление сравнения

Случайно прерванный запуск `comparison/reproduce.sh` временно изменил `results/repro-native-frames.log`. Файл восстановлен из scratch копии, SHA-256 совпал с ожидаемым `d9b674c420b2bd1fff6fbc0011f600ef50868d4c28a287aa42d2dd0efd558932`. `shasum -a 256 -c Theory~/transport-v7/comparison/MANIFEST.sha256` после восстановления: 223/223 совпадения.

## Логи в scratch

Подробные stdout/XML сохранены вне отчёта в `/tmp/mortris-v7-audit-20261018/` (включая три server, race, E2E, Unity и emulator прогона). В отчёт не включены сырые события или Puzzle записи.
