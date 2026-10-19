using System;
using System.Net;
using System.Net.Sockets;
using System.Threading.Tasks;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class RedirectTests
    {
        private static HttpListener Listen(out string url)
        {
            var probe = new TcpListener(IPAddress.Loopback, 0); probe.Start();
            int port = ((IPEndPoint)probe.LocalEndpoint).Port; probe.Stop();
            url = "http://127.0.0.1:" + port;
            var listener = new HttpListener(); listener.Prefixes.Add(url + "/"); listener.Start();
            return listener;
        }

        [Fact]
        public void A307IsNotFollowedAndNoBodyReachesTheOtherOrigin()
        {
            using var target = Listen(out var targetUrl);
            using var origin = Listen(out var originUrl);
            int targetHits = 0;
            var targetLoop = Task.Run(() => { try { var c = target.GetContext(); targetHits++; c.Response.StatusCode = 200; c.Response.Close(); } catch (HttpListenerException) { } });
            var originLoop = Task.Run(() => { var c = origin.GetContext(); c.Response.StatusCode = 307; c.Response.RedirectLocation = targetUrl + "/stolen"; c.Response.Close(); });

            using var client = HttpV7Transport.CreateClient();
            var response = new HttpV7Transport(client, originUrl).PostJson("/v2/streams/sync", "{\"secret\":1}", "credential");
            originLoop.Wait(5000);
            target.Stop();
            targetLoop.Wait(5000);

            Assert.Equal(307, response.Status);
            Assert.Equal(0, targetHits);
        }
    }
}
