
## init_mortris_v1 (3 повтора)

Событий: 1; длительность сценария 0.0 с; CPU приложения за сценарий 0 мс, за хвост 29367 мс; Mono GC0 0; ART 0 КБ; Unity GC alloc 0 КБ

| стадия | вызовов/событие | wall мкс/событие | CPU мкс/событие | рост кучи Б/событие | p50 мкс | p99 мкс | max мкс |
|---|---|---|---|---|---|---|---|
| worker.pass | 2.00 | 9384214.7 | 26135.0 | 789163 | 9315676 | 68538 | 9315676 |
| worker.upload | 2.00 | 9315618.3 | 6321.7 | 275797 | 9315589 | 28 | 9315589 |
| upload.flush | 2.00 | 9315606.7 | 6313.0 | 238933 | 9315585 | 22 | 9315585 |
| init.total | 1.00 | 122852.3 | 115749.7 | 285355 | 122852 | 122852 | 122852 |
| init.runtime | 1.00 | 118737.7 | 114531.3 | 258048 | 118738 | 118738 | 118738 |
| init.worker | 1.00 | 117522.7 | 114038.0 | 177493 | 117523 | 117523 | 117523 |
| init.device_context | 1.00 | 115761.7 | 113008.0 | 72363 | 115762 | 115762 | 115762 |
| device.timezone | 1.00 | 114998.3 | 112548.3 | 17749 | 114998 | 114998 | 114998 |
| bridge.create | 1.00 | 57197.7 | 12529.3 | 2731 | 57198 | 57198 | 57198 |
| worker.write_buffer | 1.00 | 6065.7 | 3295.7 | 70997 | 6066 | 6066 | 6066 |
| worker.buffer_drain | 2.00 | 2335.7 | 299.0 | 1365 | 2334 | 0 | 2334 |
| init.lifecycle | 1.00 | 2198.0 | 999.3 | 0 | 2198 | 2198 | 2198 |
| session.recover | 1.00 | 1634.7 | 965.0 | 36864 | 1635 | 1635 | 1635 |
| init.uploader | 1.00 | 997.0 | 535.0 | 124245 | 997 | 997 | 997 |
| init.http_client | 1.00 | 497.7 | 313.3 | 1365 | 498 | 498 | 498 |
| init.session_start | 1.00 | 448.3 | 129.0 | 90112 | 448 | 448 | 448 |
| init.event_context | 1.00 | 292.7 | 104.0 | 0 | 293 | 293 | 293 |
| worker.attach | 2.00 | 207.0 | 109.3 | 0 | 164 | 43 | 164 |
| jni.enqueue | 1.00 | 174.0 | 173.7 | 0 | 174 | 174 | 174 |
| device.culture | 1.00 | 167.0 | 90.3 | 1365 | 167 | 167 | 167 |
| init.timers | 1.00 | 166.0 | 161.7 | 20480 | 166 | 166 | 166 |
| init.session_tracker | 1.00 | 152.0 | 45.3 | 1365 | 152 | 152 | 152 |
| device.app | 1.00 | 140.7 | 140.3 | 21845 | 141 | 141 | 141 |
| jni.get_state | 1.00 | 138.3 | 138.7 | 0 | 138 | 138 | 138 |
| init.limiter | 1.00 | 116.0 | 116.0 | 0 | 116 | 116 | 116 |
| jni.session | 2.00 | 111.7 | 112.3 | 0 | 66 | 45 | 66 |
| worker.save_session | 2.00 | 92.3 | 91.7 | 8192 | 91 | 0 | 91 |
| worker.evicted_read | 2.00 | 50.7 | 50.0 | 36864 | 50 | 0 | 50 |
| track.encode | 1.00 | 49.3 | 49.7 | 0 | 49 | 49 | 49 |
| jni.meta | 1.00 | 42.0 | 42.0 | 0 | 42 | 42 | 42 |
| worker.complete | 2.00 | 29.3 | 29.3 | 0 | 28 | 1 | 28 |
| worker.detach | 2.00 | 29.0 | 29.0 | 0 | 15 | 13 | 15 |
| init.v7_session | 1.00 | 8.0 | 8.0 | 0 | 8 | 8 | 8 |
| device.model | 1.00 | 6.3 | 4.7 | 0 | 6 | 6 | 6 |
| device.os | 1.00 | 3.3 | 3.3 | 0 | 3 | 3 | 3 |
| worker.idle_check | 2.00 | 2.3 | 3.3 | 0 | 1 | 0 | 1 |
| init.v8_session | 1.00 | 0.0 | 0.0 | 0 | 0 | 0 | 0 |
| track.buffer | 1.00 | 0.0 | 0.0 | 0 | 0 | 0 | 0 |

