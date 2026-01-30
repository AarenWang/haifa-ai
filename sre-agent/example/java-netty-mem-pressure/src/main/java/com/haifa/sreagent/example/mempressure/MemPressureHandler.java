package com.haifa.sreagent.example.mempressure;

import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.SimpleChannelInboundHandler;
import io.netty.handler.codec.http.FullHttpRequest;
import io.netty.handler.codec.http.HttpMethod;
import io.netty.handler.codec.http.HttpResponseStatus;
import io.netty.handler.codec.http.QueryStringDecoder;

import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class MemPressureHandler extends SimpleChannelInboundHandler<FullHttpRequest> {
  private final MemPressureController controller;

  public MemPressureHandler(MemPressureController controller) {
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
      String json = "{\"mem_running\":" + controller.isRunning()
          + ",\"targetMb\":" + controller.targetMb()
          + ",\"chunkMb\":" + controller.chunkMb()
          + ",\"intervalMs\":" + controller.intervalMs()
          + ",\"retainedMb\":" + controller.retainedMb()
          + ",\"retainedChunks\":" + controller.retainedChunks()
          + "}";
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, json);
      return;
    }

    if ("/mem/start".equals(path) && HttpMethod.POST.equals(method)) {
      int targetMb = intParam(q.parameters(), "targetMb", 512);
      int chunkMb = intParam(q.parameters(), "chunkMb", 4);
      int intervalMs = intParam(q.parameters(), "intervalMs", 50);
      String mode = strParam(q.parameters(), "mode", "heap");
      if (!"heap".equals(mode.toLowerCase(Locale.ROOT))) {
        RespUtil.sendJson(ctx, req, HttpResponseStatus.BAD_REQUEST, "{\"error\":\"unsupported_mode\"}");
        return;
      }
      controller.start(targetMb, chunkMb, intervalMs);
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, "{\"ok\":true}");
      return;
    }

    if ("/mem/stop".equals(path) && HttpMethod.POST.equals(method)) {
      controller.stop();
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, "{\"ok\":true}");
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
