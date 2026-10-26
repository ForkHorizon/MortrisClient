"""Actual fixed-window header synthesis trial, isolated from recommended frame."""
import json
from pathlib import Path
import zstandard as z
from framing import compressor
ROOT=Path(__file__).resolve().parent
d=z.ZstdCompressionDict((ROOT.parents[1]/'transport-v3/06-experiments/results/dict64_base.bin').read_bytes())
rows=[]
for n in [1,128,1559,10000,100000,262144,1048576]:
 raw=(b'example_data '*((n+12)//13))[:n];c=compressor(9,d).compress(raw)
 assert c[0]==0 # no checksum/dict-id/content-size flags
 stripped=c[2:]
 # Use fixed 1 MiB window instead of original descriptor; all matches remain legal.
 rebuilt=b'\x00\x50'+stripped
 decoded=z.ZstdDecompressor(dict_data=d,format=z.FORMAT_ZSTD1_MAGICLESS,max_window_size=2097152).decompress(rebuilt,max_output_size=n,allow_extra_data=False)
 assert decoded==raw
 rows.append({'raw_bytes':n,'original_window':z.get_frame_parameters(b'\x28\xb5\x2f\xfd'+c).window_size,'synthesized_window':1048576,'wire_bytes_saved':2,'roundtrip':True})
(ROOT/'results/header-synthesis.json').write_text(json.dumps(rows,indent=2))
