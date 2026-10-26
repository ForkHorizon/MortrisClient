using System;
using System.IO;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;

static unsafe class Program
{
    [DllImport("libzstd")] static extern IntPtr ZSTD_createCCtx();
    [DllImport("libzstd")] static extern IntPtr ZSTD_createCDict(byte* dictionary, nuint length, int level);
    [DllImport("libzstd")] static extern nuint ZSTD_compress_usingCDict(IntPtr ctx, byte* dest, nuint capacity, byte* src, nuint size, IntPtr dictionary);
    [DllImport("libzstd")] static extern uint ZSTD_isError(nuint code);
    [DllImport("libzstd")] static extern void ZSTD_freeCCtx(IntPtr ctx);
    [DllImport("libzstd")] static extern void ZSTD_freeCDict(IntPtr dict);
    internal static Row[] LoadRows(JsonElement root, out int[] types)
    {
        types = JsonSerializer.Deserialize<int[]>(root.GetProperty("types").GetRawText());
        var source = root.GetProperty("rows");
        Row[] rows = new Row[source.GetArrayLength()];
        int ix = 0;
        foreach (var e in source.EnumerateArray())
        {
            var row = new Row { Sequence=e.GetProperty("sequence").GetInt64(), Time=e.GetProperty("time").GetInt64(), Elapsed=e.GetProperty("elapsed").GetInt64(), Shape=e.GetProperty("shape").GetInt32(), Context=e.GetProperty("context").GetInt32(), Session=e.GetProperty("session").GetInt32(), Id=Convert.FromHexString(e.GetProperty("id").GetString()), Columns=JsonSerializer.Deserialize<int[]>(e.GetProperty("columns").GetRawText()) };
            var values=e.GetProperty("values");row.Values=new Cell[values.GetArrayLength()];int j=0;
            foreach(var v in values.EnumerateArray())
            {
                int type=types[row.Columns[j]];Cell cell=new Cell();
                if(type==0)cell.I=v.GetInt64();else if(type==10)cell.U=v.GetUInt64();else if(type==2)cell.I=v.GetBoolean()?1:0;else if(type==3||type==4)cell.D=v.GetDouble();else if(type!=7)cell.S=v.GetString();
                row.Values[j++]=cell;
            }
            rows[ix++]=row;
        }
        return rows;
    }
    static int Main(string[] args)
    {
        using var doc = JsonDocument.Parse(File.ReadAllBytes(args[0]));
        var root = doc.RootElement;
        Row[] rows = LoadRows(root, out int[] types);
        var codec=new Columns();byte[] raw=new byte[2097152],compressed=new byte[262144],dictionary=File.ReadAllBytes(args[1]);
        bool numeric=root.TryGetProperty("integer_model",out var nm)&&nm.GetBoolean();
        bool stringsModel=root.TryGetProperty("string_model",out var sm)&&sm.GetBoolean();
        bool ids=root.GetProperty("preserve_ids").GetBoolean();IntPtr ctx=ZSTD_createCCtx(),dict;
        fixed(byte* p=dictionary)dict=ZSTD_createCDict(p,(nuint)dictionary.Length,1);
        if(ctx==IntPtr.Zero||dict==IntPtr.Zero)throw new Exception("zstd init");
        try
        {
            int length=codec.Pack(rows,types,ids,raw,numeric,stringsModel);nuint size=0;
            fixed(byte* src=raw)fixed(byte* dst=compressed)
            {
                for(int i=0;i<100;i++){length=codec.Pack(rows,types,ids,raw,numeric,stringsModel);size=ZSTD_compress_usingCDict(ctx,dst,(nuint)compressed.Length,src,(nuint)length,dict);if(ZSTD_isError(size)!=0)throw new Exception("zstd");}
                long before=GC.GetAllocatedBytesForCurrentThread();long start=Stopwatch.GetTimestamp();
                for(int i=0;i<1000;i++){length=codec.Pack(rows,types,ids,raw,numeric,stringsModel);size=ZSTD_compress_usingCDict(ctx,dst,(nuint)compressed.Length,src,(nuint)length,dict);if(ZSTD_isError(size)!=0)throw new Exception("zstd");}
                long ticks=Stopwatch.GetTimestamp()-start,alloc=GC.GetAllocatedBytesForCurrentThread()-before;
                File.WriteAllBytes(args[2],raw.AsSpan(0,length).ToArray());
                Console.WriteLine(JsonSerializer.Serialize(new { events=rows.Length, iterations=1000, raw_bytes=length, compressed_bytes=(long)size, gc_bytes=alloc, mean_ms=1000.0*ticks/Stopwatch.Frequency/1000, runtime=RuntimeInformation.FrameworkDescription, platform=RuntimeInformation.OSDescription, scope="typed column packing + reused native zstd; excludes ingress, framing, Unity, JNI and HTTP" }));
                if(alloc!=0)throw new Exception("GC allocation");
            }
        }
        finally{ZSTD_freeCCtx(ctx);ZSTD_freeCDict(dict);}
        return 0;
    }
}
