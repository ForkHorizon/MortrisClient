// Content-addressed cache of transport assets (catalogs, dictionaries): in memory or on disk.
using System;
using System.Collections.Generic;
using System.IO;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>Content-addressed cache for catalogs and dictionaries (a file name is the asset id).</summary>
    internal interface IV7AssetStore
    {
        byte[] TryRead(string kind, string id);
        void Write(string kind, string id, byte[] data);
        void Delete(string kind, string id);
    }

    internal sealed class MemoryV7AssetStore : IV7AssetStore
    {
        private readonly Dictionary<string, byte[]> _items = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        public byte[] TryRead(string kind, string id) => _items.TryGetValue(kind + "/" + id, out var data) ? data : null;
        public void Write(string kind, string id, byte[] data) => _items[kind + "/" + id] = data;
        public void Delete(string kind, string id) => _items.Remove(kind + "/" + id);
    }

    internal sealed class FileV7AssetStore : IV7AssetStore
    {
        private readonly string _directory;
        internal FileV7AssetStore(string directory) { _directory = directory; }

        public byte[] TryRead(string kind, string id)
        {
            try { var path = PathFor(kind, id); return File.Exists(path) ? File.ReadAllBytes(path) : null; }
            catch (IOException) { return null; }
            catch (UnauthorizedAccessException) { return null; }
        }

        public void Write(string kind, string id, byte[] data)
        {
            try
            {
                Directory.CreateDirectory(_directory);
                var temporary = PathFor(kind, id) + ".tmp";
                File.WriteAllBytes(temporary, data);
                if (File.Exists(PathFor(kind, id))) File.Delete(PathFor(kind, id));
                File.Move(temporary, PathFor(kind, id));
            }
            catch (IOException) { /* a cache miss is only a refetch */ }
            catch (UnauthorizedAccessException) { }
        }

        public void Delete(string kind, string id)
        {
            try { File.Delete(PathFor(kind, id)); } catch (IOException) { } catch (UnauthorizedAccessException) { }
        }

        private string PathFor(string kind, string id) => Path.Combine(_directory, kind + "-" + id + ".bin");
    }
}