Счётчики: events_written=1, worker_passes=2, worker_writes=1

Java-очередь (за сценарий, среднее по повторам):

| этап | вызовов | wall мкс всего | CPU мкс всего (итоги) | ART КБ всего (итоги) | max мкс |
|---|---|---|---|---|---|
| enq.bounds | 1 | 1 | 0 | 0 | 1 |
| enq.commit | 1 | 27 | 0 | 0 | 27 |
| enq.counters | 1 | 0 | 0 | 0 | 0 |
| enq.expire | 1 | 0 | 0 | 0 | 0 |
| enq.insert_exec | 1 | 19 | 0 | 0 | 19 |
| enq.insert_loop | 1 | 60 | 0 | 0 | 60 |
| enq.meta_sequence | 1 | 15 | 0 | 0 | 15 |
| enq.total | 1 | 148 | 136 | 0 | 148 |
| meta_get | 1 | 25 | 0 | 0 | 25 |
| session_load | 1 | 23 | 0 | 0 | 23 |
| session_save | 1 | 25 | 0 | 0 | 25 |
| state | 1 | 10 | 0 | 0 | 10 |

Потоки процесса за сценарий (мс CPU): UnityMain=10, UnityGfxDeviceW=10

Таймлайн первого запуска (мс от сброса таймеров; поток; стадия; длительность мс):

| начало мс | поток | стадия | длит. мс |
|---|---|---|---|
| 21.0 | 1 | init.total | 144.20 |
| 25.5 | 1 | init.runtime | 135.46 |
| 25.5 | 1 | init.limiter | 0.12 |
| 25.7 | 1 | init.worker | 134.27 |
| 25.9 | 1 | init.device_context | 131.88 |
| 26.4 | 1 | device.app | 0.16 |
| 26.5 | 1 | device.os | 0.00 |
| 26.5 | 1 | device.model | 0.00 |
| 26.5 | 1 | device.culture | 0.44 |
| 27.0 | 1 | device.timezone | 130.10 |
| 157.7 | 1 | init.event_context | 0.00 |
| 157.8 | 1 | init.uploader | 1.62 |
| 158.1 | 1 | init.http_client | 1.04 |
| 159.4 | 1 | init.v7_session | 0.01 |
| 159.4 | 1 | init.v8_session | 0.00 |
| 159.8 | 1 | init.timers | 0.19 |
| 159.9 | 1 | init.session_tracker | 0.43 |
| 160.4 | 1 | init.session_start | 0.19 |
| 161.0 | 1 | init.lifecycle | 4.15 |
| 362.6 | 7 | worker.pass | 101.67 |
| 362.6 | 7 | worker.idle_check | 0.00 |
| 362.6 | 7 | worker.attach | 0.04 |
| 362.6 | 7 | bridge.create | 71.36 |
| 434.0 | 7 | session.recover | 4.76 |
| 445.1 | 7 | worker.write_buffer | 17.93 |
| 445.1 | 7 | worker.buffer_drain | 7.00 |
| 463.0 | 7 | worker.save_session | 0.11 |
| 463.1 | 7 | worker.evicted_read | 0.08 |
| 464.2 | 7 | worker.upload | 0.03 |
| 464.2 | 7 | upload.flush | 0.03 |
| 464.2 | 7 | worker.detach | 0.02 |
| 464.2 | 7 | worker.complete | 0.03 |
| 4005.3 | 10 | worker.pass | 9390.70 |
| 4005.3 | 10 | worker.idle_check | 0.00 |
| 4005.4 | 10 | worker.attach | 0.06 |
| 4005.4 | 10 | worker.buffer_drain | 0.00 |
| 4005.4 | 10 | worker.save_session | 0.00 |
| 4005.4 | 10 | worker.evicted_read | 0.00 |
| 4005.4 | 10 | upload.flush | 9390.57 |
| 4005.4 | 10 | worker.upload | 9390.58 |
| 13396.0 | 10 | worker.detach | 0.02 |
| 13396.0 | 10 | worker.complete | 0.00 |

## init_mortris_v7 (3 повтора)

Событий: 1; длительность сценария 0.0 с; CPU приложения за сценарий 0 мс, за хвост 28777 мс; Mono GC0 0; ART 0 КБ; Unity GC alloc 0 КБ

