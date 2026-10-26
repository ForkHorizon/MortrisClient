using System;
using System.IO;
using System.Globalization;
using System.Diagnostics;
using System.Runtime.InteropServices;
using UnityEngine;
using Unity.Profiling;
using System.IO.Compression;
using System.Text;

namespace TransportV7Research
{
    [Serializable] public sealed class CellInput { public string i, u, d, s; }
    [Serializable] public sealed class RowInput
    {
        public long sequence, time, elapsed;
        public int shape, context, session;
        public byte[] id;
        public int[] columns;
        public CellInput[] values;
    }
    [Serializable] public sealed class FixtureInput
    {
        public int[] types;
        public RowInput[] rows;
        public bool preserve_ids, integer_model, string_model;
    }
    [Serializable] public sealed class FixtureList { public string[] fixtures; }
    [Serializable] public sealed class Measurement
    {
        public string fixture, unity_version, platform, processor, stage;
        public int events, iterations, raw_bytes, compressed_bytes, gc_alloc_samples;
        public long gc_bytes;
        public double mean_ms;
        public bool integer_model, string_model, passed;
    }
    [Serializable] public sealed class Report
    {
        public string runtime;
        public bool physical_phone, allocation_measurement_valid, development_build;
        public string scripting_backend;
        public long allocation_counter_control_bytes;
        public int allocation_control_samples, empty_control_samples;
        public Measurement[] measurements;
    }
    public static unsafe class Harness
    {
        static object allocationControl;
        // Host-only research dependency. No library path enters the SDK packer.
#if UNITY_ANDROID && !UNITY_EDITOR
        const string Zstd = "zstd";
#else
        const string Zstd = "/opt/homebrew/opt/zstd/lib/libzstd.dylib";
#endif
#if UNITY_EDITOR
        const string Backend = "Editor Mono";
#elif ENABLE_IL2CPP
        const string Backend = "IL2CPP";
#else
        const string Backend = "Mono";
#endif
        [DllImport(Zstd)] static extern IntPtr ZSTD_createCCtx();
        [DllImport(Zstd)] static extern IntPtr ZSTD_createCDict(byte* data, UIntPtr length, int level);
        [DllImport(Zstd)] static extern UIntPtr ZSTD_compress_usingCDict(IntPtr context, byte* dst, UIntPtr capacity, byte* src, UIntPtr size, IntPtr dictionary);
        [DllImport(Zstd)] static extern uint ZSTD_isError(UIntPtr result);
        [DllImport(Zstd)] static extern void ZSTD_freeCCtx(IntPtr context);
        [DllImport(Zstd)] static extern void ZSTD_freeCDict(IntPtr dictionary);

