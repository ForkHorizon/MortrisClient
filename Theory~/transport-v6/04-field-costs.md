# Стоимость полей

JSON bytes здесь = quoted key + colon + value, без общей запятой/envelope; ts — внутренний integer ms, в реальном V1 occurred_at_client длиннее. Это разложение компонентов, не additive entropy attribution после компрессии. `event_id` включён в field census, хотя legacy comparison его исключает. Считать каждое поле отдельно после zstd и суммировать нельзя: зависимости между полями меняют результат.

Schema+alias payload: name/keys ноль байт на известных формах; session/device/origin ноль value bytes в event, но context-slot column и handshake остаются. event enum/shape mask, sequence/time и property values оплачиваются совместно в raw column streams. При unknown forms имена снова приходят inline. Для каждого поля ниже указан путь восстановления; точный compressed размер всего кадра — в 02.


## base, holdout

| Поле | Значений | JSON component B/event | V6 raw values B/event | V6 schema+aliases |
|---|---|---|---|---|
| app_version | 6646 | 22.000 | 0/ref or shared | alias record + shared slot column |
| build_number | 6646 | 49.000 | 0/ref or shared | alias record + shared slot column |
| device_class | 6646 | 33.521 | 0/ref or shared | alias record + shared slot column |
| event_id | 6646 | 49.000 | 16 (full mode) | 16B/value in full mode; excluded only by legacy contract |
| locale | 6646 | 16.000 | 0/ref or shared | alias record + shared slot column |
| name | 6646 | 23.970 | 0/ref or shared | compiled shape ID column |
| os_version | 6646 | 71.263 | 0/ref or shared | alias record + shared slot column |
| platform | 6646 | 20.000 | 0/ref or shared | alias record + shared slot column |
| properties.active_elapsed_ms | 6241 | 24.074 | 1.440 | key0 on known shape; typed value column |
| properties.ad_format | 14 | 0.055 | 0.034 | key0 on known shape; typed value column |
| properties.app_version | 6646 | 22.000 | 0/ref or shared | context ref if exact type/value; otherwise value column |
| properties.attempt_id | 6530 | 50.110 | 0.355 | key0 on known shape; typed value column |
| properties.attempt_number | 6530 | 17.710 | 0.097 | key0 on known shape; typed value column |
| properties.block_id | 4518 | 8.679 | 0.539 | key0 on known shape; typed value column |
| properties.block_type | 4518 | 14.395 | 1.016 | key0 on known shape; typed value column |
| properties.blocks_in_wave | 175 | 0.486 | 0.036 | key0 on known shape; typed value column |
| properties.cell_x | 1506 | 2.266 | 0.121 | key0 on known shape; typed value column |
| properties.cell_y | 1506 | 2.266 | 0.147 | key0 on known shape; typed value column |
| properties.city_id | 6530 | 10.808 | 0.031 | key0 on known shape; typed value column |
| properties.difficulty | 42 | 0.126 | 0.055 | key0 on known shape; typed value column |
| properties.drag_ms | 1506 | 3.000 | 0.361 | key0 on known shape; typed value column |
| properties.element | 77 | 0.208 | 0.096 | key0 on known shape; typed value column |
| properties.first_session | 25 | 0.078 | 0.004 | key0 on known shape; typed value column |
| properties.hint_type | 72 | 0.224 | 0.096 | key0 on known shape; typed value column |
| properties.hints_left | 72 | 0.152 | 0.018 | key0 on known shape; typed value column |
| properties.house_id | 6530 | 11.791 | 0.072 | key0 on known shape; typed value column |
| properties.launch_type | 25 | 0.075 | 0.030 | key0 on known shape; typed value column |
| properties.moves_count | 1506 | 3.567 | 0.167 | key0 on known shape; typed value column |
| properties.network | 14 | 0.036 | 0.019 | key0 on known shape; typed value column |
| properties.outcome | 1548 | 4.255 | 0.277 | key0 on known shape; typed value column |
| properties.placed_block_count | 4735 | 16.163 | 0.401 | key0 on known shape; typed value column |
| properties.placed_state_hash | 3012 | 38.976 | 6.398 | binary32 distinct + indices; replay bit + anchors |
| properties.placement | 14 | 0.063 | 0.042 | key0 on known shape; typed value column |
| properties.release_x | 1506 | 4.895 | 0.917 | key0 on known shape; typed value column |
| properties.release_y | 1506 | 4.771 | 0.917 | key0 on known shape; typed value column |
| properties.remaining_block_count | 1506 | 5.871 | 0.180 | key0 on known shape; typed value column |
| properties.rotation | 1506 | 2.998 | 0.287 | key0 on known shape; typed value column |
| properties.score | 42 | 0.075 | 0.019 | key0 on known shape; typed value column |
| properties.screen | 77 | 0.220 | 0.081 | key0 on known shape; typed value column |
| properties.slot_index | 1506 | 3.172 | 0.121 | key0 on known shape; typed value column |
| properties.snap_distance | 1506 | 5.868 | 0.917 | key0 on known shape; typed value column |
| properties.target_cell_x | 1506 | 3.852 | 0.121 | key0 on known shape; typed value column |
| properties.target_cell_y | 1506 | 3.852 | 0.146 | key0 on known shape; typed value column |
| properties.total_block_count | 42 | 0.139 | 0.012 | key0 on known shape; typed value column |
| properties.wave_attempt_id | 6530 | 55.023 | 0/ref or shared | attempt_id ref if exact; otherwise value column |
| properties.wave_index | 6446 | 13.579 | 0.272 | key0 on known shape; typed value column |
| sequence | 6646 | 14.065 | 0/ref or shared | integer/residual column |
| session_elapsed_ms | 6646 | 26.648 | 0/ref or shared | integer/residual column |
| session_id | 6646 | 51.000 | 0/ref or shared | alias record + shared slot column |
| timezone_offset_minutes | 6646 | 28.807 | 0/ref or shared | alias record + shared slot column |
| ts | 6646 | 18.000 | 0/ref or shared | integer/residual column |