| стадия | вызовов/событие | wall мкс/событие | CPU мкс/событие | рост кучи Б/событие | p50 мкс | p99 мкс | max мкс |
|---|---|---|---|---|---|---|---|
| worker.pass | 2.00 | 9490983.7 | 10175.0 | 797355 | 9461697 | 29286 | 9461697 |
| worker.upload | 2.00 | 9461645.7 | 5184.0 | 290816 | 9461621 | 24 | 9461621 |
| upload.flush | 2.00 | 9461636.7 | 5176.7 | 253952 | 9461618 | 19 | 9461618 |
| init.total | 1.00 | 123694.3 | 113339.7 | 285355 | 123694 | 123694 | 123694 |
| init.runtime | 1.00 | 121379.7 | 112455.7 | 258048 | 121380 | 121380 | 121380 |
| init.worker | 1.00 | 114645.3 | 112004.0 | 177493 | 114645 | 114645 | 114645 |
| init.device_context | 1.00 | 113257.0 | 111092.3 | 152917 | 113257 | 113257 | 113257 |
| device.timezone | 1.00 | 112611.0 | 110705.7 | 28672 | 112611 | 112611 | 112611 |
| bridge.create | 1.00 | 27166.3 | 3839.3 | 0 | 27166 | 27166 | 27166 |
| init.session_start | 1.00 | 6080.0 | 187.7 | 90112 | 6080 | 6080 | 6080 |
| init.lifecycle | 1.00 | 1534.0 | 631.3 | 0 | 1534 | 1534 | 1534 |
| init.uploader | 1.00 | 668.0 | 439.0 | 124245 | 668 | 668 | 668 |
| session.recover | 1.00 | 426.3 | 266.3 | 32768 | 426 | 426 | 426 |
| init.timers | 1.00 | 301.7 | 220.0 | 13653 | 302 | 302 | 302 |
| init.http_client | 1.00 | 281.7 | 250.7 | 1365 | 282 | 282 | 282 |
| worker.evicted_read | 2.00 | 234.0 | 133.7 | 32768 | 234 | 0 | 234 |
| worker.save_session | 2.00 | 169.7 | 118.7 | 8192 | 169 | 0 | 169 |
| device.culture | 1.00 | 156.7 | 92.3 | 1365 | 157 | 157 | 157 |
| worker.complete | 2.00 | 153.0 | 78.7 | 0 | 151 | 2 | 151 |
| init.event_context | 1.00 | 143.7 | 54.7 | 0 | 144 | 144 | 144 |
| track.encode | 1.00 | 140.0 | 61.7 | 0 | 140 | 140 | 140 |
| init.session_tracker | 1.00 | 139.7 | 39.3 | 1365 | 140 | 140 | 140 |
| device.app | 1.00 | 132.7 | 132.7 | 21845 | 133 | 133 | 133 |
| init.limiter | 1.00 | 125.7 | 116.3 | 0 | 126 | 126 | 126 |
| jni.get_state | 1.00 | 104.0 | 104.3 | 0 | 104 | 104 | 104 |
| worker.write_buffer | 1.00 | 103.0 | 103.0 | 73728 | 103 | 103 | 103 |
| worker.attach | 2.00 | 93.7 | 84.0 | 2731 | 57 | 36 | 57 |
| jni.enqueue | 1.00 | 84.0 | 84.0 | 0 | 84 | 84 | 84 |
| jni.session | 2.00 | 69.7 | 70.0 | 0 | 37 | 32 | 37 |
| init.v7_session | 1.00 | 44.3 | 44.3 | 0 | 44 | 44 | 44 |
| worker.detach | 2.00 | 24.3 | 24.3 | 0 | 15 | 9 | 15 |
| jni.meta | 1.00 | 23.3 | 23.3 | 0 | 23 | 23 | 23 |
| device.os | 1.00 | 3.3 | 3.3 | 0 | 3 | 3 | 3 |
| device.model | 1.00 | 3.0 | 3.0 | 0 | 3 | 3 | 3 |
| worker.buffer_drain | 2.00 | 1.7 | 1.7 | 0 | 1 | 0 | 1 |
| worker.idle_check | 2.00 | 0.7 | 1.0 | 0 | 0 | 0 | 0 |
| track.buffer | 1.00 | 0.3 | 0.3 | 0 | 0 | 0 | 0 |
| init.v8_session | 1.00 | 0.0 | 0.0 | 0 | 0 | 0 | 0 |

