"""Reports come from saved integer byte totals; aspirations remain separate."""
import json
from pathlib import Path
from support7 import ROOT
R=ROOT/'results';DOC=ROOT.parent

def read(name):return json.loads((R/name).read_text())

def run():
    real=read('bench-real.json')['rows'];audit=read('real-audit.json')
    summary='''# V7: итог завершённого исследования, 17 октября 2026

Исследование закрыто по решению пользователя. [Финальные выводы и статус всех
критериев](11-final-conclusions.md) фиксируют результат V7; продолжение экспериментов
и production-интеграция в эту завершённую работу не входят.

Гипотеза о достаточности словаря **не подтвердилась**. Универсальный прототип
работает, но целевые 11–13 Б на сырых и 5–7 Б на очищенных событиях не достигнуты.
Продакшен SDK, игра и сервер не изменялись.

С VPS в read-only транзакции скопирован день **2026-10-16 UTC**: 524934 события,
162 установки, 564 сессии, сжатая копия 67914154 Б. Полный день проверен на дубли,
хеши и соответствие взаимодействий. В бенчмарке 19882 обучающих и 63943 проверочных
события; установки не пересекаются. Лимит 600 первых событий на установку
преднамеренно ограничивает стоимость эксперимента; это не случайная выборка дня.

| Данные | V1 gzip1, исходные UUID | V7 dict32, identity по sequence | V7 dict16, исходные UUID |
|---|---:|---:|---:|
'''
    labels=['Исходные','Без выводимого SHA и wave-дубля','Дополнительно без interaction GUID¹']
    for label,row in zip(labels,real):
        b=row['B_event'];summary+=f"| {label} | {b['v1_gzip1']:.2f} | {b['v7_dict32']:.2f} | {b['v7_full_ids_dict16']:.2f} |\n"
    summary+='''
Все размеры — Б/событие, включая M7-заголовок, dictionary ID и CRC, при пачках
до 100. 200 событий с неизвестными схемами оплачены полным V1 gzip fallback.
HTTP/TLS, ACK, повторные отправки и setup в этой таблице не включены.
DB jsonb не хранит исходные HTTP-байты/порядок ключей/границы пачек: V1 здесь
реконструирован. ~800–850 Б из манифеста были размером несжатого JSON старого
синтетического корпуса, а не измеренным gzip-трафиком production.

¹ Удаление interaction GUID — **условная миграция**, не готовое безопасное изменение:
в наблюдаемом дне коллизий пары нет, но PlayerPrefs сохраняет счётчик с задержкой.
Crash между enqueue и Save может повторно использовать индекс. Сначала нужен
устойчивый счётчик и перевод серверных потребителей на составной ключ.

Результаты проверены Python roundtrip, восемью тестами протокола и независимым
декодером колонок Go. C# pack+native zstd на .NET10/macOS показывает 0 GC bytes
на 1000 повторений каждой из 6 проверенных fixtures; стандартная библиотека
netstandard2.1 компилируется. Это не замер Unity/IL2CPP/телефона. C# и Go здесь
проверяют колоночный этап, не весь SDK/HTTP delivery pipeline.

Объём в 5–7 Б не обеспечивается словарём: исходный случайный event UUID сам несёт
около 16 несжимаемых байт/событие. Отказ от него требует отдельной миграции
дедупликации на (project, immutable origin_install, sequence), включая reset/retry.
Существующий resetIdentity переписывает install_id очереди; включать такой режим
в текущий SDK без исправления origin нельзя.

Артефакты: [аудит игры](01-game-deduplication-audit.md),
[матрица](02-benchmark-v7.md), [протокол](03-protocol-and-integration.md),
[CPU/GC и ограничения](04-cpu-memory-and-device.md),
[воспроизведение](06-experiments/README.md),
[машинная проверка](06-experiments/results/verification.json).
'''
    if (R/'numeric-benchmark.json').exists():
        candidate=read('numeric-benchmark.json')
        raw,clean=candidate
        extra=f"Дополнительная generic integer model улучшила holdout до **{raw['B_event']['dict32']:.2f} Б/событие** на исходных и **{clean['B_event']['dict32']:.2f} Б** на условно очищенных данных, без исходных event UUID. С их сохранением clean dict16 = **{clean['B_event']['full_ids_dict16']:.2f} Б**. Все пять режимов дополнительно проверены C#/Python/Go; C# по-прежнему 0 GC на host. Подробности: [дополнительная модель чисел](05-integer-model-evaluation.md). Цели трафика и mobile gates остаются открыты.\n\n"
        summary=summary.replace('Артефакты:',extra+'Артефакты:')
        text="""# Дополнительная generic integer model

Это продолжение V7 после исходного columnar+dictionary benchmark. Старые totals
сохранены как baseline. Цель — уменьшить остаточную избыточность числовых колонок
универсальным алгоритмом, без игровых имён в codec.

На том же дне и том же разбиении по установкам:19882 train,63943 holdout,
по 600 первых событий на установку. Оба размера словаря заданы заранее,
словари обучены только на train в новом представлении.200 событий с неизвестной
схемой по-прежнему оплачены full V1 gzip fallback. Identity contract для legacy
колонок исключает original event UUID; full-ID колонка оплачивает его полностью.

| Вариант | V7 baseline dict32 | Integer model dict16 | Integer model dict32 | Integer model full UUID dict16 |
|---|---:|---:|---:|---:|
"""
        for row,base in zip(candidate,real[::2]):
            b=row['B_event'];text+=f"| {row['variant']} | {base['B_event']['v7_dict32']:.3f} | {b['dict16']:.3f} | {b['dict32']:.3f} | {b['full_ids_dict16']:.3f} |\n"
        text+="""
Единица — Б/событие, весь frame и CRC включены, setup/HTTP/retry исключены.
Каждый успешно закодированный batch декодирован и сравнён по всем typed values.
Критерии raw<13 и clean<7 всё ещё не выполнены. Эта модель не удаляет SHA или
GUID: game cleanup остаётся отдельным условным преобразованием.

## Формат и проверка

С flag2 signed-int property column получает opcode0..4: исходный V6 packer,
разность с timestamp/sequence/session_elapsed_ms либо integer dictionary+indices.
Самый короткий raw кандидат выбирается до zstd с оплаченным opcode. Переполнение
исключает кандидат; decoder отбрасывает invalid opcode/index/range. Поля кадра,
UUID и остальные типы остаются прежними. Дополнительная программа не переносит
игровые правила в SDK и не обучается на значениях holdout.

В probe несжатая экономия составила 2.460 Б/событие. Наиболее заметны active_elapsed_ms
и event counters; эти имена есть только в диагностике и проектных данных.
Экономию raw нельзя целиком переносить на результат zstd: часть паттернов уже
сжимал старый компрессор. Фактический эффект приведён выше.

Новый C# packer использует preallocated scratch arrays и integer dictionary.
Шесть fixtures: synthetic100, edge int64/uint64/signed-zero/Unicode/Decimal,
500 rows, специальная 500-row проверка всех opcodes, actual raw100 и clean100.
Все прошли независимый Go decoder и Python roundtrip, по 1000 pack+native-zstd
повторений на .NET/macOS с 0 managed GC bytes. Original/default режим также
повторно проверен. Статическая netstandard2.1 библиотека компилируется.

"""
        natives=read('native-numeric.json')
        for row in natives:
            if row['fixture'].startswith('candidate-real'):
                text+=f"C# {row['fixture']}: {row['mean_ms']:.3f} мс/100 событий, {row['gc_bytes']} GC bytes на {row['iterations']} повторений.\n\n"
        text+="""Это host typed-column stage, не Unity/IL2CPP и не телефон; framing/CRC/ingress/JNI/HTTP
в замер не входят. Полный Python encode100 p50 примерно 7 мс, а первоначальный
вариант был около 2–3 мс. Дополнительные кандидаты имеют цену CPU: быстрее на
телефоне они не объявлены. Нагрев/энергия и production integration не проверены.

Воспроизведение: `06-experiments/run_numeric.sh`. Основные доказательства:
`results/numeric-benchmark.json`, `native-numeric.json`, `go-check-numeric.json`,
`numeric-tests.log`. Полный generic codec —transport7.py/numeric7.py; C# —native/Columns.cs,
Go —go/main.go. Эта работа продвинула размер и сохраняет host Zero-GC, но не
закрывает исходные критерии V7.
"""
        (DOC/'05-integer-model-evaluation.md').write_text(text)
    if (R/'tables-benchmark.json').exists():
        from export_tables7 import run as tables_report
        summary+=tables_report()
    if (R/'native-frames-corpus.json').exists():
        from export_frames7 import run as frames_report
        frames_report()
        summary+='\nC# теперь самостоятельно формирует полный M7 packet, включая header/CRC:1306 native packets двух представлений holdout декодированы Python, итоговые byte totals точно совпали. Host0 GC подтверждён для pretyped pack+zstd+framing, но Unity framing/Go receiver/SDK ingress не проверены. [Полные C# пакеты](09-full-packet-validation.md).\n'
    if (R/'go-frames.json').exists():
        from export_go_frames7 import run as go_frames_report
        go_frames_report()
        summary+='\nGo независимо декодирует полный M7 по project catalog/aliases без fixture row hints:1316 C# packets/128787 событий с учётом повторных представлений, все source typed values совпали;112 malformed/auth cases отвергнуты. HTTP/persistence/ACK пока отсутствуют. [Go packet decoder](10-go-packet-validation.md).\n'
    (DOC/'00-summary.md').write_text(summary)
    out='''# Матрица V7

Единица: полное бинарное тело/число событий. V4/V6/V7 в исторических колонках
сравниваются без исходного event_id; V1 full и V7 full сохраняют UUID.
V1 legacy gzip даёт baseline с тем же исключением UUID. Нельзя считать это
готовой заменой текущего сервера, который дедуплицирует event_id.
V4 — исходный reference core+zstd19/dict64KiB, а не просто сжатие JSON строк.

## События из production DB, holdout63943

| Вариант | V1 full gzip1 | V1 legacy gzip1 | V4 | V6 | V7 без словаря | V7 dict16 | V7 dict32 | V7 full dict16 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
'''
    keys=['v1_gzip1','v1_gzip1_legacy_ids','v4_zstd19','v6_zstd1','v7_nodict','v7_dict16','v7_dict32','v7_full_ids_dict16']
    for row in real:out+='| '+row['variant']+' | '+' | '.join(f"{row['B_event'][k]:.3f}"for k in keys)+' |\n'
    out+='''
Каждый V7 результат декодирован и сравнен с исходными типизированными событиями,
включая значения/типы полей, integer и floating semantics (порядок JSON ключей нормализован). V4 также полностью
декодирован; V6 используется как замороженный reference baseline. Ранее сохранённые
результаты V2–V6 и product inputs защищены SHA256 594 файлов.

## Setup и словари

Shared dictionary/catalog — артефакты build-time: при встроенном asset они не
передаются с каждым пакетом, но увеличивают размер сборки. Вариант скачивания
через handshake должен платить их для каждой новой установки/версии.
Столбец ниже с одной копией asset — только амортизация build-time общего ресурса;
это не честная стоимость отдельного download каждому клиенту.

| Вариант | Каталог, Б | alias requests+ACK, Б | dict16 с одной копией catalog/dict + aliases, Б/соб | dict16 download каждому holdout install + aliases, Б/соб |
|---|---:|---:|---:|---:|
'''
    for row in real:
        cold=(row['bytes']['v7_dict16']+row['alias_setup_bytes']+audit['holdout_installs']*(row['schema_bytes']+16384+16))/row['events']
        out+=f"| {row['variant']} | {row['schema_bytes']} | {row['alias_setup_bytes']} | {row['dict16_setup_inclusive_B_event']:.3f} | {cold:.3f} |\n"
    out+='''
Download estimate counts raw dictionary+descriptor+16B confirmation; actual
HTTP/auth/retry setup is not implemented. Alias table negotiations are serialized
and paid.200 fallback events occur in2 batches: train-only catalog did not learn
all shapes. No test-time catalog retraining, dropped events or dictionary leakage.

## Замороженные синтетические профили

Обучение 202, независимые 101/1729/2601. `safe_clean` удаляет только проверенный
wave-дубль и выводимые поля: старый generator не содержит реальную CSV/SHA связь
и interaction_index. Поэтому его непредсказуемые SHA сохранены. Отнимать их
из размера, называя данные очищенными, было бы подменой эксперимента.

| Профиль | Seed | Вариант | События | V1 full gzip | V6 | V6+dict16¹ | V7 dict16 | V7 dict32 | V7 full | Fallback events |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
'''
    for profile in ('base','rich','alt','drift'):
        for row in read(f'bench-{profile}.json')['rows']:
            b=row['B_event'];out+=f"| {profile} | {row['seed']} | {row['variant']} | {row['events']} | "+' | '.join(f'{b[k]:.3f}'for k in ('v1_gzip1','v6_zstd1','v6_dict16','v7_dict16','v7_dict32','v7_full_ids_dict16'))+f" | {row.get('fallback_events',0)} |\n"
    out+='''
¹ Контрольная абляция: неизменённый raw V6 +zstd1/dict16 с оплаченным 8B ID.
Это размерная оценка кадра с новым compressor asset, а не новый V6 серверный codec.
В clean-вариантах V4/V6/V7 обучаются на соответствующем clean train; каталог и
словарь не оставляются от несовместимого raw-представления.
Dictionary32 не выбирался после просмотра test: оба размера заданы заранее.
Средние взвешены событиями, последние короткие пачки включены. Короткие drift
пачки несут больше framing overhead. Сырые totals, source SHA и окружение в JSON.

Словарь полезен, когда в независимых малых samples есть общая структура;
универсальной гарантии размера он не даёт: [Zstandard README](https://github.com/facebook/zstd/blob/v1.5.7/README.md).
'''
    (DOC/'02-benchmark-v7.md').write_text(out)
    if (R/'unity-editor.json').exists()and(R/'unity-android.json').exists():
        editor=read('unity-editor.json');android=read('unity-android.json')
        summary=summary.replace('Это не замер Unity/IL2CPP/телефона.','Эти .NET замеры относятся к host; отдельная проверка Unity приведена ниже.')
        count=len(editor['measurements'])
        summary+=f'\nПроверены также Unity Editor Mono и **Android15/17 ARM64 Development IL2CPP на эмуляторах 4KB/16KB**:{count}+{count}+{count} fixtures, по 1000 упаковок,0 GC.Alloc, побайтное совпадение raw buffers. Счётчик проверен положительным/пустым контролем. Это pretyped columns+zstd; полный ingress/framing/HTTP и физический телефон не измерены. [Доказательства Unity](06-unity-runtime-validation.md).\n'
        (DOC/'00-summary.md').write_text(summary)
        text="""# Unity runtime: Editor Mono и Android IL2CPP

Создан изолированный Unity6000.3.16f1 проект в ignored results/private/unity-player.
SDK Runtime/, Puzzle и сервер не изменялись. Отдельный пакет
com.daliys.transport7.research запущен на AVD Mortris_API_35 (Android15, arm64-v8a,
qemu=1). APK содержит libil2cpp.so и отдельно собранный libzstd.so1.5.7.
Исходный zstd archive, compiler command, source/plugin hashes записаны в
results/android-native-build.json; APK hash —в unity-android.json.

Дополнительно тот же APK проверен на Pixel_8 Android17 с 16KB страницами:
ещё FIXTURE_COUNT fixtures проходят калибровку,0 GC и raw parity. У native zstd выставлены
max/common page size 16384; APK проходит zipalign -P16. Unity/Gradle stripping
проверяется точным SHA преобразованного llvm-strip --strip-unneeded plugin,
а не сравнением APK с не-stripped исходным ELF. Различие container SHA не скрыто.

## Проверка GC

GC.GetAllocatedBytesForCurrentThread здесь вернул 0 даже после new byte[4096].
Этот API не использован как доказательство. Использован Unity ProfilerRecorder,
категория Internal, маркер GC.Alloc, только текущий поток и отдельные samples.
Контроль 4096B даёт 1 событие, пустой интервал 0. В каждом измеряемом интервале
FIXTURE_COUNT fixtures ×1000 pack+native-zstd итераций:0 событий, следовательно 0 managed GC
bytes в проверенном синхронном этапе. Оба runtime проходят калибровку отдельно.
Маркеры и thread scoping описаны в [официальном API](https://docs.unity.com/en-us/engine/6000.5/script-reference/unity/profiling/profilerrecorderoptions/collectonlyoncurrentthread).

Input loading, JSON/ZIP/JNI, typed cells и persistent workspaces готовятся до
warmup 200 операций. Начало/конец profiler recorder, serialization/export также
вне таймера. Сам цикл включает C# column packing и reuse CCtx/CDict zstd1.
C# framing/CRC, исходный SDK ingress/queue/JNI/HTTP/retry не входят в этот тест.
Нет доказательства 0 allocations на ошибочных/неподдерживаемых input paths.

## Настоящие 100-event fixtures

| Fixture | Editor Mono, mean ms | Android15/4KB IL2CPP, mean ms | Android17/16KB IL2CPP, mean ms | GC.Alloc/1000 packs |
|---|---:|---:|---:|---:|
"""
        em={r['fixture']:r for r in editor['measurements']}
        mobile16=read('unity-android-16k.json')if(R/'unity-android-16k.json').exists()else None
        mapped16={r['fixture']:r for r in mobile16['measurements']}if mobile16 else {}
        for row in android['measurements']:
            if 'real-'in row['fixture']:
                value16=f"{mapped16[row['fixture']]['mean_ms']:.4f}"if row['fixture']in mapped16 else 'not run'
                text+=f"| {row['fixture']} | {em[row['fixture']]['mean_ms']:.4f} | {row['mean_ms']:.4f} | {value16} | {row['gc_alloc_samples']} |\n"
        text+="""
Это средние, не p95/p99 и не physical-phone latency. Синхронный benchmark не
является проверкой FPS/thermal/energy: его многократные операции намеренно
занимают игровой поток. На реальном телефоне результаты могут отличаться.
Development IL2CPP применён для действующего allocation profiler; release CPU
отдельно пока не измерена. Требования отсутствия нагрева/фризов остаются открыты.

Остальные fixtures покрывают int64 overflow, uint64 max, IEEE -0.0, Unicode,
Decimal lexeme,500 events и все 5 дополнительных numeric opcodes. Все FIXTURE_COUNT буферов
из каждого runtime побайтно совпадают с .NET fixtures, которые независимо
декодированы Python и Go. verify_unity7.py проверяет каждый буфер и counter
controls, а также наличие IL2CPP и SHA native plugin внутри APK.

## Среда и воспроизведение

Android поддержка была уже установлена в version-root/PlaybackEngines/AndroidPlayer
вместе с SDK/NDK/JDK. Прежний вывод об отсутствии, основанный только на
Unity.app/Contents/PlaybackEngines, был ошибочным. BuildPipeline.IsBuildTargetSupported
возвращает true. Ничего не переустанавливалось и не перемещалось.

prepare_unity7.py создаёт проект из публичных harness templates и private fixtures.
prepare_android7.py использует существующий NDK и pinned zstd 1.5.7 source; сборка
плагина остаётся внутри V7. Android assets читаются как entries APK ZIP до
измерения; результаты пишутся в getFilesDir тестового приложения, доступны
через run-as. Удаляется только сгенерированный benchmark-output своего пакета,
перед повтором —это защита от чтения старого report. Игра не запускается.

Команда:06-experiments/run_unity7.sh. Существующие FIXTURE_COUNT host fixtures и private day
нужны заранее; полный baseline воспроизводится run_all.sh/run_numeric.sh.
Стенд использует уже существующий AVD. Generated project/cache/APK и реальные
payloads остаются ignored/private, aggregate reports и scripts доступны в V7.

**Подтверждено:** scoped Unity/Android IL2CPP Zero-GC для typed column+zstd этапа.
**Открыто:** цели трафика, full SDK integration/framing, release/physical-phone CPU,
thermal/FPS и production game/server migration. Цель V7 полностью не закрыта.
"""
        text=text.replace('FIXTURE_COUNT',str(count))
        if (R/'native-tables.json').exists():text+='\nДополнительно проверены четыре string-model fixtures: все opcodes0..4, Unicode500 и реальные raw/clean100. C#/Python raw byte parity и независимый Go decoder подтверждены; Unity проверяет те же буферы.\n'
        (DOC/'06-unity-runtime-validation.md').write_text(text)

if __name__=='__main__':run()