## rich, holdout

| Поле | Значений | JSON component B/event | V6 raw values B/event | V6 schema+aliases |
|---|---|---|---|---|
| app_version | 6652 | 22.000 | 0/ref or shared | alias record + shared slot column |
| build_number | 6652 | 49.000 | 0/ref or shared | alias record + shared slot column |
| device_class | 6652 | 33.367 | 0/ref or shared | alias record + shared slot column |
| event_id | 6652 | 49.000 | 16 (full mode) | 16B/value in full mode; excluded only by legacy contract |
| locale | 6652 | 16.000 | 0/ref or shared | alias record + shared slot column |
| name | 6652 | 23.990 | 0/ref or shared | compiled shape ID column |
| os_version | 6652 | 70.762 | 0/ref or shared | alias record + shared slot column |
| platform | 6652 | 20.000 | 0/ref or shared | alias record + shared slot column |
| properties.active_elapsed_ms | 6260 | 24.151 | 1.446 | key0 on known shape; typed value column |
| properties.ad_format | 17 | 0.066 | 0.041 | key0 on known shape; typed value column |
| properties.app_version | 6652 | 22.000 | 0/ref or shared | context ref if exact type/value; otherwise value column |
| properties.attempt_id | 6544 | 50.172 | 0.381 | key0 on known shape; typed value column |
| properties.attempt_number | 6544 | 17.732 | 0.108 | key0 on known shape; typed value column |
| properties.block_id | 4524 | 8.676 | 0.542 | key0 on known shape; typed value column |
| properties.block_type | 4524 | 14.440 | 1.040 | key0 on known shape; typed value column |
| properties.blocks_in_wave | 182 | 0.505 | 0.037 | key0 on known shape; typed value column |
| properties.board_rows | 1508 | 23.577 | 20.475 | key0 on known shape; typed value column |
| properties.camera_zoom | 6032 | 15.933 | 0.522 | key0 on known shape; typed value column |
| properties.cell_x | 1508 | 2.267 | 0.121 | key0 on known shape; typed value column |
| properties.cell_y | 1508 | 2.267 | 0.147 | key0 on known shape; typed value column |
| properties.city_id | 6544 | 10.821 | 0.035 | key0 on known shape; typed value column |
| properties.difficulty | 46 | 0.138 | 0.060 | key0 on known shape; typed value column |
| properties.drag_ms | 1508 | 3.007 | 0.367 | key0 on known shape; typed value column |
| properties.element | 68 | 0.182 | 0.083 | key0 on known shape; typed value column |
| properties.first_session | 23 | 0.072 | 0.003 | key0 on known shape; typed value column |
| properties.fps | 6032 | 7.254 | 0.715 | key0 on known shape; typed value column |
| properties.frame_ms | 6032 | 17.869 | 3.638 | key0 on known shape; typed value column |
| properties.free_memory_mb | 6032 | 18.969 | 0.787 | key0 on known shape; typed value column |
| properties.hint_type | 56 | 0.174 | 0.082 | key0 on known shape; typed value column |
| properties.hints_left | 56 | 0.118 | 0.015 | key0 on known shape; typed value column |
| properties.house_id | 6544 | 11.805 | 0.094 | key0 on known shape; typed value column |
| properties.house_progress | 1508 | 4.819 | 0.917 | key0 on known shape; typed value column |
| properties.launch_type | 23 | 0.069 | 0.027 | key0 on known shape; typed value column |
| properties.moves_count | 1508 | 3.561 | 0.160 | key0 on known shape; typed value column |
| properties.network | 17 | 0.043 | 0.023 | key0 on known shape; typed value column |
| properties.outcome | 1554 | 4.270 | 0.282 | key0 on known shape; typed value column |
| properties.placed_block_count | 4752 | 16.187 | 0.411 | key0 on known shape; typed value column |
| properties.placed_block_ids | 1508 | 13.613 | 7.508 | key0 on known shape; typed value column |
| properties.placed_state_hash | 3016 | 38.992 | 6.333 | binary32 distinct + indices; replay bit + anchors |
| properties.placement | 17 | 0.077 | 0.051 | key0 on known shape; typed value column |
| properties.release_x | 1508 | 4.887 | 0.917 | key0 on known shape; typed value column |
| properties.release_y | 1508 | 4.779 | 0.917 | key0 on known shape; typed value column |
| properties.remaining_block_count | 1508 | 5.886 | 0.176 | key0 on known shape; typed value column |
| properties.rotation | 1508 | 2.998 | 0.288 | key0 on known shape; typed value column |
| properties.score | 46 | 0.082 | 0.021 | key0 on known shape; typed value column |
| properties.screen | 68 | 0.194 | 0.080 | key0 on known shape; typed value column |
| properties.since_last_action_ms | 6032 | 24.895 | 1.744 | key0 on known shape; typed value column |
| properties.slot_index | 1508 | 3.174 | 0.120 | key0 on known shape; typed value column |
| properties.snap_distance | 1508 | 5.877 | 0.917 | key0 on known shape; typed value column |
| properties.target_cell_x | 1508 | 3.854 | 0.121 | key0 on known shape; typed value column |
| properties.target_cell_y | 1508 | 3.854 | 0.147 | key0 on known shape; typed value column |
| properties.total_block_count | 46 | 0.152 | 0.014 | key0 on known shape; typed value column |
| properties.touch_x | 6032 | 17.787 | 3.638 | key0 on known shape; typed value column |
| properties.touch_y | 6032 | 17.790 | 3.638 | key0 on known shape; typed value column |
| properties.ui_layer | 6032 | 15.414 | 0.428 | key0 on known shape; typed value column |
| properties.wave_attempt_id | 6544 | 55.091 | 0/ref or shared | attempt_id ref if exact; otherwise value column |
| properties.wave_index | 6452 | 13.579 | 0.262 | key0 on known shape; typed value column |
| sequence | 6652 | 14.127 | 0/ref or shared | integer/residual column |
| session_elapsed_ms | 6652 | 26.672 | 0/ref or shared | integer/residual column |
| session_id | 6652 | 51.000 | 0/ref or shared | alias record + shared slot column |
| timezone_offset_minutes | 6652 | 28.709 | 0/ref or shared | alias record + shared slot column |
| ts | 6652 | 18.000 | 0/ref or shared | integer/residual column |


