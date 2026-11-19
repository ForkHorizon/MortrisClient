Аудит A6 завершён (read-only; без запусков/правок). Нашёл три подтверждаемых/вероятных риска по жизненному циклу; ниже в требуемом формате.

ID A6-1; Severity средний; Confidence подтверждено; Location: `Runtime/Internal/Session/SessionTracker.cs:71–96, 211–218`, `Runtime/Internal/AnalyticsRuntime.cs:48–53`.
Что не так: решение о новой сессии использует системные Unix-часы для измерения интервала в фоне. Ручной перевод часов/автоматическая коррекция времени может ложно пересечь SessionTimeout или скрыть реальный тайм-аут; смена только часового пояса не влияет на Unix milliseconds.
Сценарий: приложение уходит в фон; системные часы переводятся вперёд более чем на SessionTimeout; приложение возвращается → `gap` вычисляется длиннее порога, старую сессию закрывает по времени ухода и создаёт новую, хотя реального отсутствия нужной длительности могло не быть (обратная коррекция даёт противоположный результат).
Цитата:
```csharp
var now = _nowMs();
...
var left = _backgroundAt; var gap = Math.Max(0, now - left);
if (gap >= (long)_timeout.TotalMilliseconds)
{
    EmitSessionEnd(left, "timeout", true);
    BeginSession(now, coldStart: false);
```
Как исправить: для интервалов/тайм-аута сохранять монотонные elapsed значения, отдельно оставив UTC для timestamp событий; для переживания процесса хранить соответствующую платформенную оценку/ограничение.

ID A6-2; Severity средний; Confidence подтверждено; Location: `Runtime/Internal/AnalyticsPersistenceWorker.cs:169–182, 235–244`, `Runtime/Internal/Session/SessionTracker.cs:142–182`.
Что не так: восстановленная сессия закрывается событием, но это событие и замена сохранённого snapshot новой сессией не являются одной атомарной операцией. Между успешной записью очереди и `SaveSessionState` процесс может умереть; прежний snapshot остаётся, и следующий запуск повторно эмитит тот же конец сессии.
Сценарий: B загружает snapshot A и `Recover` добавляет `sys_session_end`; `WriteBuffer()` успешно сохраняет его в SQLite; процесс B аварийно завершается до `SaveSessionState(false)` → C всё ещё читает snapshot A и снова пишет `sys_session_end` для A.
Цитата:
```csharp
RecoverPreviousSession();
...
WriteBuffer();
...
SaveSessionState(false);
```
Как исправить: сделать recovery+маркер обработки атомарными с очередью либо дедуплицировать recovery-end стабильным ID/идемпотентным ключом.

ID A6-3; Severity низкий/средний; Confidence вероятно; Location: `Runtime/Internal/Session/SessionTracker.cs:52, 65–96, 211–218`; `Runtime/Internal/AnalyticsRuntime.cs:48–53`.
Что не так: Track читает `Current` без `_sync`, а ротация сессии делает новый `_current` видимым до эмита start и не синхронизирована с записью игровых событий. При Track с другого потока событие может оказаться после `sys_session_end` со старым session ID либо до `sys_session_start` с новым ID.
Сценарий: фоновый поток Track получает старую `Current`, приостанавливается; lifecycle-поток при возврате после тайм-аута добавляет end, меняет Current, добавляет start; первый поток продолжает `Write` → старая сессия получает событие после end. Публичный API не документирует main-thread-only ограничение; точную гарантию потокобезопасности из файлов не подтвердил.
Цитата:
```csharp
internal SessionInfo Current => System.Threading.Volatile.Read(ref _current);
...
private void BeginSession(long now, bool coldStart)
{
    var info = new SessionInfo(_newId(), now);
    System.Threading.Volatile.Write(ref _current, info);
```
Как исправить: синхронизировать выбор session ID и enqueue события с ротацией либо явно гарантировать/документировать main-thread-only Track.

Проверено, замечаний нет: повторные pause/resume игнорируются по `_backgroundAt`; повторный quit после `_ended` не эмитит второй конец; `OnQuit` в фоне завершает сессию timestamp-ом ухода; `SessionTimeout` и `EventBufferWindow` валидируются; UTC Unix timestamps не зависят от DST/смены timezone; `Touch` только обновляет heartbeat в foreground; `Recover` фильтрует ended snapshot и неэмитит при пустом/невалидном JSON или невалидном Guid. `ExitReasonName` отображает Android reasons 1–16, прочитал switch.

Читал `Runtime/Internal/Session/SessionTracker.cs`, `Runtime/Internal/AnalyticsLifecycle.cs`, `Runtime/Internal/AnalyticsRuntime.cs`, `Runtime/Internal/AnalyticsPersistenceWorker.cs` и `Runtime/AnalyticsOptions.cs`; контекст — `Documentation/EventPipelineAndSessions.md`, `Documentation/ServerContractLifecycle.md`. Не запускал проверки, не менял файлы.
