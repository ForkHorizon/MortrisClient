"""Measure pinned published AAR, not a Unity APK delta. Network required."""
import urllib.request,zipfile,io,json,hashlib
url='https://repo.maven.apache.org/maven2/com/github/luben/zstd-jni/1.5.7-6/zstd-jni-1.5.7-6.aar'
b=urllib.request.urlopen(url,timeout=30).read();z=zipfile.ZipFile(io.BytesIO(b))
print(json.dumps({'url':url,'aar_bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'native_entries':[{'name':x.filename,'raw_bytes':x.file_size,'zip_bytes':x.compress_size} for x in z.infolist() if x.filename.endswith('.so')]},indent=2))
