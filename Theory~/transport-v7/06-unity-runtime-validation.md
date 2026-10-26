# Unity runtime: Editor Mono и Android IL2CPP

Создан изолированный Unity6000.3.16f1 проект в ignored results/private/unity-player.
SDK Runtime/, Puzzle и сервер не изменялись. Отдельный пакет
com.daliys.transport7.research запущен на AVD Mortris_API_35 (Android15, arm64-v8a,
qemu=1). APK содержит libil2cpp.so и отдельно собранный libzstd.so1.5.7.
Исходный zstd archive, compiler command, source/plugin hashes записаны в
results/android-native-build.json; APK hash —в unity-android.json.

Дополнительно тот же APK проверен на Pixel_8 Android17 с 16KB страницами:
ещё 16 fixtures проходят калибровку,0 GC и raw parity. У native zstd выставлены
max/common page size 16384; APK проходит zipalign -P16. Unity/Gradle stripping
проверяется точным SHA преобразованного llvm-strip --strip-unneeded plugin,
а не сравнением APK с не-stripped исходным ELF. Различие container SHA не скрыто.

## Проверка GC

GC.GetAllocatedBytesForCurrentThread здесь вернул 0 даже после new byte[4096].
Этот API не использован как доказательство. Использован Unity ProfilerRecorder,
категория Internal, маркер GC.Alloc, только текущий поток и отдельные samples.
Контроль 4096B даёт 1 событие, пустой интервал 0. В каждом измеряемом интервале
16 fixtures ×1000 pack+native-zstd итераций:0 событий, следовательно 0 managed GC
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
| candidate-real-all_clean | 0.2682 | 0.1373 | 0.1365 | 0 |
| candidate-real-raw | 0.3247 | 0.1628 | 0.1647 | 0 |
| real-all_clean | 0.1880 | 0.0867 | 0.0866 | 0 |
| real-hash_wave_clean | 0.2099 | 0.0978 | 0.0966 | 0 |
| real-raw | 0.2417 | 0.1201 | 0.1143 | 0 |
| table-real-all_clean | 0.2709 | 0.1429 | 0.1422 | 0 |
| table-real-raw | 0.3359 | 0.2014 | 0.1776 | 0 |

Это средние, не p95/p99 и не physical-phone latency. Синхронный benchmark не
является проверкой FPS/thermal/energy: его многократные операции намеренно
занимают игровой поток. На реальном телефоне результаты могут отличаться.
Development IL2CPP применён для действующего allocation profiler; release CPU
отдельно пока не измерена. Требования отсутствия нагрева/фризов остаются открыты.

Остальные fixtures покрывают int64 overflow, uint64 max, IEEE -0.0, Unicode,
Decimal lexeme,500 events и все 5 дополнительных numeric opcodes. Все 16 буферов
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

Команда:06-experiments/run_unity7.sh. Существующие 16 host fixtures и private day
нужны заранее; полный baseline воспроизводится run_all.sh/run_numeric.sh.
Стенд использует уже существующий AVD. Generated project/cache/APK и реальные
payloads остаются ignored/private, aggregate reports и scripts доступны в V7.

**Подтверждено:** scoped Unity/Android IL2CPP Zero-GC для typed column+zstd этапа.
**Открыто:** цели трафика, full SDK integration/framing, release/physical-phone CPU,
thermal/FPS и production game/server migration. Цель V7 полностью не закрыта.

Дополнительно проверены четыре string-model fixtures: все opcodes0..4, Unicode500 и реальные raw/clean100. C#/Python raw byte parity и независимый Go decoder подтверждены; Unity проверяет те же буферы.