        static byte[] ReadAsset(string name)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            using(var archive=new ZipArchive(File.OpenRead(Application.dataPath),ZipArchiveMode.Read))
            {
                var entry=archive.GetEntry("assets/"+name);
                if(entry==null)throw new FileNotFoundException(name);
                using(var input=entry.Open())using(var memory=new MemoryStream())
                { input.CopyTo(memory);return memory.ToArray(); }
            }
#else
            return File.ReadAllBytes(Path.Combine(Application.streamingAssetsPath,name));
#endif
        }
        static Row[] Input(FixtureInput f)
        {
            var result = new Row[f.rows.Length];
            for (int ix = 0; ix < result.Length; ix++)
            {
                RowInput e = f.rows[ix];
                var row = new Row { Sequence=e.sequence, Time=e.time, Elapsed=e.elapsed, Shape=e.shape, Context=e.context, Session=e.session, Id=e.id, Columns=e.columns, Values=new Cell[e.values.Length] };
                for (int j = 0; j < e.values.Length; j++)
                {
                    CellInput v=e.values[j];int type=f.types[e.columns[j]];Cell cell=new Cell();
                    if (type==0) cell.I=long.Parse(v.i, CultureInfo.InvariantCulture);
                    else if(type==10) cell.U=ulong.Parse(v.u, CultureInfo.InvariantCulture);
                    else if(type==2) cell.I=long.Parse(v.i, CultureInfo.InvariantCulture);
                    else if(type==3||type==4) cell.D=BitConverter.Int64BitsToDouble(unchecked((long)ulong.Parse(v.d, NumberStyles.HexNumber, CultureInfo.InvariantCulture)));
                    else if(type!=7) cell.S=v.s;
                    row.Values[j]=cell;
                }
                result[ix]=row;
            }
            return result;
        }
        static Measurement Measure(string label, string outputDirectory, bool measureAllocations)
        {
            var f=JsonUtility.FromJson<FixtureInput>(Encoding.UTF8.GetString(ReadAsset(label+".json")));
            Row[] rows=Input(f);var codec=new Columns();
            byte[] raw=new byte[2097152],compressed=new byte[262144],dictBytes=ReadAsset(label+".dict");
            IntPtr context=ZSTD_createCCtx(),dictionary;
            fixed(byte* p=dictBytes) dictionary=ZSTD_createCDict(p,(UIntPtr)dictBytes.Length,1);
            if(context==IntPtr.Zero||dictionary==IntPtr.Zero) throw new Exception("zstd init");
            try
            {
                int length=0;UIntPtr compressedSize=UIntPtr.Zero;
                fixed(byte* src=raw) fixed(byte* dst=compressed)
                {
                    for(int i=0;i<200;i++)
                    {
                        length=codec.Pack(rows,f.types,f.preserve_ids,raw,f.integer_model,f.string_model);
                        compressedSize=ZSTD_compress_usingCDict(context,dst,(UIntPtr)compressed.Length,src,(UIntPtr)length,dictionary);
                        if(ZSTD_isError(compressedSize)!=0) throw new Exception("zstd warmup");
                    }
                    Stopwatch.GetTimestamp();GC.GetAllocatedBytesForCurrentThread();
                    ProfilerRecorder allocationsRecorder=default;
                    if(measureAllocations)
                    {
                        allocationsRecorder=ProfilerRecorder.StartNew(ProfilerCategory.Internal,"GC.Alloc",8192,ProfilerRecorderOptions.CollectOnlyOnCurrentThread|ProfilerRecorderOptions.StartImmediately);
                        if(!allocationsRecorder.Valid)throw new Exception("GC.Alloc recorder unavailable");
                    }
                    long start=Stopwatch.GetTimestamp();
                    const int iterations=1000;
                    for(int i=0;i<iterations;i++)
                    {
                        length=codec.Pack(rows,f.types,f.preserve_ids,raw,f.integer_model,f.string_model);
                        compressedSize=ZSTD_compress_usingCDict(context,dst,(UIntPtr)compressed.Length,src,(UIntPtr)length,dictionary);
                        if(ZSTD_isError(compressedSize)!=0) throw new Exception("zstd");
                    }
                    long ticks=Stopwatch.GetTimestamp()-start;
                    int allocationSamples=-1;
                    if(measureAllocations){allocationsRecorder.Stop();allocationSamples=allocationsRecorder.Count;allocationsRecorder.Dispose();}
                    long allocations=allocationSamples==0?0:-1;
                    // Serialization and payload export stay outside the measured interval.
                    var exact=new byte[length];Buffer.BlockCopy(raw,0,exact,0,length);
                    File.WriteAllBytes(Path.Combine(outputDirectory,label+".raw"),exact);
                    return new Measurement { fixture=label, unity_version=Application.unityVersion, platform=Application.platform.ToString(), processor=SystemInfo.processorType,
                        stage="pretyped columns + reused native zstd; excludes ingress/framing/JNI/HTTP", events=rows.Length, iterations=iterations,
                        raw_bytes=length, compressed_bytes=checked((int)compressedSize.ToUInt64()), gc_bytes=allocations, gc_alloc_samples=allocationSamples, mean_ms=1000.0*ticks/Stopwatch.Frequency/iterations,
                        integer_model=f.integer_model, string_model=f.string_model, passed=!measureAllocations||allocations==0 };
                }
            }
            finally { ZSTD_freeCCtx(context);ZSTD_freeCDict(dictionary); }
        }
        public static bool Run(string outputDirectory, string runtime, bool requireAllocations=true)
        {
            Directory.CreateDirectory(outputDirectory);
            
            FixtureList fixtures=JsonUtility.FromJson<FixtureList>(Encoding.UTF8.GetString(ReadAsset("manifest.json")));
            var report=new Report { runtime=runtime, physical_phone=false, development_build=UnityEngine.Debug.isDebugBuild, scripting_backend=Backend, measurements=new Measurement[fixtures.fixtures.Length] };
            using(var empty=ProfilerRecorder.StartNew(ProfilerCategory.Internal,"GC.Alloc",32,ProfilerRecorderOptions.CollectOnlyOnCurrentThread|ProfilerRecorderOptions.StartImmediately))
            {
                empty.Stop();report.empty_control_samples=empty.Valid?empty.Count:-1;
            }
            using(var control=ProfilerRecorder.StartNew(ProfilerCategory.Internal,"GC.Alloc",32,ProfilerRecorderOptions.CollectOnlyOnCurrentThread|ProfilerRecorderOptions.StartImmediately))
            {
                long calibrationStart=GC.GetAllocatedBytesForCurrentThread();
                allocationControl=new byte[4096];
                report.allocation_counter_control_bytes=GC.GetAllocatedBytesForCurrentThread()-calibrationStart;
                GC.KeepAlive(allocationControl);
                control.Stop();report.allocation_control_samples=control.Valid?control.Count:0;
            }
            report.allocation_measurement_valid=report.allocation_control_samples>0&&report.empty_control_samples==0;
            if(requireAllocations&&!report.allocation_measurement_valid)throw new Exception("GC.Alloc recorder calibration failed");
            bool passed=true;
            for(int i=0;i<fixtures.fixtures.Length;i++)
            {
                report.measurements[i]=Measure(fixtures.fixtures[i],outputDirectory,report.allocation_measurement_valid);
                passed &= report.measurements[i].passed;
                UnityEngine.Debug.Log("V7 fixture "+fixtures.fixtures[i]+": GC="+report.measurements[i].gc_bytes);
            }
            File.WriteAllText(Path.Combine(outputDirectory,"report.json"),JsonUtility.ToJson(report,true));
            return passed;
        }
    }
}
