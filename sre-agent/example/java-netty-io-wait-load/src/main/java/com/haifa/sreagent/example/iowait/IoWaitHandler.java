package com.haifa.sreagent.example.iowait;

import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.SimpleChannelInboundHandler;
import io.netty.handler.codec.http.FullHttpRequest;
import io.netty.handler.codec.http.HttpMethod;
import io.netty.handler.codec.http.HttpResponseStatus;
import io.netty.handler.codec.http.QueryStringDecoder;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

public final class IoWaitHandler extends SimpleChannelInboundHandler<FullHttpRequest> {
  private final IoBurnController controller;

  public IoWaitHandler(IoBurnController controller) {
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
      Path dir = controller.dir();
      String json = "{\"io_running\":" + controller.isRunning()
          + ",\"threads\":" + controller.threadCount()
          + ",\"mbPerOp\":" + controller.mbPerOp()
          + ",\"fsync\":" + controller.fsync()
          + ",\"dir\":\"" + escape(dir == null ? "" : dir.toString()) + "\"}";
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, json);
      return;
    }

    if ("/io/start".equals(path) && HttpMethod.POST.equals(method)) {
      int threads = intParam(q.parameters(), "threads", Math.max(1, Runtime.getRuntime().availableProcessors() / 2));
      int mbPerOp = intParam(q.parameters(), "mbPerOp", 64);
      boolean fsync = boolParam(q.parameters(), "fsync", true);
      String dir = strParam(q.parameters(), "dir", "/tmp");
      controller.start(threads, mbPerOp, fsync, dir);
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, "{\"ok\":true}");
      return;
    }

    if ("/io/stop".equals(path) && HttpMethod.POST.equals(method)) {
      controller.stop();
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, "{\"ok\":true}");
      return;
    }

    if ("/io/once".equals(path) && HttpMethod.GET.equals(method)) {
      int mb = intParam(q.parameters(), "mb", 256);
      boolean fsync = boolParam(q.parameters(), "fsync", true);
      String dir = strParam(q.parameters(), "dir", "/tmp");
      AtomicOneShot.writeOnce(dir, mb, fsync);
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, "{\"ok\":true,\"mb\":" + mb + ",\"fsync\":" + fsync + "}");
      return;
    }

    RespUtil.sendJson(ctx, req, HttpResponseStatus.NOT_FOUND, "{\"error\":\"not_found\"}");
  }

  private static int intParam(Map<String, List<String>> params, String key, int def) {
    List<String> vs = params.get(key);
    if (vs == null || vs.isEmpty()) return def;
    try {
      return Integer.parseInt(vs.get(0));
    } catch (Exception e) {
      return def;
    }
  }

  private static boolean boolParam(Map<String, List<String>> params, String key, boolean def) {
    List<String> vs = params.get(key);
    if (vs == null || vs.isEmpty()) return def;
    String v = vs.get(0);
    return "1".equals(v) || "true".equalsIgnoreCase(v) || "yes".equalsIgnoreCase(v);
  }

  private static String strParam(Map<String, List<String>> params, String key, String def) {
    List<String> vs = params.get(key);
    if (vs == null || vs.isEmpty()) return def;
    return vs.get(0);
  }

  private static String escape(String s) {
    if (s == null) return "";
    return s.replace("\\", "\\\\").replace("\"", "\\\"");
  }
}