## alt, holdout

| Поле | Значений | JSON component B/event | V6 raw values B/event | V6 schema+aliases |
|---|---|---|---|---|
| app_version | 5400 | 19.000 | 0/ref or shared | alias record + shared slot column |
| build_number | 5400 | 26.000 | 0/ref or shared | alias record + shared slot column |
| device_class | 5400 | 33.333 | 0/ref or shared | alias record + shared slot column |
| event_id | 5400 | 49.000 | 16 (full mode) | 16B/value in full mode; excluded only by legacy contract |
| locale | 5400 | 16.000 | 0/ref or shared | alias record + shared slot column |
| name | 5400 | 16.128 | 0/ref or shared | compiled shape ID column |
| os_version | 5400 | 70.833 | 0/ref or shared | alias record + shared slot column |
| platform | 5400 | 20.000 | 0/ref or shared | alias record + shared slot column |
| properties.board | 1229 | 138.831 | 135.974 | key0 on known shape; typed value column |
| properties.counter | 5400 | 12.878 | 0.834 | key0 on known shape; typed value column |
| properties.description | 1864 | 95.422 | 90.677 | key0 on known shape; typed value column |
| properties.measurement | 5400 | 31.664 | 8.010 | key0 on known shape; typed value column |
| properties.opaque | 2307 | 141.411 | 69.307 | key0 on known shape; typed value column |
| properties.phase | 5400 | 9.000 | 0.044 | key0 on known shape; typed value column |
| properties.release_label | 2694 | 16.962 | 0.117 | key0 on known shape; typed value column |
| sequence | 5400 | 13.880 | 0/ref or shared | integer/residual column |
| session_elapsed_ms | 5400 | 27.270 | 0/ref or shared | integer/residual column |
| session_id | 5400 | 51.000 | 0/ref or shared | alias record + shared slot column |
| timezone_offset_minutes | 5400 | 28.667 | 0/ref or shared | alias record + shared slot column |
| ts | 5400 | 18.000 | 0/ref or shared | integer/residual column |


