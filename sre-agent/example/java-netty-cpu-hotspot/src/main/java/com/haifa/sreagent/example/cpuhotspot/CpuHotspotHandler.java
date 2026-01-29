package com.haifa.sreagent.example.cpuhotspot;

import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.SimpleChannelInboundHandler;
import io.netty.handler.codec.http.FullHttpRequest;
import io.netty.handler.codec.http.HttpMethod;
import io.netty.handler.codec.http.HttpResponseStatus;
import io.netty.handler.codec.http.QueryStringDecoder;

import java.util.List;
import java.util.Map;

public final class CpuHotspotHandler extends SimpleChannelInboundHandler<FullHttpRequest> {
  private final CpuBurnController controller;

  public CpuHotspotHandler(CpuBurnController controller) {
    this.controller = controller;
  }

  @Override
  protected void channelRead0(ChannelHandlerContext ctx, FullHttpRequest req) {
    QueryStringDecoder q = new QueryStringDecoder(req.uri());
    String path = q.path();
    HttpMethod method = req.method();

    if ("/health".equals(path)) {
      RespUtil.sendText(ctx, req, HttpResponseStatus.OK, "OK\n");
      return;
    }

    if ("/pid".equals(path)) {
      long pid = ProcessHandle.current().pid();
      String json = "{\"pid\":" + pid + ",\"java\":\"" + escape(System.getProperty("java.version")) + "\"}";
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, json);
      return;
    }

    if ("/status".equals(path)) {
      String json = "{\"burn_running\":" + controller.isRunning() + ",\"burn_threads\":" + controller.threadCount() + ",\"burn_intensity\":" + controller.intensity() + "}";
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, json);
      return;
    }

    if ("/burn/start".equals(path) && HttpMethod.POST.equals(method)) {
      int threads = intParam(q.parameters(), "threads", Math.max(1, Runtime.getRuntime().availableProcessors()));
      int intensity = intParam(q.parameters(), "intensity", 100);
      controller.start(threads, intensity);
      String json = "{\"ok\":true,\"threads\":" + controller.threadCount() + ",\"intensity\":" + controller.intensity() + "}";
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, json);
      return;
    }

    if ("/burn/stop".equals(path) && HttpMethod.POST.equals(method)) {
      controller.stop();
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, "{\"ok\":true}");
      return;
    }

    if ("/cpu".equals(path) && HttpMethod.GET.equals(method)) {
      int ms = intParam(q.parameters(), "ms", 3000);
      long deadline = System.nanoTime() + Math.max(1, ms) * 1_000_000L;
      java.security.MessageDigest md;
      try {
        md = java.security.MessageDigest.getInstance("SHA-256");
      } catch (Exception e) {
        RespUtil.sendJson(ctx, req, HttpResponseStatus.INTERNAL_SERVER_ERROR, "{\"error\":\"sha256_unavailable\"}");
        return;
      }
      byte[] buf = new byte[256];
      java.util.concurrent.ThreadLocalRandom.current().nextBytes(buf);
      long ops = 0;
      while (System.nanoTime() < deadline) {
        CpuBurnTask.hotLoop(md, buf);
        ops++;
      }
      String json = "{\"ok\":true,\"ms\":" + ms + ",\"ops\":" + ops + "}";
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, json);
      return;
    }

    RespUtil.sendJson(ctx, req, HttpResponseStatus.NOT_FOUND, "{\"error\":\"not_found\"}");
  }

  private static int intParam(Map<String, List<String>> params, String key, int def) {
    List<String> vs = params.get(key);
    if (vs == null || vs.isEmpty()) {
      return def;
    }
    try {
      return Integer.parseInt(vs.get(0));
    } catch (Exception e) {
      return def;
    }
  }

  private static String escape(String s) {
    if (s == null) return "";
    return s.replace("\\", "\\\\").replace("\"", "\\\"");
  }
}