Счётчики: events_written=1, worker_passes=2, worker_writes=1

Java-очередь (за сценарий, среднее по повторам):

| этап | вызовов | wall мкс всего | CPU мкс всего (итоги) | ART КБ всего (итоги) | max мкс |
|---|---|---|---|---|---|
| enq.bounds | 1 | 0 | 0 | 0 | 0 |
| enq.commit | 1 | 14 | 0 | 0 | 14 |
| enq.counters | 1 | 0 | 0 | 0 | 0 |
| enq.expire | 1 | 0 | 0 | 0 | 0 |
| enq.insert_exec | 1 | 10 | 0 | 0 | 10 |
| enq.insert_loop | 1 | 33 | 0 | 0 | 33 |
| enq.meta_sequence | 1 | 6 | 0 | 0 | 6 |
| enq.total | 1 | 72 | 67 | 0 | 72 |
| meta_get | 1 | 12 | 0 | 0 | 12 |
| session_load | 1 | 18 | 0 | 0 | 18 |
| session_save | 1 | 15 | 0 | 0 | 15 |
| state | 1 | 9 | 0 | 0 | 9 |

Потоки процесса за сценарий (мс CPU): UnityMain=10

Таймлайн первого запуска (мс от сброса таймеров; поток; стадия; длительность мс):

| начало мс | поток | стадия | длит. мс |
|---|---|---|---|
| 19.9 | 1 | init.total | 110.42 |
| 20.4 | 1 | init.runtime | 108.37 |
| 20.5 | 1 | init.limiter | 0.15 |
| 20.6 | 1 | init.worker | 107.26 |
| 20.7 | 1 | init.device_context | 105.70 |
| 20.8 | 1 | device.app | 0.12 |
| 20.9 | 1 | device.os | 0.00 |
| 20.9 | 1 | device.model | 0.00 |
| 20.9 | 1 | device.culture | 0.03 |
| 21.0 | 1 | device.timezone | 105.48 |
| 126.5 | 1 | init.event_context | 0.42 |
| 126.9 | 1 | init.uploader | 0.83 |
| 126.9 | 1 | init.http_client | 0.21 |
| 127.1 | 1 | init.v7_session | 0.05 |
| 127.2 | 1 | init.v8_session | 0.00 |
| 127.7 | 1 | init.timers | 0.16 |
| 128.3 | 1 | init.session_tracker | 0.01 |
| 128.3 | 1 | init.session_start | 0.48 |
| 128.8 | 1 | init.lifecycle | 1.54 |
| 332.4 | 7 | worker.pass | 26.09 |
| 332.5 | 7 | worker.idle_check | 0.00 |
| 332.5 | 7 | worker.attach | 0.08 |
| 332.6 | 7 | bridge.create | 24.78 |
| 357.4 | 7 | session.recover | 0.06 |
| 357.4 | 7 | worker.buffer_drain | 0.00 |
| 357.4 | 7 | worker.write_buffer | 0.09 |
| 358.0 | 7 | worker.save_session | 0.05 |
| 358.0 | 7 | worker.evicted_read | 0.03 |
| 358.1 | 7 | worker.upload | 0.02 |
| 358.1 | 7 | upload.flush | 0.02 |
| 358.5 | 7 | worker.detach | 0.01 |
| 358.5 | 7 | worker.complete | 0.02 |
| 4011.6 | 9 | worker.pass | 8961.26 |
| 4011.6 | 9 | worker.idle_check | 0.00 |
| 4011.6 | 9 | worker.attach | 0.04 |
| 4011.7 | 9 | worker.buffer_drain | 0.00 |
| 4011.7 | 9 | worker.save_session | 0.00 |
| 4011.7 | 9 | worker.evicted_read | 0.00 |
| 4011.7 | 9 | worker.upload | 8961.18 |
| 4011.7 | 9 | upload.flush | 8961.18 |
| 12972.9 | 9 | worker.detach | 0.01 |
| 12972.9 | 9 | worker.complete | 0.00 |

## init_mortris_v8 (3 повтора)

Событий: 1; длительность сценария 0.0 с; CPU приложения за сценарий 0 мс, за хвост 29270 мс; Mono GC0 0; ART 0 КБ; Unity GC alloc 0 КБ