## drift, holdout

| Поле | Значений | JSON component B/event | V6 raw values B/event | V6 schema+aliases |
|---|---|---|---|---|
| app_version | 2400 | 22.000 | 0/ref or shared | alias record + shared slot column |
| build_number | 2400 | 22.000 | 0/ref or shared | alias record + shared slot column |
| device_class | 2400 | 33.500 | 0/ref or shared | alias record + shared slot column |
| event_id | 2400 | 49.000 | 16 (full mode) | 16B/value in full mode; excluded only by legacy contract |
| locale | 2400 | 16.000 | 0/ref or shared | alias record + shared slot column |
| name | 2400 | 13.261 | 0/ref or shared | compiled shape ID column |
| os_version | 2400 | 70.750 | 0/ref or shared | alias record + shared slot column |
| platform | 2400 | 20.000 | 0/ref or shared | alias record + shared slot column |
| properties.counter | 2400 | 13.483 | 2.500 | key0 on known shape; typed value column |
| properties.flag | 2400 | 11.508 | 0.266 | key0 on known shape; typed value column |
| properties.label | 2400 | 15.349 | 4.133 | key0 on known shape; typed value column |
| properties.note | 188 | 1.874 | 1.478 | key0 on known shape; typed value column |
| properties.numeric | 2400 | 18.467 | 6.725 | key0 on known shape; typed value column |
| properties.opaque | 128 | 9.120 | 4.480 | key0 on known shape; typed value column |
| properties.release_label | 1600 | 18.000 | 2.146 | key0 on known shape; typed value column |
| sequence | 2400 | 13.852 | 0/ref or shared | integer/residual column |
| session_elapsed_ms | 2400 | 25.803 | 0/ref or shared | integer/residual column |
| session_id | 2400 | 51.000 | 0/ref or shared | alias record + shared slot column |
| timezone_offset_minutes | 2400 | 28.250 | 0/ref or shared | alias record + shared slot column |
| ts | 2400 | 18.000 | 0/ref or shared | integer/residual column |


Shared shape/context/time/sequence/extension raw B/event: base=4.046, rich=4.056, alt=7.557, drift=8.885. Сумма всех raw columns и shared metadata проверена assert против encode_raw.


Размер отдельного поля в готовом compressed кадре не уникален: удаление поля меняет схемы, словари и компрессор. Поэтому raw census не выдаётся за «точно6.06Б энтропии». Чистая практическая разница baseline/replay дана на одинаковых событиях с одинаковой рамкой в 02. UUID seed хеша, самого поля и IDs после удаления не магически восстанавливаются. Никаких несуществующих player_id/device_id колонок в корпус не добавлено.
