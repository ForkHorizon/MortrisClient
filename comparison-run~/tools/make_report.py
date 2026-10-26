#!/usr/bin/env python3
"""REPORT.md = report_head.md + tables (build_tables.py + analyze_long.py) + report_tail.md; RESULTS_TABLES.md = tables only."""
import subprocess, sys
from pathlib import Path
CR = Path(__file__).resolve().parent.parent
tables = subprocess.run([sys.executable, str(CR / 'tools/build_tables.py')], capture_output=True, text=True).stdout
long_tbl = subprocess.run([sys.executable, str(CR / 'tools/analyze_long.py')], capture_output=True, text=True).stdout
tables += '\n## Таблица G. 10-минутная игровая сессия на телефоне (5 событий/с, 3000 событий, естественные таймеры SDK, без принудительного сброса)\n\n' + long_tbl
(CR / 'RESULTS_TABLES.md').write_text(tables)
(CR / 'REPORT.md').write_text((CR / 'report_head.md').read_text() + '\n## 2. Результаты (таблицы)\n\nСреднее ±95% ДИ там, где несколько повторов; иначе один прогон. «Байт вверх» — заголовки+тела запросов на доставленное событие; «с TLS» — вверх+вниз+модель TLS.\n\n' + tables + '\n## 3. Как читать\n\n* **Таблица A** — главный CPU/память/кадры/вес на реальных событиях Puzzle (3 повтора, слайсы 0–2).\n* **Таблицы B-*** — доставка и сохранность полей по четырём наборам (эмулятор, один прогон); «расчёт по лимитам» — Firebase/Facebook/Adjust, их содержимое на проводе нельзя прочитать, считается по документированным лимитам.\n* **C1–C5** — сбои и дренаж; **D** — размер пачки и частота (лимиты сервера подняты); **E/E2** — всплески; **F** — сервер; **G** — длинная сессия.\n' + (CR / 'report_findings.md').read_text() + (CR / 'report_tail.md').read_text())
print('ok', len((CR / 'REPORT.md').read_text()))