| стадия | вызовов/событие | wall мкс/событие | CPU мкс/событие | рост кучи Б/событие | p50 мкс | p99 мкс | max мкс |
|---|---|---|---|---|---|---|---|
| worker.pass | 2.00 | 9304667.0 | 11769.0 | 951637 | 9272022 | 32644 | 9272022 |
| worker.upload | 2.00 | 9271959.0 | 5672.7 | 447829 | 9271927 | 32 | 9271927 |
| upload.flush | 2.00 | 9271951.0 | 5665.7 | 410965 | 9271925 | 26 | 9271925 |
| v8.send | 1.00 | 9269227.3 | 4985.7 | 337237 | 9269227 | 9269227 | 9269227 |
| v8.hello | 1.00 | 9264806.3 | 4181.7 | 255317 | 9264806 | 9264806 | 9264806 |
| init.total | 1.00 | 113186.3 | 108526.7 | 283989 | 113186 | 113186 | 113186 |
| init.runtime | 1.00 | 110871.7 | 107656.3 | 255317 | 110872 | 110872 | 110872 |
| init.worker | 1.00 | 109839.7 | 107172.7 | 174763 | 109840 | 109840 | 109840 |
| init.device_context | 1.00 | 108037.3 | 105850.3 | 150187 | 108037 | 108037 | 108037 |
| device.timezone | 1.00 | 107346.3 | 105416.3 | 30037 | 107346 | 107346 | 107346 |
| bridge.create | 1.00 | 28616.3 | 4748.3 | 0 | 28616 | 28616 | 28616 |
| init.lifecycle | 1.00 | 1681.3 | 660.3 | 1365 | 1681 | 1681 | 1681 |
| init.uploader | 1.00 | 1015.0 | 791.0 | 129707 | 1015 | 1015 | 1015 |
| session.recover | 1.00 | 580.7 | 228.0 | 32768 | 581 | 581 | 581 |
| init.v8_session | 1.00 | 535.0 | 431.3 | 5461 | 535 | 535 | 535 |
| init.session_start | 1.00 | 459.0 | 200.3 | 91477 | 459 | 459 | 459 |
| init.timers | 1.00 | 318.0 | 248.3 | 9557 | 318 | 318 | 318 |
| jni.meta | 11.00 | 284.0 | 240.0 | 0 | 6 | 80 | 100 |
| init.http_client | 1.00 | 276.0 | 256.0 | 1365 | 276 | 276 | 276 |
| jni.sequence_state | 3.00 | 212.0 | 212.3 | 0 | 59 | 59 | 113 |
| worker.save_session | 2.00 | 199.3 | 136.7 | 8192 | 199 | 0 | 199 |
| init.event_context | 1.00 | 161.3 | 53.7 | 0 | 161 | 161 | 161 |
| jni.get_state | 1.00 | 151.7 | 152.0 | 0 | 152 | 152 | 152 |
| device.app | 1.00 | 145.3 | 145.3 | 21845 | 145 | 145 | 145 |
| init.session_tracker | 1.00 | 144.7 | 48.7 | 1365 | 145 | 145 | 145 |
| worker.write_buffer | 1.00 | 143.7 | 143.7 | 73728 | 144 | 144 | 144 |
| device.culture | 1.00 | 141.3 | 81.7 | 0 | 141 | 141 | 141 |
| jni.session | 2.00 | 138.3 | 138.3 | 0 | 77 | 61 | 77 |
| init.limiter | 1.00 | 114.7 | 114.7 | 0 | 115 | 115 | 115 |
| jni.enqueue | 1.00 | 114.7 | 114.7 | 0 | 115 | 115 | 115 |
| worker.attach | 2.00 | 112.3 | 98.0 | 0 | 72 | 40 | 72 |
| track.encode | 1.00 | 88.3 | 77.0 | 0 | 88 | 88 | 88 |
| jni.other | 1.00 | 84.7 | 84.7 | 0 | 85 | 85 | 85 |
| worker.evicted_read | 2.00 | 44.7 | 44.7 | 36864 | 44 | 0 | 44 |
| worker.complete | 2.00 | 37.3 | 37.3 | 0 | 35 | 2 | 35 |
| worker.detach | 2.00 | 30.3 | 30.3 | 0 | 20 | 10 | 20 |
| device.os | 1.00 | 3.7 | 3.7 | 0 | 4 | 4 | 4 |
| device.model | 1.00 | 3.3 | 3.3 | 0 | 3 | 3 | 3 |
| worker.buffer_drain | 2.00 | 2.7 | 2.7 | 0 | 2 | 1 | 2 |
| track.buffer | 1.00 | 0.7 | 0.3 | 0 | 1 | 1 | 1 |
| worker.idle_check | 2.00 | 0.7 | 1.0 | 0 | 0 | 0 | 0 |
| init.v7_session | 1.00 | 0.0 | 0.0 | 0 | 0 | 0 | 0 |

Счётчики: events_written=1, requests=1, worker_passes=2, worker_writes=1

Java-очередь (за сценарий, среднее по повторам):

| этап | вызовов | wall мкс всего | CPU мкс всего (итоги) | ART КБ всего (итоги) | max мкс |
|---|---|---|---|---|---|
| enq.bounds | 1 | 1 | 0 | 0 | 1 |
| enq.commit | 1 | 28 | 0 | 0 | 28 |
| enq.counters | 1 | 0 | 0 | 0 | 0 |
| enq.expire | 1 | 0 | 0 | 0 | 0 |
| enq.insert_exec | 1 | 12 | 0 | 0 | 12 |
| enq.insert_loop | 1 | 41 | 0 | 0 | 41 |
| enq.meta_sequence | 1 | 10 | 0 | 0 | 10 |
| enq.total | 1 | 101 | 95 | 0 | 101 |
| meta_get | 10 | 130 | 0 | 0 | 66 |
| meta_set | 1 | 52 | 0 | 0 | 52 |
| sequence_state | 3 | 176 | 0 | 0 | 91 |
| session_load | 1 | 49 | 0 | 0 | 49 |
| session_save | 1 | 34 | 0 | 0 | 34 |
| state | 1 | 11 | 0 | 0 | 11 |

Таймлайн первого запуска (мс от сброса таймеров; поток; стадия; длительность мс):

| начало мс | поток | стадия | длит. мс |
|---|---|---|---|
| 16.8 | 1 | init.total | 114.58 |
| 17.4 | 1 | init.runtime | 111.91 |
| 17.4 | 1 | init.limiter | 0.11 |
| 17.5 | 1 | init.worker | 111.22 |
| 17.7 | 1 | init.device_context | 109.80 |
| 17.7 | 1 | device.app | 0.14 |
| 17.8 | 1 | device.os | 0.00 |
| 17.8 | 1 | device.model | 0.00 |
| 17.8 | 1 | device.culture | 0.03 |
| 17.9 | 1 | device.timezone | 109.58 |
| 127.5 | 1 | init.event_context | 0.00 |
| 127.5 | 1 | init.uploader | 0.61 |
| 127.5 | 1 | init.http_client | 0.22 |
| 127.7 | 1 | init.v7_session | 0.00 |
| 127.8 | 1 | init.v8_session | 0.33 |
| 128.1 | 1 | init.timers | 0.64 |
| 128.7 | 1 | init.session_tracker | 0.01 |
| 128.8 | 1 | init.session_start | 0.54 |
| 129.3 | 1 | init.lifecycle | 2.08 |
| 329.9 | 7 | worker.pass | 38.14 |
| 329.9 | 7 | worker.idle_check | 0.00 |
| 329.9 | 7 | worker.attach | 0.04 |
| 335.3 | 7 | bridge.create | 30.41 |
| 365.8 | 7 | session.recover | 0.12 |
| 365.9 | 7 | worker.buffer_drain | 0.00 |
| 365.9 | 7 | worker.write_buffer | 0.17 |
| 367.1 | 7 | worker.save_session | 0.17 |
| 367.3 | 7 | worker.evicted_read | 0.07 |
| 367.3 | 7 | worker.upload | 0.04 |
| 367.4 | 7 | upload.flush | 0.04 |
| 368.0 | 7 | worker.detach | 0.02 |
| 368.0 | 7 | worker.complete | 0.04 |
| 4016.3 | 10 | worker.pass | 8698.19 |
| 4016.3 | 10 | worker.idle_check | 0.00 |
| 4016.3 | 10 | worker.attach | 0.06 |
| 4016.4 | 10 | worker.buffer_drain | 0.00 |
| 4016.4 | 10 | worker.save_session | 0.00 |
| 4016.4 | 10 | worker.evicted_read | 0.00 |
| 4016.4 | 10 | worker.upload | 8698.10 |
| 4016.4 | 10 | upload.flush | 8698.10 |
| 4022.8 | 10 | v8.send | 8691.32 |
| 4023.4 | 10 | v8.hello | 8690.64 |
| 12714.5 | 10 | worker.detach | 0.01 |
| 12714.5 | 10 | worker.complete | 0.00 |
